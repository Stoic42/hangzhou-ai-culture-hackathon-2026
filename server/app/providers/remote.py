"""真实 ASR Provider 占位与 local 占位；远程 LLM 经 openai_llm.py 真实接入。

凭证只从环境变量读取，不写入仓库与日志。
- remote ASR：读取 ASR_REMOTE_URL，真实接入待后续任务，当前抛 GenerationUnavailable。
- local ASR：本地识别任务 2 再接入，装配占位 Provider，调用期抛 GenerationUnavailable。
- remote LLM：OpenAILLMGeneration（OpenAI 兼容接口，凭证 OPENAI_API_KEY）。
"""

from __future__ import annotations

import os

from .base import GenerationUnavailable
from .openai_llm import OpenAILLMGeneration


class RemoteASR:
    def __init__(self) -> None:
        self._url = os.environ.get("ASR_REMOTE_URL")

    def transcribe(self, audio: bytes, locale: str) -> str:
        if not self._url:
            raise GenerationUnavailable("remote ASR 未配置 ASR_REMOTE_URL")
        # TODO：接真实 ASR 服务；注意音频不得落盘、不入日志。
        raise GenerationUnavailable("remote ASR 尚未实现")


class LocalASR:
    """本地 ASR 占位（任务 2 接入）：装配不失败，transcribe 调用期抛
    GenerationUnavailable（对应契约 503 generation_unavailable）。"""

    def transcribe(self, audio: bytes, locale: str) -> str:
        raise GenerationUnavailable("local ASR 未实现")


class RemoteGeneration(OpenAILLMGeneration):
    """remote LLM 即 OpenAI 兼容适配器（见 openai_llm.py）。"""
