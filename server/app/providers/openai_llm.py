"""OpenAI 兼容的远程 LLM 适配器：真实实现候选生成与规则包生成。

经 POST {OPENAI_BASE_URL}/chat/completions 调用，response_format 固定为
json_object。凭证只从环境变量读取，不写入仓库与日志：

- OPENAI_BASE_URL：默认 https://api.openai.com/v1（可指向任意 OpenAI 兼容端点）
- OPENAI_API_KEY：必需，缺失即 GenerationUnavailable
- OPENAI_MODEL：默认 gpt-4o-mini
- OPENAI_TIMEOUT_SEC：默认 60

重试策略：解析/校验失败时把上一次的错误反馈给模型重试，最多 2 次重试
（共 3 次调用）；网络/超时/5xx 直接抛 GenerationUnavailable，不做重试。
"""

from __future__ import annotations

import json
import os

import httpx

from ..generation.validate import validate_for_publish
from ..library.publish import build_manifest
from .base import ContentNotSupported, GenerationFailed, GenerationUnavailable

MAX_ATTEMPTS = 3  # 首次调用 + 2 次重试


def _post_chat(messages: list[dict], *, base_url: str, api_key: str,
               model: str, timeout: float) -> dict:
    """POST /chat/completions 并返回响应 JSON。

    网络错误、超时、5xx 与非法响应体统一抛 GenerationUnavailable。
    独立成模块级函数，测试可 monkeypatch 注入假响应，绝不打真实网络。
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise GenerationUnavailable(f"LLM 请求失败: {type(exc).__name__}") from exc
    if resp.status_code >= 400:
        raise GenerationUnavailable(f"LLM 返回 HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise GenerationUnavailable("LLM 响应不是合法 JSON") from exc


def _extract_content(response: dict) -> str:
    """从 chat.completions 响应里取首个 message.content；结构异常视为不可用。"""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GenerationUnavailable("LLM 响应缺少 choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise GenerationUnavailable("LLM 响应内容为空")
    return content


# ---------------------------------------------------------------------------
# prompt 构造
# ---------------------------------------------------------------------------

_CANDIDATE_SYSTEM = """你是「当代妖怪收容所」的主题设计师。这个装置把用户说出的\
一句坏习惯，转生成一个可爱的妖怪搭子（元信息）。用户会说出一句描述坏习惯的话，\
你要把它变成一个让人会心一笑、可以做成小游戏的妖怪。

只输出一个 JSON 对象，恰好四个字段：
- "name"：妖怪名字，不超过 8 个汉字，俏皮可爱；
- "personality"：一句话性格，不超过 40 字；
- "gameplay_summary"：玩法简介，不超过 60 字，必须说清玩家要做什么、怎么算赢；
- "theme_tags"：1 到 4 个简短主题标签组成的数组。

安全红线：如果输入涉及暴力、色情、政治敏感、自伤、仇恨或任何不适合做成\
轻松小游戏的主题，不要强行生成，只输出 {"unsupported": true}。
除此之外必须给出四个字段，不要输出其他文字。"""

_GAME_SYSTEM = """你是「当代妖怪收容所」的关卡设计师。已确认的妖怪搭子元信息（content）\
会逐字给你，你要为它设计一个 60—90 秒的触控小游戏规则包和它的虚拟形象。\
玩法要呼应 content 的主题与性格，不要照搬示例。

只输出一个 JSON 对象，恰好两个键："avatar" 与 "game"。全部取值必须来自下面的\
封闭值域与硬约束，任何超出都会被判非法：

avatar 约束：
- face ∈ round | square | bean
- eyes ∈ sleepy | wide | side | dot
- mouth ∈ small | grin | flat | open
- motion_style ∈ drowsy | jittery | still | bouncy
- palette：2—4 个 #RRGGBB 颜色

