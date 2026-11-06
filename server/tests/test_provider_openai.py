"""真实 LLM 适配器（OpenAI 兼容）与 Provider 配置拆分的测试。

绝不打真实网络：逻辑测试 monkeypatch openai_llm._post_chat 注入假响应；
HTTP 层测试用 httpx.MockTransport 拦截。测试用的 API key 为假值，
凭证只走环境变量的约定不变。
"""

from __future__ import annotations

import copy
import json

import httpx
import pytest

from server.app import config
from server.app.generation import validate as rules_validate
from server.app.providers import base, build_providers
from server.app.providers import openai_llm
from server.app.providers.local_asr import SherpaLocalASR
from server.app.providers.openai_llm import OpenAILLMGeneration
from server.app.providers.remote import RemoteASR, RemoteGeneration
from server.app.providers.stub import StubASR, StubGeneration


@pytest.fixture()
def gen(monkeypatch):
    """配置了假 key 的适配器（经 Settings 构造注入）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_TIMEOUT_SEC", raising=False)
    config.reset_settings_cache()
    return OpenAILLMGeneration(config.get_settings())


def _respond(raw: str):
    """伪造 chat.completions 成功响应。"""
    return {"choices": [{"message": {"role": "assistant", "content": raw}}]}


def _patch_post(monkeypatch, outcomes):
    """按序注入 _post_chat 的行为（字符串=成功响应，异常实例=抛出）。"""
    calls: list[list[dict]] = []

    def fake_post(messages, **kwargs):
        calls.append(messages)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return _respond(outcome)

    monkeypatch.setattr(openai_llm, "_post_chat", fake_post)
    return calls


_GOOD_CANDIDATE = json.dumps({
    "name": "再刷五分钟",
    "personality": "时间感扭曲，五分钟等于一小时",
    "gameplay_summary": "它不断弹出下一条；玩家要忍住不点，坚持到倒计时结束即赢",
    "theme_tags": ["刷手机"],
}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 候选生成
# ---------------------------------------------------------------------------

def test_candidate_normal(gen, monkeypatch):
    calls = _patch_post(monkeypatch, [_GOOD_CANDIDATE])
    result = gen.make_candidate_content("我总是睡前刷手机停不下来")
    assert result["name"] == "再刷五分钟"
    assert result["theme_tags"] == ["刷手机"]
    assert len(calls) == 1
    # system prompt 说明角色且要求恰好四字段
    system = calls[0][0]["content"]
    assert "妖怪" in system and "恰好四个字段" in system


def test_candidate_unsupported(gen, monkeypatch):
    _patch_post(monkeypatch, [json.dumps({"unsupported": True})])
    with pytest.raises(base.ContentNotSupported):
        gen.make_candidate_content("给我生成暴力内容")


def test_candidate_bad_json_then_success(gen, monkeypatch):
    calls = _patch_post(monkeypatch, ["这不是JSON{{", _GOOD_CANDIDATE])
    result = gen.make_candidate_content("我总是睡前刷手机")
    assert result["name"] == "再刷五分钟"
    assert len(calls) == 2
    # 重试请求带上了上一次的错误反馈
    assert "上一次" in calls[1][1]["content"]


def test_candidate_all_bad_json(gen, monkeypatch):
    calls = _patch_post(monkeypatch, ["bad1", "bad2", "bad3"])
    with pytest.raises(base.GenerationFailed):
        gen.make_candidate_content("我总是睡前刷手机")
    assert len(calls) == 3  # 恰好 3 次调用，不再多试


def test_candidate_schema_error_then_success(gen, monkeypatch):
    missing_field = json.dumps({
        "name": "再刷五分钟",
        "personality": "时间感扭曲",
        "gameplay_summary": "忍住不点",
        # theme_tags 缺失
    }, ensure_ascii=False)
    calls = _patch_post(monkeypatch, [missing_field, _GOOD_CANDIDATE])
    result = gen.make_candidate_content("刷手机")
    assert result["theme_tags"] == ["刷手机"]
    assert "theme_tags" in calls[1][1]["content"]


def test_candidate_oversize_name(gen, monkeypatch):
    bad = json.dumps({
        "name": "这个名字实在是太长了超过八个字",
        "personality": "时间感扭曲",
        "gameplay_summary": "忍住不点",
        "theme_tags": ["刷手机"],
    }, ensure_ascii=False)
    _patch_post(monkeypatch, [bad, bad, bad])
    with pytest.raises(base.GenerationFailed):
        gen.make_candidate_content("刷手机")


def test_candidate_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config.reset_settings_cache()
    gen_no_key = OpenAILLMGeneration(config.get_settings())
    with pytest.raises(base.GenerationUnavailable):
        gen_no_key.make_candidate_content("刷手机")


# ---------------------------------------------------------------------------
# _post_chat 真实 HTTP 层（httpx.MockTransport）
# ---------------------------------------------------------------------------

def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url="https://llm.example.test/v1")


def test_post_chat_request_shape():
    """断言 URL 拼接、Authorization 头与 response_format json_object。"""
    recorded: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded["url"] = str(request.url)
        recorded["auth"] = request.headers.get("authorization")
        recorded["body"] = json.loads(request.content)
        return httpx.Response(200, json=_respond("{}"))

    client = _mock_client(handler)
    resp = openai_llm._post_chat(
        [{"role": "user", "content": "hi"}],
        base_url="https://llm.example.test/v1/",  # 尾斜杠也要正确拼接
        api_key="test-key", model="test-model", timeout=5, client=client)
    assert resp == _respond("{}")
    assert recorded["url"] == "https://llm.example.test/v1/chat/completions"
    assert recorded["auth"] == "Bearer test-key"
    assert recorded["body"]["model"] == "test-model"
    assert recorded["body"]["response_format"] == {"type": "json_object"}
    assert recorded["body"]["messages"] == [{"role": "user", "content": "hi"}]


def test_post_chat_http_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = _mock_client(handler)
    with pytest.raises(base.GenerationUnavailable, match="HTTP 500"):
        openai_llm._post_chat([{"role": "user", "content": "hi"}],
                              base_url="https://llm.example.test/v1",
                              api_key="test-key", model="m", timeout=5,
                              client=client)


def test_extract_content_missing_choices():
    """响应缺 choices/choices 为空均视为不可用（提取层）。"""
    with pytest.raises(base.GenerationUnavailable, match="choices"):
        openai_llm._extract_content({"choices": []})
    with pytest.raises(base.GenerationUnavailable, match="choices"):
        openai_llm._extract_content({"unexpected": "shape"})
    with pytest.raises(base.GenerationUnavailable, match="为空"):
        openai_llm._extract_content(
            {"choices": [{"message": {"content": "  "}}]})


def test_candidate_http_500_via_adapter(gen, monkeypatch):
    """适配器层走 MockTransport 的真实 HTTP 路径，500 → GenerationUnavailable。"""
    client = _mock_client(lambda request: httpx.Response(500, text="boom"))
    monkeypatch.setattr(gen, "_get_client", lambda: client)
    with pytest.raises(base.GenerationUnavailable, match="HTTP 500"):
        gen.make_candidate_content("刷手机")


def test_candidate_missing_choices_via_adapter(gen, monkeypatch):
    """响应缺 choices → GenerationUnavailable。"""
    client = _mock_client(
        lambda request: httpx.Response(200, json={"choices": []}))
    monkeypatch.setattr(gen, "_get_client", lambda: client)
    with pytest.raises(base.GenerationUnavailable, match="choices"):
        gen.make_candidate_content("刷手机")


def test_client_reuse(gen, monkeypatch):
    """httpx.Client 惰性创建并跨调用复用。"""
    assert gen._client is None
    calls = _patch_post(monkeypatch, [_GOOD_CANDIDATE, _GOOD_CANDIDATE])
    gen.make_candidate_content("刷手机")
    client1 = gen._get_client()
    gen.make_candidate_content("刷手机")
    client2 = gen._get_client()
    assert client1 is client2
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# 规则包生成
# ---------------------------------------------------------------------------

def _valid_content() -> dict:
    return {
        "name": "再刷五分钟",
        "personality": "时间感扭曲，五分钟等于一小时",
        "gameplay_summary": "它不断弹出下一条；玩家要忍住不点",
        "theme_tags": ["刷手机"],
    }


def _valid_package(content: dict) -> str:
    """用 StubGeneration 产出一个必过全量校验的规则包。"""
    game, avatar = StubGeneration().make_game_and_avatar(content)
    return json.dumps({"avatar": avatar, "game": game}, ensure_ascii=False)


def _invalid_package() -> str:
    """违反动作白名单的规则包。"""
    return json.dumps({
        "avatar": {"face": "round", "eyes": "sleepy", "mouth": "small",
                   "motion_style": "drowsy", "palette": ["#18243A", "#FFD166"]},
        "game": {
            "duration_sec": 70, "initial_node": "a",
            "variables": [], "nodes": [
                {"id": "a", "title": "t", "instruction": "i",
                 "on_enter": [{"op": "avatar.explode"}],
                 "transitions": []},
                {"id": "e", "title": "t", "instruction": "i",
                 "on_enter": [{"op": "game.end", "outcome": "escaped"}],
                 "transitions": []},
                {"id": "c", "title": "t", "instruction": "i",
                 "on_enter": [{"op": "game.end", "outcome": "carried_away"}],
                 "transitions": []},
            ],
        },
    }, ensure_ascii=False)


def test_game_normal(gen, monkeypatch):
    content = _valid_content()
    _patch_post(monkeypatch, [_valid_package(content)])
    game, avatar = gen.make_game_and_avatar(content)
    assert avatar["face"] in ("round", "square", "bean")
    assert 60 <= game["duration_sec"] <= 90


def test_game_invalid_then_valid_with_feedback(gen, monkeypatch):
    content = _valid_content()
    calls = _patch_post(monkeypatch, [_invalid_package(), _valid_package(content)])
    game, _ = gen.make_game_and_avatar(content)
    assert isinstance(game, dict)
    assert len(calls) == 2
    # 重试请求里包含校验错误反馈与封闭值域提示
    retry_user = calls[1][1]["content"]
    assert "未通过校验" in retry_user and "avatar.explode" in retry_user


def test_game_all_invalid(gen, monkeypatch):
    _patch_post(monkeypatch, [_invalid_package()] * 3)
    with pytest.raises(base.GenerationFailed):
        gen.make_game_and_avatar(_valid_content())


def test_game_content_not_modified(gen, monkeypatch):
    content = _valid_content()
    snapshot = copy.deepcopy(content)
    _patch_post(monkeypatch, [_valid_package(content)])
    gen.make_game_and_avatar(content)
    assert content == snapshot


def test_game_bad_json_retry(gen, monkeypatch):
    content = _valid_content()
    calls = _patch_post(monkeypatch, ["{{{", _valid_package(content)])
    game, _ = gen.make_game_and_avatar(content)
    assert isinstance(game, dict)
    assert len(calls) == 2


def test_game_prompt_whitelist_from_shared_constants(monkeypatch):
    """prompt 白名单段落包含 shared 校验器各常量值。"""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    prompt = openai_llm._game_system_prompt()
    for value in (rules_validate.EVENTS | rules_validate.ACTIONS
                  | rules_validate.COMPARE_OPS | rules_validate.OUTCOMES
                  | rules_validate.AVATAR_FACES | rules_validate.AVATAR_EYES
                  | rules_validate.AVATAR_MOUTHS | rules_validate.AVATAR_MOTION_STYLES
                  | rules_validate.AVATAR_EXPRESSIONS | rules_validate.AVATAR_MOTIONS):
        assert value in prompt, f"prompt 缺少白名单值 {value!r}"


def test_game_prompt_tracks_constant_changes(monkeypatch):
    """篡改校验器常量后 prompt 文本随之变化（单一来源）。"""
    fake_faces = set(rules_validate.AVATAR_FACES) | {"star"}
    monkeypatch.setattr(rules_validate, "AVATAR_FACES", fake_faces)
    prompt = openai_llm._game_system_prompt()
    assert "star" in prompt


# ---------------------------------------------------------------------------
# Provider 配置拆分
# ---------------------------------------------------------------------------

def _settings(monkeypatch, **env) -> config.Settings:
    monkeypatch.delenv("SERVER_PROVIDER", raising=False)
    monkeypatch.delenv("SERVER_ASR_PROVIDER", raising=False)
    monkeypatch.delenv("SERVER_LLM_PROVIDER", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.reset_settings_cache()
    return config.get_settings()


def test_settings_defaults_stub(monkeypatch):
    settings = _settings(monkeypatch)
    assert settings.asr_provider == "stub"
    assert settings.llm_provider == "stub"
    # OpenAI 兼容配置默认值
    assert settings.openai_base_url == "https://api.openai.com/v1"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_timeout_sec == 60.0


def test_settings_openai_env(monkeypatch):
    settings = _settings(monkeypatch, OPENAI_BASE_URL="https://llm.example.test/v1/",
                         OPENAI_MODEL="some-model", OPENAI_TIMEOUT_SEC="12.5")
    assert settings.openai_base_url == "https://llm.example.test/v1"  # 去尾斜杠
    assert settings.openai_model == "some-model"
    assert settings.openai_timeout_sec == 12.5


def test_settings_openai_timeout_invalid(monkeypatch):
    """超时解析错误在启动期（get_settings）即抛 ValueError。"""
    monkeypatch.setenv("OPENAI_TIMEOUT_SEC", "abc")
    config.reset_settings_cache()
    with pytest.raises(ValueError):
        config.get_settings()
    monkeypatch.delenv("OPENAI_TIMEOUT_SEC", raising=False)


def test_settings_batch_server_provider(monkeypatch):
    settings = _settings(monkeypatch, SERVER_PROVIDER="remote")
    assert settings.asr_provider == "remote"
    assert settings.llm_provider == "remote"


def test_settings_individual_overrides_batch(monkeypatch):
    settings = _settings(monkeypatch, SERVER_PROVIDER="remote",
                         SERVER_ASR_PROVIDER="stub")
    assert settings.asr_provider == "stub"
    assert settings.llm_provider == "remote"


def test_settings_individual_only(monkeypatch):
    settings = _settings(monkeypatch, SERVER_LLM_PROVIDER="remote")
    assert settings.asr_provider == "stub"
    assert settings.llm_provider == "remote"


def test_build_providers_stub(monkeypatch):
    settings = _settings(monkeypatch)
    asr, generation = build_providers(settings)
    assert isinstance(asr, StubASR)
    assert isinstance(generation, StubGeneration)


def test_build_providers_remote(monkeypatch):
    settings = _settings(monkeypatch, SERVER_PROVIDER="remote",
                         OPENAI_API_KEY="test-key")
    asr, generation = build_providers(settings)
    assert isinstance(asr, RemoteASR)
    assert isinstance(generation, RemoteGeneration)
    assert generation._model == settings.openai_model


def test_build_providers_local(monkeypatch):
    """local ASR 装配为 SherpaLocalASR；未配置模型目录时请求期抛
    GenerationUnavailable（503 语义）。"""
    settings = _settings(monkeypatch, SERVER_ASR_PROVIDER="local")
    asr, generation = build_providers(settings)
    assert isinstance(asr, SherpaLocalASR)
    assert isinstance(generation, StubGeneration)
    with pytest.raises(base.GenerationUnavailable, match="本地模型未配置"):
        asr.transcribe(b"audio", "zh-CN")


def test_whitelist_block_rejects_unknown_action(monkeypatch):
    """校验器新增动作而 prompt 文案未跟进时必须显式抛错（防静默漏报）。"""
    monkeypatch.setattr(rules_validate, "ACTIONS",
                        rules_validate.ACTIONS | {"ghost.new_action"})
    with pytest.raises(ValueError, match="ghost.new_action"):
        openai_llm._game_system_prompt()


def test_build_providers_unknown(monkeypatch):
    settings = _settings(monkeypatch, SERVER_ASR_PROVIDER="nope")
    with pytest.raises(ValueError):
        build_providers(settings)
