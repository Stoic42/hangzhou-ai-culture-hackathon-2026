"""契约 4.2：POST/GET /api/v1/buddy-generations 异步生成任务测试。"""

from __future__ import annotations

from server.app.providers.base import GenerationFailed

from .conftest import create_candidate, submit_generation, wait_generation


def test_full_chain_publishes_buddy_atomically(client):
    """候选 → 202 pending → succeeded 且 buddy_id 立即可读（同事务发布语义）。"""
    candidate = create_candidate(client)
    task = submit_generation(client, candidate["candidate_id"])
    assert task["status"] == "pending"
    assert task["generation_id"]

    done = wait_generation(client, task["generation_id"])
    assert done["status"] == "succeeded"
    assert done["buddy_id"]

    detail = client.get(f"/api/v1/buddies/{done['buddy_id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["buddy_id"] == done["buddy_id"]


def test_idempotent_while_pending_and_after_success(client):
    """幂等：pending 期间与成功后重复提交同一 candidate_id 返回同一任务。"""
    candidate = create_candidate(client)
    first = submit_generation(client, candidate["candidate_id"])
    # pending 期间立即重复提交
    second = submit_generation(client, candidate["candidate_id"])
    assert second["generation_id"] == first["generation_id"]
    done = wait_generation(client, first["generation_id"])
    assert done["status"] == "succeeded"
    # 成功后重复提交返回同一 generation_id 与同一 buddy_id
    third = submit_generation(client, candidate["candidate_id"])
    assert third["generation_id"] == first["generation_id"]
    assert third["buddy_id"] == done["buddy_id"]


def test_unknown_candidate_fails_task_with_202(client):
    """未知 candidate_id → 202，任务 status=failed、error_code=candidate_expired。"""
    task = submit_generation(client, "cnd_no_such")
    assert task["status"] == "failed"
    assert task["error_code"] == "candidate_expired"


def test_unknown_generation_returns_404(client):
    """未知 generation_id → 404 generation_not_found。"""
    resp = client.get("/api/v1/buddy-generations/gen_no_such")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "generation_not_found"


def test_published_content_identical_to_candidate(client):
    """发布内容不变性：buddy 详情 content 与候选响应逐字段相等。"""
    candidate = create_candidate(client)
    buddy_id = None
    task = submit_generation(client, candidate["candidate_id"])
    done = wait_generation(client, task["generation_id"])
    assert done["status"] == "succeeded"
    buddy_id = done["buddy_id"]

    detail = client.get(f"/api/v1/buddies/{buddy_id}").json()
    assert detail["content"] == candidate["content"]


def test_generation_failure_not_published(client, monkeypatch):
    """生成失败注入 → 任务 failed/generation_failed，公共库不出现 buddy。"""
    from server.app.providers.stub import StubGeneration

    original = StubGeneration.make_game_and_avatar

    def _boom(self, content):
        raise GenerationFailed("注入：生成失败")

    monkeypatch.setattr(StubGeneration, "make_game_and_avatar", _boom)
    try:
        candidate = create_candidate(client)
        task = submit_generation(client, candidate["candidate_id"])
        done = wait_generation(client, task["generation_id"])
        assert done["status"] == "failed"
        assert done["error_code"] == "generation_failed"
        listing = client.get("/api/v1/buddies").json()
        assert listing["items"] == []
    finally:
        monkeypatch.setattr(StubGeneration, "make_game_and_avatar", original)


def test_concurrent_submits_return_same_task(client):
    """并发提交同一候选：唯一约束兜底，两边拿到同一任务。"""
    candidate = create_candidate(client)
    results = []
    for _ in range(2):
        results.append(submit_generation(client, candidate["candidate_id"]))
    assert results[0]["generation_id"] == results[1]["generation_id"]
    done = wait_generation(client, results[0]["generation_id"])
    assert done["status"] == "succeeded"
