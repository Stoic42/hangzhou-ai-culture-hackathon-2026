"""Provider 统一装配：按 Settings 的 asr_provider / llm_provider 开关返回 (asr, generation)。

- stub：确定性假数据（默认，本地可跑全链路）
- remote：真实服务（LLM 为 OpenAI 兼容接口；ASR 仍为占位）
- local：本地 sherpa-onnx ASR（providers/local_asr.py），模型目录缺失或
  依赖未安装时装配不失败，请求期抛 GenerationUnavailable
"""

from __future__ import annotations

from ..config import Settings
from .base import ASRProvider, GenerationProvider
from .local_asr import SherpaLocalASR
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
        asr = SherpaLocalASR(settings)
    else:
        raise ValueError(f"未知 SERVER_ASR_PROVIDER: {settings.asr_provider!r}")

    if settings.llm_provider == "stub":
        generation: GenerationProvider = StubGeneration()
    elif settings.llm_provider == "remote":
        generation = RemoteGeneration(settings)
    else:
        raise ValueError(f"未知 SERVER_LLM_PROVIDER: {settings.llm_provider!r}")

    return asr, generation
