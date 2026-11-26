//! 本地引擎进程管理：Tauri 桌面壳负责拉起 / 停止 FastAPI 子进程，
//! 并通过 IPC 把随机令牌交给前端，令牌不经过任何公开 HTTP 端点。
use serde::Serialize;
use std::net::TcpListener;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
/// 前端调用 start_engine 后拿到的连接信息。
#[derive(Debug, Clone, Serialize)]
pub struct EngineInfo {
    pub running: bool,
    pub port: u16,
    pub token: String,
    pub base_url: String,
    pub error: Option<String>,
}
impl Default for EngineInfo {
    fn default() -> Self {
        Self {
            running: false,
            port: 0,
            token: String::new(),
            base_url: String::new(),
            error: None,
        }
    }
}
#[derive(Default)]
pub struct EngineState {
    child: Mutex<Option<Child>>,
    info: Mutex<EngineInfo>,
}
fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(7420)
}
fn port_open(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_err()
}
fn random_token() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(1);
    let pid = std::process::id() as u128;
    format!("{:032x}{:032x}", nanos, pid)
}
fn find_python(root: &Path) -> Result<std::path::PathBuf, String> {
    let candidates = [
        root.join(".venv").join("Scripts").join("python.exe"),
        root.join(".venv").join("bin").join("python"),
        root.join("venv").join("Scripts").join("python.exe"),
    ];
    candidates
        .iter()
        .find(|p| p.is_file())
        .cloned()
        .ok_or_else(|| format!("未找到 Python 虚拟环境，请在 {} 执行 python -m venv .venv", root.display()))
}
impl EngineState {
    pub fn info(&self) -> EngineInfo {
        self.info
            .lock()
            .map(|g| g.clone())
            .unwrap_or_default()
    }
    /// 打包模式：安装包内捆绑的 PyInstaller 引擎（resources/engine/whaleju-engine.exe）。
    /// 存在则直接拉起，不再要求用户机器上有源码与 .venv。
    fn bundled_engine(resource_dir: &Path) -> Option<std::path::PathBuf> {
        let exe = resource_dir
            .join("engine")
            .join("whaleju-engine.exe");
        exe.is_file().then_some(exe)
    }
    pub fn start(&self, root: &Path, resource_dir: &Path, data_root: &Path) -> Result<EngineInfo, String> {
        // 已在运行则直接复用（避免重复拉起子进程）
        if let Ok(info) = self.info.lock() {
            if info.running && info.port > 0 && port_open(info.port) {
                return Ok(info.clone());
            }
        }
        let port = free_port();
        let token = random_token();
        // 数据目录：打包模式落用户数据目录（AppData），开发模式沿用源码内 engine/data
        let data_dir = if Self::bundled_engine(resource_dir).is_some() {
            data_root.to_path_buf()
        } else {
            root.join("engine").join("data")
        };
        std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;

        let (program, args): (std::path::PathBuf, Vec<String>) =
            if let Some(exe) = Self::bundled_engine(resource_dir) {
                (
                    exe.clone(),
                    vec![
                        "--host".into(),
                        "127.0.0.1".into(),
                        "--port".into(),
                        port.to_string(),
                        "--log-level".into(),
                        "warning".into(),
                    ],
                )
            } else {
                let python = find_python(root)?;
                (
                    python.clone(),
                    vec![
                        "-m".into(),
                        "uvicorn".into(),
                        "engine.app.main:app".into(),
                        "--host".into(),
                        "127.0.0.1".into(),
                        "--port".into(),
                        port.to_string(),
                        "--log-level".into(),
                        "warning".into(),
                    ],
                )
            };
        let mut cmd = Command::new(&program);
        cmd.args(&args)
            .env("MANGJU_LOCAL_TOKEN", &token)
            .env("MANGJU_DATA_DIR", &data_dir.to_string_lossy().to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        // Windows 下不弹出黑色控制台窗口
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = cmd
            .spawn()
            .map_err(|e| format!("启动引擎失败：{}（{}）", e, program.display()))?;
        // 轮询端口，最长 20 秒
        let mut ready = false;
        for _ in 0..80 {
            if port_open(port) {
                ready = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        if !ready {
            let _ = child.kill();
            return Err(format!(
                "引擎 20 秒内未就绪。请检查 {} 与依赖安装（pip install -r engine/requirements.txt）",
                program.display()
            ));
        }
        let mut guard = self.child.lock().map_err(|e| e.to_string())?;
        *guard = Some(child);
        let info = EngineInfo {
            running: true,
            port,
            token,
            base_url: format!("http://127.0.0.1:{}", port),
            error: None,
        };
        *self.info.lock().map_err(|e| e.to_string())? = info.clone();
        Ok(info)
    }
    pub fn stop(&self) -> Result<(), String> {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
        if let Ok(mut info) = self.info.lock() {
            info.running = false;
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn start_then_stop_engine() {
        let root = Path::new("../..").canonicalize().unwrap();
        // 没有 Python 虚拟环境的机器跳过（不影响核心逻辑覆盖）
        if find_python(&root).is_err() {
            eprintln!("跳过：未找到 .venv，无法执行进程管理实测");
            return;
        }
        let state = EngineState::default();
        let info = state.start(&root).expect("引擎应能拉起");
        assert!(info.running, "启动后应为运行态");
        assert!(info.port > 0, "应分配随机端口");
        assert!(port_open(info.port), "端口应可连接");
        assert_eq!(info.base_url, format!("http://127.0.0.1:{}", info.port));
        assert_eq!(info.token.len(), 64, "令牌应为 64 位十六进制");
        state.stop().expect("引擎应能停止");
        assert!(!state.info().running, "停止后应为非运行态");
    }
    #[test]
    fn token_is_unique() {
        assert_ne!(random_token(), random_token());
    }
}
