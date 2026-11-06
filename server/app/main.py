"""应用工厂与装配：配置、数据库、Provider、限流、API 路由、管理后台与静态资源。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config, db
from .admin import routes as admin_routes
from .generation import candidates as generation_candidates
from .generation import tasks as generation_tasks
from .library import routes as library_routes
from .providers import build_providers
from .util import RateLimiter

_APP_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _APP_DIR / "static"


class _ThreadLocalConn:
    """线程本地连接代理：按当前线程转发到各自的数据库连接。

    路由里 `state.conn.xxx` 的既有调用零改动地落到本线程的连接上，
    避免共享单连接在并发请求下事务交错。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return db.get_thread_conn(self._db_path)

    def __getattr__(self, name: str):
        return getattr(self._conn(), name)

    def __enter__(self) -> sqlite3.Connection:
        # `with conn:` 走隐式特殊方法查找，不经 __getattr__，需显式转发
        return self._conn().__enter__()

    def __exit__(self, *args) -> None:
        self._conn().__exit__(*args)

    def __eq__(self, other: object) -> bool:
        return self._conn() == other

    def __hash__(self) -> int:
        return hash(self._conn())


def create_app() -> FastAPI:
    settings = config.get_settings()

    # 确保 SQLite 父目录存在，再建库与表（init_schema 只在启动时跑一次）
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    bootstrap_conn = db.connect(settings.db_path)
    db.init_schema(bootstrap_conn)
    bootstrap_conn.close()

    asr, generation = build_providers(settings)

    app = FastAPI(title="当代妖怪收容所 · 生成服务与公共搭子库")
    app.state.settings = settings
    app.state.conn = _ThreadLocalConn(settings.db_path)
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
