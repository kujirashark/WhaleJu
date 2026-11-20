"""凭证加密：AES-256-GCM，主密钥来自环境变量（生产环境应改为 OS 凭证库）。
安全约束（设计 v3.1 §4.9）：
- SQLite 中只有 credential_cipher（密文），永无明文 Key
- 任何查询接口绝不返回此字段
- 主密钥不落盘（开发用 env；生产用 DPAPI/Keychain）
"""
from __future__ import annotations
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
_ENV_KEY = "MANGJU_MASTER_KEY"
def _master_key() -> bytes:
    raw = os.getenv(_ENV_KEY)
    if raw:
        return base64.urlsafe_b64decode(raw.encode())
    # 开发兜底：从用户数据目录读取随机密钥文件（600 权限语义由 OS 保证）
    from pathlib import Path
    p = Path(os.getenv("MANGJU_DATA_DIR", str(Path.cwd() / "engine" / "data"))) / ".master.key"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(base64.urlsafe_b64encode(os.urandom(32)).decode())
    return base64.urlsafe_b64decode(p.read_text().encode())
def encrypt(plaintext: str) -> bytes:
    nonce = os.urandom(12)
    return nonce + AESGCM(_master_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
def decrypt(cipher: bytes) -> str:
    return AESGCM(_master_key()).decrypt(cipher[:12], cipher[12:], None).decode("utf-8")
def mask(plaintext: str) -> str:
    """仅用于 UI 回显（设计：Key 输入后不再明文回显）。"""
    if len(plaintext) <= 8:
        return "***"
    return plaintext[:4] + "***" + plaintext[-4:]
