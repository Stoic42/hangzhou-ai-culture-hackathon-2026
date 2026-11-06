"""Provider 统一装配：按 Settings 的 asr_provider / llm_provider 开关返回 (asr, generation)。

- stub：确定性假数据（默认，本地可跑全链路）
- remote：真实服务（LLM 为 OpenAI 兼容接口；ASR 仍为占位）
- local：本地 ASR 占位（任务 2 接入），选择即抛 GenerationUnavailable
"""

from __future__ import annotations

from ..config import Settings
from .base import ASRProvider, GenerationProvider, GenerationUnavailable
from .remote import RemoteASR, RemoteGeneration
from .stub import StubASR, StubGeneration

__all__ = ["build_providers"]


def build_providers(settings: Settings) -> tuple[ASRProvider, GenerationProvider]:
    """按开关装配 (asr, generation)；未知开关抛 ValueError（配置错误）。"""
    if settings.asr_provider == "stub":
        asr: ASRProvider = StubASR()
    elif settings.asr_provider == "remote":
        asr = RemoteASR()
    elif settings.asr_provider == "local":
        # 本地 ASR 任务 2 接入，选择即报不可用占位
        raise GenerationUnavailable("local ASR 未实现")
    else:
        raise ValueError(f"未知 SERVER_ASR_PROVIDER: {settings.asr_provider!r}")

    if settings.llm_provider == "stub":
        generation: GenerationProvider = StubGeneration()
    elif settings.llm_provider == "remote":
        generation = RemoteGeneration()
    else:
        raise ValueError(f"未知 SERVER_LLM_PROVIDER: {settings.llm_provider!r}")

    return asr, generation
