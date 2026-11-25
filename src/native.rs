use anyhow::{Context, Result, bail};
use std::{
    fs::File,
    path::Path,
    process::{Command, ExitCode},
};
use windows::{
    Win32::System::Console::{AllocConsole, SetConsoleTitleW},
    core::w,
};

pub(crate) fn run(engine: &Path, image: &Path, console: &str) -> Result<ExitCode> {
    // Give the native file services a conventional DOS path when it names
    // the same file. Keep the extended form for paths that require it.
    let image = dunce::canonicalize(image).context("ouverture de l’exécutable du jeu")?;
    let mut game = Command::new(engine);
    game.current_dir(engine.parent().context("dossier du moteur natif")?)
        .env(
            "VICTORY_GAME_DIR",
            image.parent().context("dossier du jeu")?,
        )
        .arg("run")
        .arg(&image)
        .args(["--console", console, "--execute"]);
    if std::env::var_os("KELVAROQ_DESKTOP_LOG").is_some() {
        // The desktop launcher starts this CLI without a console and captures its
        // stderr for the error dialog. Give the child its own visible log output.
        unsafe {
            AllocConsole().context("ouverture du journal Windows")?;
            SetConsoleTitleW(w!("Kelvaroq | Journal du jeu"))?;
        }
        let log = File::options().write(true).open("CONOUT$")?;
        game.stdout(log.try_clone()?).stderr(log);
    }
    let status = game
        .status()
        .with_context(|| format!("démarrage de {}", engine.display()))?;
    if !status.success() {
        bail!("Le moteur natif s’est arrêté ({status}).");
    }
    Ok(ExitCode::SUCCESS)
}
