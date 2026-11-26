"""安全相关工具：口令哈希、会话令牌、登录失败限流。

口令使用 PBKDF2-HMAC-SHA256（20 万次迭代 + 16 字节随机盐），
会话令牌使用 secrets 生成，落库前先做 SHA-256，避免数据库泄露即可直接冒用。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time

PBKDF2_ITERATIONS = 200_000
SESSION_COOKIE = "fit_session"


def hash_password(password: str) -> str:
    """生成 `pbkdf2_sha256$迭代次数$盐$哈希` 格式的口令摘要。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """恒定时间比较口令摘要，格式异常直接判失败。"""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    """生成 256 位随机会话令牌。"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """会话令牌入库前做摘要，防止直接以明文 token 访问数据库即可冒用。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginThrottle:
    """简单的内存登录限流：同一账号连续失败 5 次后锁定 60 秒。

    单进程部署下的低成本防护；多进程/多实例场景应换成 Redis 计数。
    """

    MAX_FAILURES = 5
    LOCK_SECONDS = 60

    def __init__(self) -> None:
        self._state: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _key(self, username: str) -> str:
        return username.strip().lower()

    def is_locked(self, username: str) -> bool:
        with self._lock:
            count, locked_until = self._state.get(self._key(username), (0, 0.0))
            if count >= self.MAX_FAILURES and time.time() < locked_until:
                return True
            if count >= self.MAX_FAILURES:
                self._state.pop(self._key(username), None)
            return False

    def register_failure(self, username: str) -> None:
        with self._lock:
            key = self._key(username)
            count, _ = self._state.get(key, (0, 0.0))
            count += 1
            self._state[key] = (count, time.time() + self.LOCK_SECONDS)

    def reset(self, username: str) -> None:
        with self._lock:
            self._state.pop(self._key(username), None)


throttle = LoginThrottle()
