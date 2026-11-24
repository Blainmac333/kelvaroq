#[cfg(windows)]
mod gpu;
mod image;

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, ExitCode, Stdio},
};

#[derive(Parser)]
#[command(version, about)]
struct Args {
    #[command(subcommand)]
    command: Action,
}

#[derive(Subcommand)]
enum Action {
    /// Describe an x64 PE and its startup requirements.
    Inspect {
        image: PathBuf,
        #[arg(long)]
        json: bool,
    },
    /// Execute TLS and startup instructions in the isolated reference CPU.
    Boot {
        image: PathBuf,
        #[arg(long, default_value = "python")]
        python: PathBuf,
        /// Virtual console profile exposed to the guest.
        #[arg(long, value_parser = ["series-x", "series-s"], default_value = "series-x")]
        console: String,
    },
    /// Verify offscreen D3D12 rendering and readback on hardware adapters.
    Gpu {
        /// DXGI adapter index. By default all hardware adapters are tested.
        #[arg(long)]
        adapter: Option<u32>,
    },
}

fn run(args: Args) -> Result<ExitCode> {
    match args.command {
        Action::Inspect { image, json } => {
            let plan = image::inspect(&image)?;
            if json {
                println!("{}", serde_json::to_string_pretty(&plan)?);
            } else {
                println!(
                    "PE32+ x64 | entry RVA {:#x} | {} sections | {} imports | {} TLS callbacks\nSHA-256 {}",
                    plan.entry,
                    plan.sections.len(),
                    plan.imports.len(),
                    plan.callbacks.len(),
                    plan.sha256
                );
            }
        }
        Action::Boot {
            image,
            python,
            console,
        } => {
            let plan = image::inspect(&image)?;
            let mut child = Command::new(&python)
                .args(["-I", "-X", "utf8", "-m", "kelvaroq_reference"])
                .arg(&image)
                .arg(console)
                .stdin(Stdio::piped())
                .spawn()
                .with_context(|| format!("starting {}", python.display()))?;
            let write = (|| -> Result<()> {
                let mut input = child.stdin.take().context("reference CPU stdin")?;
                serde_json::to_writer(&mut input, &plan)?;
                input.flush()?;
                Ok(())
            })();
            let status = child.wait()?;
            write?;
            return match status.code() {
                Some(0) => Ok(ExitCode::SUCCESS),
                Some(2) => Ok(ExitCode::from(2)),
                _ => bail!("reference CPU exited with {status}"),
            };
        }
        Action::Gpu { adapter } => {
            #[cfg(windows)]
            gpu::probe(adapter)?;
            #[cfg(not(windows))]
            {
                let _ = adapter;
                bail!("D3D12 requires Windows");
            }
        }
    }
    Ok(ExitCode::SUCCESS)
}

fn main() -> ExitCode {
    match run(Args::parse()) {
        Ok(status) => status,
        Err(e) => {
            eprintln!("kelvaroq: {e:#}");
            ExitCode::FAILURE
        }
    }
}
