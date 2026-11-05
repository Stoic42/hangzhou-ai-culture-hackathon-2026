"""POST/GET /api/v1/buddy-generations：异步生成具体逻辑（契约 4.2）。

幂等：同一 candidate_id 重复提交返回同一任务；
候选缺失/过期时任务立即以 failed/candidate_expired 落库并照常返回 202；
任务 succeeded 时 buddy 已在公共库可读（同事务发布，见 publish.py）。
"""

from __future__ import annotations

import sqlite3
import threading

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .. import db
from ..errors import error_response
from ..util import new_id
from .tasks_runner import run_generation

router = APIRouter()


class GenerationRequest(BaseModel):
    request_id: str
    candidate_id: str


def _task_view(row) -> dict:
    return {
        "generation_id": row["generation_id"],
        "status": row["status"],
        "buddy_id": row["buddy_id"],
        "error_code": row["error_code"],
    }


@router.post("/buddy-generations", status_code=202)
async def submit_generation(body: GenerationRequest, request: Request):
    state = request.app.state
    conn = state.conn

    if not state.limiter.allow(request.client.host if request.client else "unknown"):
        return error_response(conn, 429, "rate_limited",
                              "提交过于频繁，请稍后再试", body.request_id)

    existing = db.get_generation_by_candidate(conn, body.candidate_id)
    if existing is not None:
        # 幂等：进行中返回同一任务，已成功返回同一 buddy_id
        return _task_view(existing)

    generation_id = new_id("gen")
    now = db.now_iso()
    try:
        db.insert_generation(conn, generation_id, body.candidate_id, now)
    except sqlite3.IntegrityError:
        # 并发提交撞上 candidate_id 唯一约束：返回已存在的同一任务
        existing = db.get_generation_by_candidate(conn, body.candidate_id)
        if existing is not None:
            return _task_view(existing)
        raise

    candidate = db.get_candidate(conn, body.candidate_id)
    if candidate is None:
        # 候选不存在或已过期：失败体现在任务状态里，而非 HTTP 错误
        db.update_generation(conn, generation_id, "failed", None, "candidate_expired")
        row = db.get_generation(conn, generation_id)
        return _task_view(row)

    thread = threading.Thread(
        target=run_generation,
        args=(state.db_path, state.generation, generation_id),
        daemon=True,
    )
    thread.start()
    return {"generation_id": generation_id, "status": "pending"}


@router.get("/buddy-generations/{generation_id}")
async def get_generation(generation_id: str, request: Request):
    conn = request.app.state.conn
    row = db.get_generation(conn, generation_id)
    if row is None:
        return error_response(conn, 404, "generation_not_found",
                              "生成任务不存在", None)
    return _task_view(row)
