// Open Science's curated MCP connector environment. Packages are installed on
// demand into an app-managed uv environment; the user's Python is untouched.
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

fn env_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("runtime")
        .join("science-mcp-env"))
}

fn python_bin(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = env_dir(app)?;
    #[cfg(windows)]
    return Ok(dir.join("Scripts").join("python.exe"));
    #[cfg(not(windows))]
    Ok(dir.join("bin").join("python"))
}

#[tauri::command]
pub fn science_mcp_python(app: AppHandle) -> Result<Option<String>, String> {
    let python = python_bin(&app)?;
    Ok(python
        .exists()
        .then(|| python.to_string_lossy().to_string()))
}

#[tauri::command]
pub async fn setup_science_mcp(app: AppHandle, package: String) -> Result<String, String> {
    if !is_safe_package(&package) {
        return Err("invalid package name".into());
    }
    let dir = env_dir(&app)?;
    std::fs::create_dir_all(&dir).map_err(|error| error.to_string())?;
    let python = python_bin(&app)?;
    if !python.exists() {
        crate::uv::create_venv(&app, "science", &dir).await?;
    }
    crate::uv::run_uv(
        &app,
        "science",
        vec![
            "pip".into(),
            "install".into(),
            "--python".into(),
            python.to_string_lossy().to_string(),
            package,
        ],
        "uv pip install",
    )
    .await?;
    Ok(python.to_string_lossy().to_string())
}

fn is_safe_package(package: &str) -> bool {
    let core = package
        .split_once("==")
        .map(|(name, _)| name)
        .unwrap_or(package);
    !core.is_empty()
        && !core.starts_with('-')
        && core.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-')
        })
        && package.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | '-' | '=')
        })
}

#[cfg(test)]
mod tests {
    use super::is_safe_package;

    #[test]
    fn accepts_real_package_names_and_pins() {
        assert!(is_safe_package("paper-search-mcp"));
        assert!(is_safe_package("biomcp-python"));
        assert!(is_safe_package("jupyter-mcp-server==0.14.0"));
    }

    #[test]
    fn rejects_argument_and_shell_injection() {
        for package in [
            "",
            "--upgrade",
            "pkg; rm",
            "pkg && echo",
            "pkg --index-url x",
            "pkg\nother",
        ] {
            assert!(!is_safe_package(package));
        }
    }
}
