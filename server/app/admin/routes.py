"""管理后台路由：口令认证依赖、概览/列表页面与撤回、重试等运维操作。

隐私约束（契约 4.1）：候选页面绝不显示识别原文 private_text，
模板中不得引用该字段。口令只来自环境变量，不写入代码、模板或日志。
"""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import db
from ..generation import tasks_runner
from ..library.withdraw import withdraw

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_UNCONFIGURED_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>后台未配置</title>
<link rel="stylesheet" href="/static/admin.css"></head>
<body><main class="notice">
<h1>后台未配置 ADMIN_TOKEN</h1>
<p>管理后台需要在环境变量 <code>SERVER_ADMIN_TOKEN</code> 中配置口令后才能使用。
配置完成后重启服务即可访问。</p>
</main></body>
</html>
"""


def _token_from(request: Request) -> str:
    """依次从 cookie 与 query 参数读取访问令牌。"""
    token = request.cookies.get("admin_token", "")
    if not token:
        token = request.query_params.get("token", "")
    return token


def _check_auth(request: Request) -> HTMLResponse | None:
    """未配置口令时返回提示页；未认证时返回登录页；通过返回 None。"""
    settings = request.app.state.settings
    if not settings.admin_token:
        return HTMLResponse(content=_UNCONFIGURED_HTML, status_code=200)
    token = _token_from(request)
    if not secrets.compare_digest(token, settings.admin_token):
        return templates.TemplateResponse(
            request, "login.html", {"token": ""}
        )
    return None


def _page(request: Request, name: str, context: dict) -> HTMLResponse:
    context.setdefault("token", _token_from(request))
    return templates.TemplateResponse(request, name, context)


def _content_brief(content_json: str) -> dict:
    """解析 content_json，提取名称与主题标签；解析失败时给出占位值。"""
    try:
        content = json.loads(content_json)
    except (TypeError, ValueError):
        return {"name": "（解析失败）", "theme_tags": []}
    return {
        "name": content.get("name", "（未命名）"),
        "theme_tags": content.get("theme_tags", []),
    }


@router.get("", response_class=HTMLResponse)
async def stats_page(request: Request):
    denied = _check_auth(request)
    if denied is not None:
        return denied
    state = request.app.state
    return _page(request, "stats.html", {
        "counters": db.get_counters(state.conn),
        "rate_limit_per_min": state.settings.rate_limit_per_min,
        "provider": state.settings.provider,
    })


@router.get("/buddies", response_class=HTMLResponse)
async def buddies_page(request: Request):
    denied = _check_auth(request)
    if denied is not None:
        return denied
    rows = db.list_buddies_admin(request.app.state.conn)
    items = []
    for row in rows:
        brief = _content_brief(row["content_json"])
        items.append({
            "buddy_id": row["buddy_id"],
            "name": brief["name"],
            "theme_tags": brief["theme_tags"],
            "content_hash": row["content_hash"][:12],
            "package_size": row["package_size"],
            "published_at": row["published_at"],
            "withdrawn": bool(row["withdrawn"]),
        })
    return _page(request, "buddies.html", {"items": items})


@router.get("/generations", response_class=HTMLResponse)
async def generations_page(request: Request):
    denied = _check_auth(request)
    if denied is not None:
        return denied
    rows = db.list_generations(request.app.state.conn)
    items = [{
        "generation_id": row["generation_id"],
        "candidate_id": row["candidate_id"],
        "status": row["status"],
        "buddy_id": row["buddy_id"],
        "error_code": row["error_code"],
        "updated_at": row["updated_at"],
    } for row in rows]
    return _page(request, "generations.html", {"items": items})


@router.get("/candidates", response_class=HTMLResponse)
async def candidates_page(request: Request):
    denied = _check_auth(request)
    if denied is not None:
        return denied
    rows = db.list_candidates(request.app.state.conn)
    items = []
    for row in rows:
        brief = _content_brief(row["content_json"])
        items.append({
            "candidate_id": row["candidate_id"],
            "name": brief["name"],
            "theme_tags": brief["theme_tags"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        })
    return _page(request, "candidates.html", {"items": items})


def _check_form_auth(request: Request, token: str) -> HTMLResponse | None:
    """POST 操作的认证：口令取自表单字段。未配置口令时返回提示页。"""
    settings = request.app.state.settings
    if not settings.admin_token:
        return HTMLResponse(content=_UNCONFIGURED_HTML, status_code=200)
    if not secrets.compare_digest(token, settings.admin_token):
        return templates.TemplateResponse(
            request, "login.html", {"token": ""}
        )
    return None


@router.post("/login")
async def login(request: Request, token: str = Form(default="")):
    settings = request.app.state.settings
    if not settings.admin_token:
        return HTMLResponse(content=_UNCONFIGURED_HTML, status_code=200)
    if not secrets.compare_digest(token, settings.admin_token):
        return templates.TemplateResponse(
            request, "login.html", {"token": "", "error": True}
        )
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie("admin_token", token, httponly=True, samesite="lax")
    return response


@router.post("/buddies/{buddy_id}/withdraw")
async def withdraw_buddy(buddy_id: str, request: Request,
                         token: str = Form(default="")):
    denied = _check_form_auth(request, token)
    if denied is not None:
        return denied
    withdraw(request.app.state.conn, buddy_id)
    return RedirectResponse(url="/admin/buddies", status_code=303)


@router.post("/generations/{generation_id}/retry")
async def retry_generation(generation_id: str, request: Request,
                           token: str = Form(default="")):
    denied = _check_form_auth(request, token)
    if denied is not None:
        return denied
    state = request.app.state
    # 仅当真正由 failed 重置为 pending 时才启动执行线程，
    # 否则说明状态已被别的请求处理，直接重定向
    if db.reset_generation_for_retry(state.conn, generation_id):
        thread = threading.Thread(
            target=tasks_runner.run_generation,
            args=(state.db_path, state.generation, generation_id),
            daemon=True,
        )
        thread.start()
    return RedirectResponse(url="/admin/generations", status_code=303)
