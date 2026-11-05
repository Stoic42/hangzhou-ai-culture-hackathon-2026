"""契约 4.3：GET /api/v1/buddies* 公共搭子库测试。"""

from __future__ import annotations

import json

from server.app.generation.validate import validate_for_publish
from server.app.library.withdraw import withdraw
from server.app.util import content_hash_of

from .conftest import create_buddy, make_wav

_LIST_FIELDS = {
    "buddy_id", "schema_version", "content", "content_hash",
    "package_size", "published_at",
}
_FORBIDDEN_FIELDS = {"private_text", "candidate_id", "manifest_json"}


def _create_three(client) -> list[str]:
    """造三只 buddy：不同音频字节让 stub 产出不同 content（撞主题也接受）。"""
    ids = []
    for seed in (11, 222, 3333):
        ids.append(create_buddy(client, make_wav(0.5, seed=seed)))
    assert len(set(ids)) == 3
    return ids


def _sort_key(item: dict) -> tuple[str, str]:
    """published_at 降序 + buddy_id 降序的稳定排序键（取反用于降序断言）。"""
    return (item["published_at"], item["buddy_id"])


def test_list_ordering_desc(client):
    """默认分页：items 按 published_at 降序、同刻 buddy_id 降序。"""
    _create_three(client)
    items = client.get("/api/v1/buddies").json()["items"]
    assert len(items) >= 3
    keys = [_sort_key(i) for i in items]
    assert keys == sorted(keys, reverse=True)


def test_cursor_pagination_no_dup_no_miss(client):
    """limit=2 翻页：两页合集 = 全量，无重复无遗漏且顺序一致。"""
    _create_three(client)
    full = client.get("/api/v1/buddies", params={"limit": 50}).json()["items"]

    page1 = client.get("/api/v1/buddies", params={"limit": 2}).json()
    assert page1["next_cursor"]
    page2 = client.get("/api/v1/buddies", params={
        "limit": 2, "cursor": page1["next_cursor"],
    }).json()

    collected = page1["items"] + page2["items"]
    assert collected == full  # 顺序一致、无重复无遗漏
    if page2["next_cursor"] is not None:
        page3 = client.get("/api/v1/buddies", params={
            "limit": 2, "cursor": page2["next_cursor"],
        }).json()
        assert page3["items"] == []  # 空页也应合法返回


def test_invalid_cursor_rejected(client):
    """cursor=garbage → 400 invalid_cursor。"""
    resp = client.get("/api/v1/buddies", params={"cursor": "garbage"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "invalid_cursor"


def test_list_item_fields_exact(client):
    """列表项字段恰好为契约集合，不得泄露 private_text/candidate_id/manifest_json。"""
    _create_three(client)
    items = client.get("/api/v1/buddies").json()["items"]
    for item in items:
        assert set(item.keys()) == _LIST_FIELDS
        assert not (_FORBIDDEN_FIELDS & set(item.keys()))
        assert "stub识别：" not in json.dumps(item, ensure_ascii=False)


def test_detail_has_manifest_url_and_valid_manifest(client):
    """详情含 manifest_url；manifest 通过发布校验且 content_hash 一致。"""
    buddy_id = create_buddy(client)
    detail = client.get(f"/api/v1/buddies/{buddy_id}").json()
    assert detail["manifest_url"].endswith(f"/api/v1/buddies/{buddy_id}/manifest")

    manifest_resp = client.get(f"/api/v1/buddies/{buddy_id}/manifest")
    assert manifest_resp.status_code == 200, manifest_resp.text
    manifest = manifest_resp.json()
    assert validate_for_publish(manifest) == []
    assert manifest["content_hash"] == content_hash_of(manifest["content"])
    assert manifest["content_hash"] == detail["content_hash"]


def test_withdraw_hides_but_keeps_record(client):
    """撤回：详情与 manifest 410，列表消失，数据库记录仍在；未知 id 404。"""
    buddy_id = create_buddy(client)
    conn = client.app.state.conn
    assert withdraw(conn, buddy_id) is True

    for path in (f"/api/v1/buddies/{buddy_id}",
                 f"/api/v1/buddies/{buddy_id}/manifest"):
        resp = client.get(path)
        assert resp.status_code == 410, resp.text
        assert resp.json()["error"]["code"] == "buddy_withdrawn"

    items = client.get("/api/v1/buddies").json()["items"]
    assert all(i["buddy_id"] != buddy_id for i in items)

    # 撤回是置标记而非删除：数据库记录仍在
    row = client.get(f"/api/v1/buddies/{buddy_id}")
    assert row.status_code == 410
    from server.app import db as db_module
    raw = db_module.get_buddy(conn, buddy_id)
    assert raw is not None and raw["withdrawn"] == 1

    # 未知 id：404 而非 410
    resp = client.get("/api/v1/buddies/bdy_no_such")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "buddy_not_found"


def test_manifest_immutable_between_reads(client):
    """不可变性：两次 GET manifest 字节相等。"""
    buddy_id = create_buddy(client)
    first = client.get(f"/api/v1/buddies/{buddy_id}/manifest")
    second = client.get(f"/api/v1/buddies/{buddy_id}/manifest")
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
