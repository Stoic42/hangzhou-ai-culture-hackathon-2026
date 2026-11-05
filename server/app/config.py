"""服务器配置：全部经环境变量覆盖，凭证与运维口令不写入仓库。

环境变量：
- SERVER_DB_PATH：SQLite 文件路径，默认 server/data/server.db
- SERVER_PROVIDER：stub（默认，确定性假数据）| remote（真实 ASR/LLM，占位）
- SERVER_RATE_LIMIT_PER_MIN：候选与生成接口的每 IP 每分钟限流阈值，默认 10
- SERVER_ADMIN_TOKEN：管理后台口令，默认空串表示后台拒绝访问
- SERVER_BASE_URL：对外基础 URL，用于 manifest_url，默认 http://127.0.0.1:8000
- ASR_REMOTE_URL / LLM_REMOTE_URL / LLM_REMOTE_KEY：remote Provider 占位配置
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    db_path: str
    provider: str
    rate_limit_per_min: int
    admin_token: str
    base_url: str
    candidate_ttl_sec: int = 86400
    audio_max_bytes: int = 2 * 1024 * 1024
    audio_max_duration_sec: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings(
        db_path=os.environ.get(
            "SERVER_DB_PATH", str(_REPO_ROOT / "server" / "data" / "server.db")
        ),
        provider=os.environ.get("SERVER_PROVIDER", "stub"),
        rate_limit_per_min=int(os.environ.get("SERVER_RATE_LIMIT_PER_MIN", "10")),
        admin_token=os.environ.get("SERVER_ADMIN_TOKEN", ""),
        base_url=os.environ.get("SERVER_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
    )


def reset_settings_cache() -> None:
    """测试专用：改环境变量后清缓存。"""
    get_settings.cache_clear()
