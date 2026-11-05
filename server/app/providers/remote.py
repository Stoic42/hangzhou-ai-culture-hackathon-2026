"""真实 ASR/LLM Provider 占位：读取环境变量，未配置即报不可用。

凭证只从环境变量读取，不写入仓库与日志。接入真实服务时实现
transcribe / make_candidate_content / make_game_and_avatar 三个方法，
并保证输出经 server/app/generation/validate.py 的全量校验。
"""

from __future__ import annotations

import os

from .base import GenerationUnavailable


class RemoteASR:
    def __init__(self) -> None:
        self._url = os.environ.get("ASR_REMOTE_URL")

    def transcribe(self, audio: bytes, locale: str) -> str:
        if not self._url:
            raise GenerationUnavailable("remote ASR 未配置 ASR_REMOTE_URL")
        # TODO(11-7前)：接真实ASR服务；注意音频不得落盘、不入日志。
        raise GenerationUnavailable("remote ASR 尚未实现")


class RemoteGeneration:
    def __init__(self) -> None:
        self._url = os.environ.get("LLM_REMOTE_URL")
        self._key = os.environ.get("LLM_REMOTE_KEY")

    def _ensure(self) -> None:
        if not (self._url and self._key):
            raise GenerationUnavailable("remote LLM 未配置 LLM_REMOTE_URL/LLM_REMOTE_KEY")

    def make_candidate_content(self, text: str) -> dict:
        self._ensure()
        raise GenerationUnavailable("remote LLM 候选生成尚未实现")

    def make_game_and_avatar(self, content: dict) -> tuple[dict, dict]:
        self._ensure()
        raise GenerationUnavailable("remote LLM 规则生成尚未实现")


def build_providers(name: str):
    """按配置返回 (asr, generation)。"""
    if name == "stub":
        from .stub import StubASR, StubGeneration
        return StubASR(), StubGeneration()
    return RemoteASR(), RemoteGeneration()
