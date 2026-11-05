"""确定性 stub Provider：本地可跑全链路，供开发、测试与设备联调注入故障。

故障注入（供真机/集成测试）：
- 音频字节以 __unavailable__ 开头 → 503 generation_unavailable
- 音频字节以 __silence__ 开头 → 422 speech_unrecognized
- 识别文本含“不支持” → 422 content_not_supported
- 生成输入 content.name 含“失败” → generation_failed
"""

from __future__ import annotations

import hashlib

from .base import (
    ASRProvider, GenerationProvider,
    ContentNotSupported, GenerationFailed, GenerationUnavailable, SpeechUnrecognized,
)

from ..resources import FEEDBACK_RESOURCE

__all__ = ["StubASR", "StubGeneration", "FEEDBACK_RESOURCE"]

_THEMES = [
    ("熬夜", "最后一条", "害怕今天结束，总想再留用户一会儿",
     "它会不断追加小任务；玩家需要忍住不再回应"),
    ("拖延", "明天再说兽", "把一切都推到明天，语气永远理直气壮",
     "它会给出诱人的拖延理由；玩家要在倒计时内连续拒绝"),
    ("零食", "一口就好怪", "嘴上只吃一口，手上永远停不下来",
     "它反复递出零食；玩家要长按拒绝直到它死心"),
    ("刷手机", "再刷五分钟", "时间感扭曲，五分钟等于一小时",
     "它不断弹出“下一条”；玩家要忍住不点"),
    ("久坐", "椅子黏黏精", "最擅长把人黏在椅子上",
     "它用舒服诱惑玩家；玩家要及时起身的节奏操作"),
]

_FACES = ["round", "square", "bean"]
_EYES = ["sleepy", "wide", "side", "dot"]
_MOUTHS = ["small", "grin", "flat", "open"]
_STYLES = ["drowsy", "jittery", "still", "bouncy"]
_PALETTES = [
    ["#18243A", "#FFD166"], ["#3B1F2B", "#EF476F"],
    ["#0F2E1D", "#8AC926"], ["#1B2A4A", "#4CC9F0"],
]


def _digest(seed: str) -> int:
    return int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)


class StubASR:
    """把音频字节确定性映射成一句“识别文本”，模拟不同输入。"""

    def transcribe(self, audio: bytes, locale: str) -> str:
        if audio.startswith(b"__unavailable__"):
            raise GenerationUnavailable("stub: 识别服务不可用")
        if audio.startswith(b"__silence__"):
            raise SpeechUnrecognized("stub: 未获得可用语义")
        idx = _digest(audio.hex()) % len(_THEMES)
        return f"stub识别：我总想改掉的坏习惯是{_THEMES[idx][0]}"


class StubGeneration:
    """由文本确定性产出候选与规则包；产出必过服务器端收紧校验。"""

    def make_candidate_content(self, text: str) -> dict:
        if "不支持" in text:
            raise ContentNotSupported("stub: 输入主题不支持")
        idx = _digest(text) % len(_THEMES)
        tag, name, personality, gameplay = _THEMES[idx]
        return {
            "name": name,
            "personality": personality,
            "gameplay_summary": gameplay,
            "theme_tags": [tag],
        }

    def make_game_and_avatar(self, content: dict) -> tuple[dict, dict]:
        if "失败" in content.get("name", ""):
            raise GenerationFailed("stub: 生成失败注入")
        seed = _digest(content["name"] + content["personality"])
        avatar = {
            "face": _FACES[seed % 3],
            "eyes": _EYES[(seed >> 3) % 4],
            "mouth": _MOUTHS[(seed >> 5) % 4],
            "palette": _PALETTES[(seed >> 7) % len(_PALETTES)],
            "motion_style": _STYLES[(seed >> 9) % 4],
        }
        duration = 60 + seed % 31  # 60—90
        threshold = 3
        game = {
            "duration_sec": duration,
            "initial_node": "invite",
            "variables": [{"name": "refusals", "type": "int", "initial": 0}],
            "nodes": [
                {
                    "id": "invite",
                    "title": content["name"],
                    "instruction": "长按拒绝它的请求；点按等于接受",
                    "on_enter": [
                        {"op": "avatar.expression", "value": "pleading"},
                        {"op": "audio.play", "resource_id": "feedback"},
                    ],
                    "transitions": [
                        {
                            "event": "touch.long_press",
                            "to": "plead",
                            "actions": [
                                {"op": "var.increment", "name": "refusals", "value": 1},
                            ],
                        },
                        {"event": "touch.tap", "to": "plead", "actions": []},
                    ],
                },
                {
                    "id": "plead",
                    "title": content["name"],
                    "instruction": "坚持住，继续长按拒绝",
                    "on_enter": [{"op": "avatar.motion", "value": "breathe"}],
                    "transitions": [
                        {
                            "event": "touch.long_press",
                            "condition": {
                                "left": {"var": "refusals"},
                                "op": "gte",
                                "right": threshold,
                            },
                            "to": "freed",
                            "actions": [{"op": "game.end", "outcome": "escaped"}],
                        },
                        {
                            "event": "touch.long_press",
                            "to": "plead",
                            "actions": [
                                {"op": "var.increment", "name": "refusals", "value": 1},
                            ],
                        },
                        {"event": "touch.tap", "to": "plead", "actions": []},
                    ],
                },
                {
                    "id": "freed",
                    "title": "破解成功",
                    "instruction": "你守住了自己的边界",
                    "on_enter": [
                        {"op": "avatar.expression", "value": "happy"},
                        {"op": "game.end", "outcome": "escaped"},
                    ],
                    "transitions": [],
                },
                {
                    "id": "taken",
                    "title": "被带跑了",
                    "instruction": "下次再来",
                    "on_enter": [
                        {"op": "avatar.expression", "value": "smug"},
                        {"op": "game.end", "outcome": "carried_away"},
                    ],
                    "transitions": [],
                },
            ],
        }
        return game, avatar
