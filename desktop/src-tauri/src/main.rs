#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod engine;
use engine::{EngineInfo, EngineState};
use std::path::PathBuf;
use std::process::Command;
use tauri::{Manager, State, WebviewWindow};
/// 桌面壳持有的工程路径（由启动时的向上搜索确定）。
pub struct Paths {
    pub root: PathBuf,
}
#[tauri::command]
fn engine_status(state: State<'_, EngineState>) -> EngineInfo {
    state.info()
}
#[tauri::command]
fn start_engine(state: State<'_, EngineState>, paths: State<'_, Paths>) -> Result<EngineInfo, String> {
    eprintln!("[bridge] start_engine 被调用, root={}", paths.root.display());
    let result = state.start(&paths.root);
    eprintln!("[bridge] start_engine 结果={:?}", result);
    result
}
#[tauri::command]
fn stop_engine(state: State<'_, EngineState>) -> Result<(), String> {
    state.stop()
}
#[tauri::command]
fn open_data_folder(paths: State<'_, Paths>) -> Result<String, String> {
    let dir = paths.root.join("engine").join("data");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    reveal(&dir)?;
    Ok(dir.to_string_lossy().to_string())
}
#[tauri::command]
fn open_works_folder(paths: State<'_, Paths>) -> Result<String, String> {
    let dir = paths.root.join("engine").join("data").join("works");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    reveal(&dir)?;
    Ok(dir.to_string_lossy().to_string())
}
#[tauri::command]
fn window_minimize(window: WebviewWindow) {
    let _ = window.minimize();
}
#[tauri::command]
fn window_toggle_maximize(window: WebviewWindow) {
    let _ = if window.is_maximized().unwrap_or(false) {
        window.unmaximize()
    } else {
        window.maximize()
    };
}
#[tauri::command]
fn window_close(window: WebviewWindow) {
    let _ = window.close();
}
fn reveal(path: &PathBuf) -> Result<(), String> {
    #[cfg(windows)]
    let result = Command::new("explorer").arg(path).spawn();
    #[cfg(target_os = "macos")]
    let result = Command::new("open").arg(path).spawn();
    #[cfg(all(not(windows), not(target_os = "macos")))]
    let result = Command::new("xdg-open").arg(path).spawn();
    result.map(|_| ()).map_err(|e| e.to_string())
}
fn find_project_root() -> PathBuf {
    if let Ok(p) = std::env::var("MANGJU_PROJECT_ROOT") {
        return PathBuf::from(p);
    }
    let start = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut cursor = start.as_path();
    for _ in 0..8 {
        if cursor.join("engine").join("app").join("main.py").is_file() {
            return cursor.to_path_buf();
        }
        match cursor.parent() {
            Some(p) => cursor = p,
            None => break,
        }
    }
    start
}
fn main() {
    let root = find_project_root();
    tauri::Builder::default()
        .manage(Paths { root })
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![
            engine_status,
            start_engine,
            stop_engine,
            open_data_folder,
            open_works_folder,
            window_minimize,
            window_toggle_maximize,
            window_close
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<EngineState>() {
                    let _ = state.stop();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("鲸鲨漫剧桌面壳启动失败");
}
