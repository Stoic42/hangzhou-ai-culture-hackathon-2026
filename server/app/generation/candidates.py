"""POST /api/v1/buddy-candidates：语音创建候选搭子（契约 4.1）。

隐私约束：原始音频只在内存中传给 ASR，识别后即弃；
识别文本作为服务端私有上下文入库，随候选过期删除，不出现在任何响应中。
"""

from __future__ import annotations

import io
import json
import wave
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, Form, Request, UploadFile

from .. import db
from ..errors import error_response
from ..providers.base import (
    ContentNotSupported, GenerationUnavailable, SpeechUnrecognized,
)
from ..util import new_id

router = APIRouter()


def _wav_duration_sec(audio: bytes) -> float | None:
    """解析 WAV 时长；非 WAV 或损坏返回 None。"""
    try:
        with wave.open(io.BytesIO(audio)) as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate) if rate else None
    except (wave.Error, EOFError):
        return None


@router.post("/buddy-candidates", status_code=201)
async def create_candidate(
    request: Request,
    request_id: str = Form(...),
    locale: str = Form("zh-CN"),
    audio: UploadFile = File(...),
):
    state = request.app.state
    settings = state.settings
    conn = state.conn

    if not state.limiter.allow(request.client.host if request.client else "unknown"):
        return error_response(conn, 429, "rate_limited",
                              "创建过于频繁，请稍后再试", request_id)

    raw = await audio.read()
    if not raw or len(raw) > settings.audio_max_bytes:
        return error_response(conn, 400, "invalid_audio",
                              "音频为空或超过大小限制", request_id)
    duration = _wav_duration_sec(raw)
    if duration is None or duration > settings.audio_max_duration_sec:
        return error_response(
            conn, 400, "invalid_audio",
            f"音频须为WAV且不超过{settings.audio_max_duration_sec}秒", request_id)

    try:
        text = state.asr.transcribe(raw, locale)
    except GenerationUnavailable:
        return error_response(conn, 503, "generation_unavailable",
                              "识别服务暂不可用", request_id)
    except SpeechUnrecognized:
        return error_response(conn, 422, "speech_unrecognized",
                              "没有听清，请再说一次", request_id)
    finally:
        del raw  # 原始音频识别后即弃，不落盘、不入日志

    try:
        content = state.generation.make_candidate_content(text)
    except ContentNotSupported:
        return error_response(conn, 422, "content_not_supported",
                              "这个话题暂时无法生成搭子", request_id)
    except GenerationUnavailable:
        return error_response(conn, 503, "generation_unavailable",
                              "候选生成服务暂不可用", request_id)

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=settings.candidate_ttl_sec)
    candidate_id = new_id("cnd")
    db.insert_candidate(
        conn, candidate_id, content, text,
        now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        expires.strftime("%Y-%m-%dT%H:%M:%SZ"))
    db.delete_expired_candidates(conn, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    db.bump_counter(conn, "candidates.created")

    return {
        "candidate_id": candidate_id,
        "content": content,
        "expires_in_sec": settings.candidate_ttl_sec,
    }
