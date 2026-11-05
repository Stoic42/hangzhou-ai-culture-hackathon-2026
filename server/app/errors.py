"""契约错误响应：统一 {"error": {code, message, request_id}} 结构并计入统计。"""

from __future__ import annotations

import sqlite3

from fastapi.responses import JSONResponse

from . import db


def error_response(conn: sqlite3.Connection | None, status: int, code: str,
                   message: str, request_id: str | None) -> JSONResponse:
    if conn is not None:
        db.bump_counter(conn, f"error.{code}")
        if status == 429:
            db.bump_counter(conn, "error.429")
        elif status == 503:
            db.bump_counter(conn, "error.503")
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id}},
    )
