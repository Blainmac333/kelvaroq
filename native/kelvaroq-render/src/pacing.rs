//! CPU intervals between successful returns from DXGI Present, in groups of 30.
//! Enabled by KELVAROQ_FRAME_TIMINGS=1 in ordinary and diagnostic builds.
//! Wait totals count completed calls across threads. For a 30-interval window,
//! the nearest-rank p95 is the second-longest interval and p99 is the longest.

use std::io::Write;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

const SAMPLES: usize = 30;

/// Start timing an operation if collection was enabled at process startup.
pub fn start() -> Option<Instant> {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    ENABLED
        .get_or_init(|| std::env::var_os("KELVAROQ_FRAME_TIMINGS").is_some_and(|v| v == "1"))
        .then(Instant::now)
}

#[derive(Default)]
struct Waits {
    count: u64,
    requested: Duration,
    elapsed: Duration,
}

#[derive(Default)]
struct Window {
    previous: Option<(u64, Instant)>,
    first_frame: u64,
    intervals: Vec<Duration>,
    dxgi: Duration,
    waits: Waits,
}

struct Report {
    first: u64,
    last: u64,
    p50: Duration,
    p95: Duration,
    p99: Duration,
    dxgi: Duration,
    waits: Waits,
}

impl Window {
    fn wait(&mut self, requested: Duration, elapsed: Duration) {
        if self.previous.is_some() {
            self.waits.count += 1;
            self.waits.requested += requested;
            self.waits.elapsed += elapsed;
        }
    }

    fn present(&mut self, frame: u64, start: Instant, end: Instant, status: i32) -> Option<Report> {
        // An occluded swap chain returns a positive status; only S_OK counts.
        if status != 0 {
            *self = Self::default();
            return None;
        }
        let (previous_frame, previous_time) = self.previous.replace((frame, end))?;
        if self.intervals.is_empty() {
            self.first_frame = previous_frame;
        }
        self.intervals.push(end.duration_since(previous_time));
        self.dxgi += end.duration_since(start);
        if self.intervals.len() < SAMPLES {
            return None;
        }
        self.intervals.sort_unstable();
        // Nearest-rank percentiles of completed intervals, including their tails.
        let percentile = |p: usize| self.intervals[(p * SAMPLES).div_ceil(100) - 1];
        let report = Report {
            first: self.first_frame,
            last: frame,
            p50: percentile(50),
            p95: percentile(95),
            p99: percentile(99),
            dxgi: std::mem::take(&mut self.dxgi),
            waits: std::mem::take(&mut self.waits),
        };
        self.intervals.clear();
        Some(report)
    }
}

fn window() -> std::sync::MutexGuard<'static, Window> {
    static WINDOW: OnceLock<Mutex<Window>> = OnceLock::new();
    WINDOW
        .get_or_init(Mutex::default)
        .lock()
        .unwrap_or_else(|e| e.into_inner())
}

/// Record a completed guest frame wait with its requested and observed durations.
pub fn wait(requested: Duration, elapsed: Duration) {
    window().wait(requested, elapsed);
}

/// Finish a timed DXGI call and write any completed sample window to stderr.
pub fn present(frame: u64, start: Instant, end: Instant, status: i32) {
    let sample = window().present(frame, start, end, status);
    if let Some(r) = sample {
        // This optional diagnostic must not fail a presentation on a closed pipe.
        let _ = writeln!(
            std::io::stderr().lock(),
            "KELVAROQ_FRAME_TIMINGS frames={}..{} samples={} cpu_present_p50_us={} cpu_present_p95_us={} cpu_present_p99_us={} dxgi_call_sum_us={} waits={} wait_requested_sum_us={} wait_elapsed_sum_us={}",
            r.first,
            r.last,
            SAMPLES,
            r.p50.as_micros(),
            r.p95.as_micros(),
            r.p99.as_micros(),
            r.dxgi.as_micros(),
            r.waits.count,
            r.waits.requested.as_micros(),
            r.waits.elapsed.as_micros()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reports_intervals_and_separates_requested_from_elapsed_waits() {
        let us = Duration::from_micros;
        let mut clock = Instant::now();
        let mut window = Window::default();
        window.wait(us(88), us(99));
        assert!(window.present(4, clock, clock, 0).is_none());
        for n in 1..=30 {
            clock += us(31 - n);
            window.wait(us(1), us(2));
            let result = window.present(4 + n, clock - us(1), clock, 0);
            if n < 30 {
                assert!(result.is_none());
            } else {
                let r = result.unwrap();
                assert_eq!((r.first, r.last), (4, 34));
                assert_eq!((r.p50, r.p95, r.p99), (us(15), us(29), us(30)));
                assert_eq!(r.dxgi, us(30));
                assert_eq!(
                    (r.waits.count, r.waits.requested, r.waits.elapsed),
                    (30, us(30), us(60))
                );
            }
        }
        for n in 1..=30 {
            clock += us(7);
            let result = window.present(34 + n, clock, clock, 0);
            if n == 30 {
                let r = result.unwrap();
                assert_eq!((r.first, r.last, r.p99, r.waits.count), (34, 64, us(7), 0));
            }
        }
    }

    #[test]
    fn failures_and_occlusion_start_a_new_window() {
        let t = Instant::now();
        let mut window = Window::default();
        for status in [-1, 0x087a0001] {
            assert!(window.present(1, t, t, 0).is_none());
            assert!(window.present(2, t, t, 0).is_none());
            window.wait(Duration::ZERO, Duration::from_millis(1));
            assert!(window.present(3, t, t, status).is_none());
            assert!(window.previous.is_none() && window.intervals.is_empty());
            assert_eq!(window.waits.count, 0);
        }
    }
}
