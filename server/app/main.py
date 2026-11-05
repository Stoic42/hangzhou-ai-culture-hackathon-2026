"""应用工厂与装配：配置、数据库、Provider、限流、API 路由、管理后台与静态资源。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, db
from .admin import routes as admin_routes
from .generation import candidates as generation_candidates
from .generation import tasks as generation_tasks
from .library import routes as library_routes
from .providers.remote import build_providers
from .util import RateLimiter

_APP_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _APP_DIR / "static"


def create_app() -> FastAPI:
    settings = config.get_settings()

    # 确保 SQLite 父目录存在，再建库与表
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(settings.db_path)
    db.init_schema(conn)

    asr, generation = build_providers(settings.provider)

    app = FastAPI(title="当代妖怪收容所 · 生成服务与公共搭子库")
    app.state.settings = settings
    app.state.conn = conn
    app.state.db_path = settings.db_path
    app.state.asr = asr
    app.state.generation = generation
    app.state.limiter = RateLimiter(settings.rate_limit_per_min)

    app.include_router(generation_candidates.router, prefix="/api/v1")
    app.include_router(generation_tasks.router, prefix="/api/v1")
    app.include_router(library_routes.router, prefix="/api/v1")

    app.include_router(admin_routes.router, prefix="/admin")
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    return app


app = create_app()
