"""服务器配置：全部经环境变量覆盖，凭证与运维口令不写入仓库。

环境变量：
- SERVER_DB_PATH：SQLite 文件路径，默认 server/data/server.db
- SERVER_PROVIDER：批量 Provider 开关（向后兼容），stub（默认）| remote；
  会被 SERVER_ASR_PROVIDER / SERVER_LLM_PROVIDER 单独覆盖
- SERVER_ASR_PROVIDER：ASR 开关，stub（默认，取 SERVER_PROVIDER）| local | remote
- SERVER_LLM_PROVIDER：LLM（候选 + 规则包生成）开关，stub（默认，取 SERVER_PROVIDER）| remote
- SERVER_RATE_LIMIT_PER_MIN：候选与生成接口的每 IP 每分钟限流阈值，默认 10
- SERVER_ADMIN_TOKEN：管理后台口令，默认空串表示后台拒绝访问
- SERVER_BASE_URL：对外基础 URL，用于 manifest_url，默认 http://127.0.0.1:8000
- OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL / OPENAI_TIMEOUT_SEC：OpenAI 兼容 LLM 配置
- ASR_REMOTE_URL：remote ASR 服务地址（仍为占位）
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
    provider: str  # SERVER_PROVIDER 批量设置（向后兼容展示用）
    asr_provider: str
    llm_provider: str
    rate_limit_per_min: int
    admin_token: str
    base_url: str
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_sec: float = 60.0
    candidate_ttl_sec: int = 86400
    audio_max_bytes: int = 2 * 1024 * 1024
    audio_max_duration_sec: int = 30


@lru_cache
def get_settings() -> Settings:
    batch = os.environ.get("SERVER_PROVIDER", "stub")
    return Settings(
        db_path=os.environ.get(
            "SERVER_DB_PATH", str(_REPO_ROOT / "server" / "data" / "server.db")
        ),
        provider=batch,
        asr_provider=os.environ.get("SERVER_ASR_PROVIDER", batch),
        llm_provider=os.environ.get("SERVER_LLM_PROVIDER", batch),
        rate_limit_per_min=int(os.environ.get("SERVER_RATE_LIMIT_PER_MIN", "10")),
        admin_token=os.environ.get("SERVER_ADMIN_TOKEN", ""),
        base_url=os.environ.get("SERVER_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        openai_base_url=os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        # 解析失败自然抛 ValueError，启动期即暴露配置错误
        openai_timeout_sec=float(os.environ.get("OPENAI_TIMEOUT_SEC", "60")),
    )


def reset_settings_cache() -> None:
    """测试专用：改环境变量后清缓存。"""
    get_settings.cache_clear()