game 约束：
- duration_sec：60—90 的整数
- variables：不超过 4 个，每项 type 只能是 "int"，initial 是整数
- nodes：不超过 16 个；每节点 transitions 不超过 8 条；on_enter 与 transitions 里的\
actions 每个列表不超过 6 个动作
- 事件白名单：game.start、touch.tap、touch.long_press、touch.swipe、timer.elapsed
- 动作白名单与取值：
  - avatar.expression，value ∈ neutral | pleading | happy | smug | anxious | sleepy | angry
  - avatar.motion，value ∈ still | breathe | shake | bounce | nod
  - audio.play，resource_id 只能是 "feedback"
  - timer.start，seconds 为正整数
  - var.set / var.increment，name 必须是已声明的变量，value 是整数
  - game.end，outcome ∈ escaped | carried_away
- 每个节点必有非空 id、title、instruction；initial_node 必须指向存在的节点
- condition（可选）形如 {"left": {"var": "已声明变量"} 或 {"remaining_sec": true},\
"op": "eq|neq|gt|gte|lt|lte", "right": 整数常量}
- 必须同时存在 escaped 与 carried_away 两个结局节点（game.end），且从 initial_node\
可达 escaped（carried_away 由全局超时强制，不考核可达性）

小型合法示例（结构参考，内容不要照抄）：
{
  "avatar": {
    "face": "round", "eyes": "sleepy", "mouth": "small",
    "motion_style": "drowsy", "palette": ["#18243A", "#FFD166"]
  },
  "game": {
    "duration_sec": 75,
    "initial_node": "invite",
    "variables": [{"name": "refusals", "type": "int", "initial": 0}],
    "nodes": [
      {
        "id": "invite", "title": "邀请", "instruction": "长按拒绝它的请求",
        "on_enter": [{"op": "avatar.expression", "value": "pleading"}],
        "transitions": [
          {"event": "touch.long_press", "to": "plead",
           "actions": [{"op": "var.increment", "name": "refusals", "value": 1}]},
          {"event": "touch.tap", "to": "invite", "actions": []}
        ]
      },
      {
        "id": "plead", "title": "恳求", "instruction": "继续长按拒绝",
        "on_enter": [],
        "transitions": [
          {"event": "touch.long_press",
           "condition": {"left": {"var": "refusals"}, "op": "gte", "right": 3},
           "to": "freed", "actions": []},
          {"event": "touch.long_press", "to": "plead",
           "actions": [{"op": "var.increment", "name": "refusals", "value": 1}]}
        ]
      },
      {
        "id": "freed", "title": "破解成功", "instruction": "你守住了边界",
        "on_enter": [
          {"op": "avatar.expression", "value": "happy"},
          {"op": "game.end", "outcome": "escaped"}
        ],
        "transitions": []
      },
      {
        "id": "taken", "title": "被带跑了", "instruction": "下次再来",
        "on_enter": [
          {"op": "avatar.expression", "value": "smug"},
          {"op": "game.end", "outcome": "carried_away"}
        ],
        "transitions": []
      }
    ]
  }
}"""


def _candidate_messages(text: str, feedback: str | None) -> list[dict]:
    user = f"用户的坏习惯描述：{text}"
    if feedback:
        user += f"\n\n上一次你的输出有问题，请修正后重新输出合法 JSON：{feedback}"
    return [{"role": "system", "content": _CANDIDATE_SYSTEM},
            {"role": "user", "content": user}]


def _game_messages(content: dict, feedback: str | None) -> list[dict]:
    user = ("搭子元信息（逐字使用，不得修改）：\n"
            + json.dumps(content, ensure_ascii=False))
    if feedback:
        user += f"\n\n上一次你输出的规则包未通过校验，请修正后重新输出合法 JSON：\n{feedback}"
    return [{"role": "system", "content": _GAME_SYSTEM},
            {"role": "user", "content": user}]


# ---------------------------------------------------------------------------
# 输出解析与本地校验
# ---------------------------------------------------------------------------

def _validate_candidate(data: object) -> str | None:
    """校验候选四字段；返回错误描述或 None。"""
    if not isinstance(data, dict):
        return "输出必须是 JSON 对象"
    extra = set(data) - {"name", "personality", "gameplay_summary", "theme_tags"}
    if extra:
        return f"不允许出现额外字段: {sorted(extra)}"
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return "name 必须是非空字符串"
    if len(name) > 8:
        return f"name 超过 8 个汉字: {name!r}"
    personality = data.get("personality")
    if not isinstance(personality, str) or not personality.strip():
        return "personality 必须是非空字符串"
    if len(personality) > 40:
        return f"personality 超过 40 字: {personality!r}"
    summary = data.get("gameplay_summary")
    if not isinstance(summary, str) or not summary.strip():
        return "gameplay_summary 必须是非空字符串"
    if len(summary) > 60:
        return f"gameplay_summary 超过 60 字: {summary!r}"
    tags = data.get("theme_tags")
    if (not isinstance(tags, list) or not 1 <= len(tags) <= 4
            or not all(isinstance(t, str) and t.strip() for t in tags)):
        return "theme_tags 必须是 1—4 个非空字符串数组"
    return None


def _parse_candidate(raw: str) -> tuple[dict | None, str | None, bool]:
    """解析候选输出，返回 (data, 错误信息, 是否 unsupported)。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return None, f"返回内容不是合法 JSON: {raw[:120]!r}", False
    if isinstance(data, dict) and data.get("unsupported") is True:
        return None, None, True
    error = _validate_candidate(data)
    return (None, error, False) if error else (data, None, False)


