// Appends frontend diagnostics to <app-data>/debug.log so we can see what the
// webview experiences (connection attempts, SSE events, errors) in packaged builds.
use std::io::Write;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

#[tauri::command]
pub fn log_debug(app: AppHandle, message: String) {
    let Ok(dir) = app.path().app_data_dir() else { return };
    let _ = std::fs::create_dir_all(&dir);
    let path = dir.join("debug.log");
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{ts} {message}");
    }
}
