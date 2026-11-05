"""GET /api/v1/buddies*：无登录公共搭子库（契约 4.3）。

稳定分页：published_at 降序 + buddy_id 降序，cursor 绑定该顺序；
撤回搭子详情返回 410，列表不再出现；列表不泄露创造者原话与规则源码说明。
"""

from __future__ import annotations

import base64
import json

from fastapi import APIRouter, Query, Request

from .. import db
from ..errors import error_response

router = APIRouter()

_MAX_LIMIT = 50


def _encode_cursor(published_at: str, buddy_id: str) -> str:
    raw = f"{published_at}|{buddy_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        published_at, buddy_id = raw.split("|", 1)
        return published_at, buddy_id
    except (ValueError, UnicodeDecodeError):
        return None


def _list_item(row) -> dict:
    return {
        "buddy_id": row["buddy_id"],
        "schema_version": row["schema_version"],
        "content": json.loads(row["content_json"]),
        "content_hash": row["content_hash"],
        "package_size": row["package_size"],
        "published_at": row["published_at"],
    }


@router.get("/buddies")
async def list_buddies(
    request: Request,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=_MAX_LIMIT),
):
    conn = request.app.state.conn
    after = None
    if cursor is not None:
        after = _decode_cursor(cursor)
        if after is None:
            return error_response(conn, 400, "invalid_cursor",
                                  "分页游标无效", None)
    rows = db.list_buddies_page(conn, limit + 1, after)
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        _encode_cursor(rows[-1]["published_at"], rows[-1]["buddy_id"])
        if has_more and rows else None
    )
    return {"items": [_list_item(r) for r in rows], "next_cursor": next_cursor}


@router.get("/buddies/{buddy_id}")
async def get_buddy_detail(buddy_id: str, request: Request):
    conn = request.app.state.conn
    row = db.get_buddy(conn, buddy_id)
    if row is None:
        return error_response(conn, 404, "buddy_not_found", "搭子不存在", None)
    if row["withdrawn"]:
        return error_response(conn, 410, "buddy_withdrawn", "搭子已被撤回", None)
    base = request.app.state.settings.base_url
    item = _list_item(row)
    item["manifest_url"] = f"{base}/api/v1/buddies/{buddy_id}/manifest"
    return item


@router.get("/buddies/{buddy_id}/manifest")
async def get_buddy_manifest(buddy_id: str, request: Request):
    conn = request.app.state.conn
    row = db.get_buddy(conn, buddy_id)
    if row is None:
        return error_response(conn, 404, "buddy_not_found", "搭子不存在", None)
    if row["withdrawn"]:
        return error_response(conn, 410, "buddy_withdrawn", "搭子已被撤回", None)
    return json.loads(row["manifest_json"])
