"""契约 4.1：POST /api/v1/buddy-candidates 候选创建接口测试。"""

from __future__ import annotations

from server.app.providers.base import (  # noqa: F401 — 注入异常类型
    GenerationUnavailable, SpeechUnrecognized,
)

from .conftest import make_wav, upload_candidate

_CONTENT_FIELDS = {"name", "personality", "gameplay_summary", "theme_tags"}


def _assert_error_shape(resp, status: int, code: str) -> None:
    """统一错误结构：{"error": {"code", "message", "request_id"}}。"""
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body["error"].keys()) == {"code", "message", "request_id"}
    assert body["error"]["code"] == code


def test_valid_wav_returns_candidate_and_no_raw_text(client):
    """正常 WAV → 201，content 四字段齐全，响应任何位置不含识别原文。"""
    resp = upload_candidate(client, make_wav(1.0))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"candidate_id", "content", "expires_in_sec"}
    assert set(body["content"].keys()) == _CONTENT_FIELDS
    assert body["expires_in_sec"] > 0
    # 隐私红线：stub 识别文本形如 “stub识别：...”，不得出现在响应中
    assert "stub识别：" not in resp.text


def test_empty_audio_rejected(client):
    """空字节音频 → 400 invalid_audio。"""
    _assert_error_shape(upload_candidate(client, b""), 400, "invalid_audio")


def test_non_wav_bytes_rejected(client):
    """非 WAV 字节 → 400 invalid_audio。"""
    _assert_error_shape(upload_candidate(client, b"not a wav at all"), 400,
                        "invalid_audio")


def test_overlong_wav_rejected(client):
    """超过 30 秒的 WAV → 400 invalid_audio。"""
    _assert_error_shape(upload_candidate(client, make_wav(31.0)), 400,
                        "invalid_audio")


def test_forged_content_length_rejected_before_read(client):
    """伪造超大 Content-Length 的小音频在预检路径被拒绝 → 400 invalid_audio。"""
    resp = client.post(
        "/api/v1/buddy-candidates",
        data={"request_id": "req-cl", "locale": "zh-CN"},
        files={"audio": ("voice.wav", make_wav(0.5), "audio/wav")},
        headers={"Content-Length": str(3 * 1024 * 1024)},
    )
    _assert_error_shape(resp, 400, "invalid_audio")


def test_silence_prefix_yields_speech_unrecognized(client, monkeypatch):
    """静音注入 → 422 speech_unrecognized。

    stub 按音频字节前缀判断，但服务端先做 WAV 校验，前缀会破坏 WAV 头；
    因此直接替换 app.state.asr 为抛 SpeechUnrecognized 的假对象（更稳的注入方式）。
    """

    class _SilentASR:
        def transcribe(self, audio: bytes, locale: str) -> str:
            raise SpeechUnrecognized("注入：未获得可用语义")

    monkeypatch.setattr(client.app.state, "asr", _SilentASR())
    _assert_error_shape(upload_candidate(client, make_wav(1.0)), 422,
                        "speech_unrecognized")


def test_unavailable_provider_yields_503(client, monkeypatch):
    """识别服务不可用注入 → 503 generation_unavailable。"""

    class _DownASR:
        def transcribe(self, audio: bytes, locale: str) -> str:
            raise GenerationUnavailable("注入：识别服务不可用")

    monkeypatch.setattr(client.app.state, "asr", _DownASR())
    _assert_error_shape(upload_candidate(client, make_wav(1.0)), 503,
                        "generation_unavailable")


def test_rate_limit_exceeded(limited_client):
    """阈值 3：交错验证公共库浏览不占候选创建配额。

    先用掉 2 次配额，中间穿插 10 次 GET /buddies，第 3 次创建仍应 201；
    第 4 次创建才 429。
    """
    for _ in range(2):
        resp = upload_candidate(limited_client, make_wav(0.2))
        assert resp.status_code == 201, resp.text
    # 公共库浏览不计入限流配额：穿插多次不影响剩余配额
    for _ in range(10):
        assert limited_client.get("/api/v1/buddies").status_code == 200
    resp = upload_candidate(limited_client, make_wav(0.2))
    assert resp.status_code == 201, resp.text
    _assert_error_shape(upload_candidate(limited_client, make_wav(0.2)),
                        429, "rate_limited")


def test_error_response_unified_shape(client):
    """任意 4xx 错误都遵循统一错误结构。"""
    _assert_error_shape(upload_candidate(client, b"junk"), 400, "invalid_audio")
    resp = client.get("/api/v1/buddy-generations/gen_missing")
    _assert_error_shape(resp, 404, "generation_not_found")
