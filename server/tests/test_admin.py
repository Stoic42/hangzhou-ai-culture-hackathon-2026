"""管理后台：口令认证、撤回/重试操作与隐私约束测试。"""

from __future__ import annotations

from .conftest import (
    create_buddy, create_candidate, make_wav, submit_generation,
    upload_candidate, wait_generation,
)

_PAGES = ["/admin", "/admin/buddies", "/admin/generations", "/admin/candidates"]


def _login(client, token: str):
    return client.post("/admin/login", data={"token": token},
                       follow_redirects=False)


def test_unauthenticated_pages_show_login(client):
    """无 token 访问四个后台页面 → 登录页。"""
    for page in _PAGES:
        resp = client.get(page)
        assert resp.status_code == 200, page
        assert "管理员登录" in resp.text, page
        assert "口令错误" not in resp.text


def test_wrong_token_still_shows_login(client):
    """错误口令 POST /admin/login 仍回登录页。"""
    resp = _login(client, "wrong-token")
    assert resp.status_code == 200, resp.text
    assert "管理员登录" in resp.text
    assert "口令错误" in resp.text


def test_login_success_unlocks_all_pages(client):
    """正确口令 → cookie 生效，四个页面 200。"""
    resp = _login(client, "test-token")
    assert resp.status_code == 303
    for page in _PAGES:
        resp = client.get(page)
        assert resp.status_code == 200, page
        assert "管理员登录" not in resp.text, page


def test_withdraw_via_admin_form(client):
    """后台表单撤回：公共详情变 410，后台列表显示已撤回。"""
    _login(client, "test-token")
    buddy_id = create_buddy(client)

    resp = client.post(f"/admin/buddies/{buddy_id}/withdraw",
                       data={"token": "test-token"}, follow_redirects=False)
    assert resp.status_code == 303

    public = client.get(f"/api/v1/buddies/{buddy_id}")
    assert public.status_code == 410
    assert public.json()["error"]["code"] == "buddy_withdrawn"

    page = client.get("/admin/buddies")
    assert page.status_code == 200
    assert buddy_id in page.text
    assert "已撤回" in page.text


def test_retry_failed_generation(client):
    """对 candidate_expired 的失败任务重试：状态重置并重新执行，最终仍 failed。"""
    _login(client, "test-token")
    task = submit_generation(client, "cnd_no_such")
    assert task["status"] == "failed"
    generation_id = task["generation_id"]

    resp = client.post(f"/admin/generations/{generation_id}/retry",
                       data={"token": "test-token"}, follow_redirects=False)
    assert resp.status_code == 303

    # 重试后线程会再次执行并再次失败（候选不存在）
    done = wait_generation(client, generation_id)
    assert done["status"] == "failed"
    assert done["error_code"] == "candidate_expired"


def test_retry_non_failed_task_keeps_state(client):
    """对非 failed 任务重试不改变状态。"""
    _login(client, "test-token")
    buddy_id = create_buddy(client)
    task = submit_generation(client, create_candidate(client)["candidate_id"])
    done = wait_generation(client, task["generation_id"])
    assert done["status"] == "succeeded"

    resp = client.post(f"/admin/generations/{task['generation_id']}/retry",
                       data={"token": "test-token"}, follow_redirects=False)
    assert resp.status_code == 303
    still = client.get(f"/api/v1/buddy-generations/{task['generation_id']}")
    assert still.json()["status"] == "succeeded"


def test_candidates_page_has_no_private_text(client):
    """候选页 HTML 不含任何识别原文（隐私红线）。"""
    _login(client, "test-token")
    upload_candidate(client, make_wav(0.5))
    page = client.get("/admin/candidates")
    assert page.status_code == 200
    assert "stub识别：" not in page.text
    assert "private_text" not in page.text


def test_unconfigured_admin_shows_notice(no_token_client):
    """ADMIN_TOKEN 为空串 → 后台页面提示未配置，且不是登录表单。"""
    for page in _PAGES:
        resp = no_token_client.get(page)
        assert resp.status_code == 200, page
        assert "未配置" in resp.text, page
        assert "管理员登录" not in resp.text, page
