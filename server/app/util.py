"""共享小工具：ID 生成、content_hash 计算、限流器。"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def content_hash_of(content: dict) -> str:
    """content 四字段规范化 JSON 的 SHA-256（UTF-8、key 排序、无空格）。

    该定义与设备侧对齐的依据，改动必须同步设备与 shared 文档。
    """
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class RateLimiter:
    """每 IP 滑动窗口限流，只作用于候选与生成接口。"""

    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window = [t for t in self._hits.get(key, []) if now - t < 60.0]
            if not window:
                # 窗口已空则顺手删除条目，避免 key 无界增长
                self._hits.pop(key, None)
            else:
                self._hits[key] = window
            if len(window) >= self._per_minute:
                return False
            window.append(now)
            self._hits[key] = window
            return True
