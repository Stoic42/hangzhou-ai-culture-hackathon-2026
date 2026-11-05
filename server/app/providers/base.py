"""生成链路 Provider 接口：ASR（语音转写）与生成（候选 / 规则包）。

默认实现为确定性 stub；真实服务经 remote.py 占位接入，凭证走环境变量。
"""

from __future__ import annotations

from typing import Protocol


class GenerationUnavailable(Exception):
    """识别或生成服务不可用（对应契约 503 generation_unavailable）。"""


class SpeechUnrecognized(Exception):
    """未获得可用语义（对应契约 422 speech_unrecognized）。"""


class ContentNotSupported(Exception):
    """输入无法转成安全、可玩的搭子主题（对应契约 422 content_not_supported）。"""


class GenerationFailed(Exception):
    """具体逻辑生成失败（生成任务 error_code=generation_failed）。"""


class ASRProvider(Protocol):
    def transcribe(self, audio: bytes, locale: str) -> str:
        """音频字节 → 识别文本。音频字节用后由调用方丢弃，不落盘。"""


class GenerationProvider(Protocol):
    def make_candidate_content(self, text: str) -> dict:
        """识别文本 → 候选 content 四字段（name/personality/gameplay_summary/theme_tags）。"""

    def make_game_and_avatar(self, content: dict) -> tuple[dict, dict]:
        """已确认 content → (game, avatar)。content 逐字不变，不得修改。"""