# ---------------------------------------------------------------------------
# Provider 实现
# ---------------------------------------------------------------------------

class OpenAILLMGeneration:
    """OpenAI 兼容端点上的真实 LLM 生成器。"""

    def __init__(self) -> None:
        self._base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._timeout = float(os.environ.get("OPENAI_TIMEOUT_SEC", "60"))

    def _ensure(self) -> None:
        if not self._api_key:
            raise GenerationUnavailable("remote LLM 未配置 OPENAI_API_KEY")

    def _call(self, messages: list[dict]) -> str:
        self._ensure()
        response = _post_chat(messages, base_url=self._base_url, api_key=self._api_key,
                              model=self._model, timeout=self._timeout)
        return _extract_content(response)

    def make_candidate_content(self, text: str) -> dict:
        feedback: str | None = None
        for _ in range(MAX_ATTEMPTS):
            raw = self._call(_candidate_messages(text, feedback))
            data, error, unsupported = _parse_candidate(raw)
            if unsupported:
                raise ContentNotSupported("LLM 判定输入主题不支持")
            if error is None:
                return data  # type: ignore[return-value]
            feedback = error
        raise GenerationFailed(f"候选生成失败: {feedback}")

    def make_game_and_avatar(self, content: dict) -> tuple[dict, dict]:
        """content 逐字作为上下文传入且不做任何修改（契约 4.2）。"""
        content_json = json.dumps(content, ensure_ascii=False)
        feedback: str | None = None
        for _ in range(MAX_ATTEMPTS):
            raw = self._call(_game_messages(content, feedback))
            try:
                data = json.loads(raw)
            except ValueError:
                feedback = f"返回内容不是合法 JSON: {raw[:120]!r}"
                continue
            if not isinstance(data, dict):
                feedback = "输出必须是 JSON 对象"
                continue
            avatar = data.get("avatar")
            game = data.get("game")
            if not isinstance(avatar, dict) or not isinstance(game, dict):
                feedback = "输出必须恰好包含 avatar 与 game 两个对象"
                continue
            # 用发布校验器做全量校验（buddy_id/content_hash 用占位值即可）
            manifest = build_manifest("buddy_pending", json.loads(content_json),
                                      game, avatar)
            errors = validate_for_publish(manifest)
            if errors:
                feedback = "；".join(errors[:8])
                continue
            return game, avatar
        raise GenerationFailed(f"规则包生成失败: {feedback}")
