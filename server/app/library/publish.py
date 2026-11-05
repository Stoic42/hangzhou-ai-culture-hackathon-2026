"""不可变发布：组装 manifest、全量校验、入库。

发布成功即生效，无第二次发布操作（契约 4.2）；
buddy_id 发布后不可变，manifest 与 content_hash 不再修改（契约 4.3）。
"""

from __future__ import annotations

import json
import sqlite3

from .. import db
from ..generation.validate import validate_for_publish
from ..resources import FEEDBACK_RESOURCE
from ..util import content_hash_of

SCHEMA_VERSION = 1


def build_manifest(buddy_id: str, content: dict, game: dict, avatar: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "buddy_id": buddy_id,
        "content_hash": content_hash_of(content),
        "content": content,
        "avatar": avatar,
        "game": game,
        "resources": [dict(FEEDBACK_RESOURCE)],
    }


def publish_buddy(conn: sqlite3.Connection, buddy_id: str, content: dict,
                  game: dict, avatar: dict) -> bool:
    """校验通过即入库发布；校验失败返回 False，不入库。"""
    manifest = build_manifest(buddy_id, content, game, avatar)
    if validate_for_publish(manifest):
        return False
    package_size = len(json.dumps(manifest, ensure_ascii=False).encode("utf-8"))
    db.insert_buddy(
        conn, buddy_id, SCHEMA_VERSION, content, manifest["content_hash"],
        manifest, package_size, db.now_iso())
    return True
