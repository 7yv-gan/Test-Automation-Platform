"""自动化测试平台 入口。

启动：python main.py   （默认 http://127.0.0.1:8000）
"""
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import (
    agents, ai, auth, cases, dashboard, devices, environments, notifications,
    reports, runs, settings as api_settings, tasks,
)
from app.agents import worker as agent_worker
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Setting, User
from app.scheduler import start_scheduler
from app.security import hash_password

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("platform")

settings.ensure_dirs()
app = FastAPI(title="自动化测试平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _migrate():
    """轻量迁移：老库 runs 表缺 agent_name 列时补列（新增表由 create_all 自动创建）。"""
    from sqlalchemy import inspect, text

    db = SessionLocal()
    try:
        inspector = inspect(engine)
        if "runs" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("runs")}
            if "agent_name" not in cols:
                db.execute(text("ALTER TABLE runs ADD COLUMN agent_name VARCHAR(64) DEFAULT ''"))
                db.commit()
                logger.info("迁移：runs 表已补充 agent_name 列")
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate()
    db = SessionLocal()
    try:
        # 默认管理员
        if not db.query(User).filter(User.username == settings.ADMIN_USERNAME).first():
            db.add(User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
            ))
            db.commit()
            logger.info("已创建默认管理员: %s", settings.ADMIN_USERNAME)
        # 将数据库中的平台设置合并进进程内配置
        for row in db.query(Setting).all():
            key = row.key
            if hasattr(settings, key.upper()):
                try:
                    current = getattr(settings, key.upper())
                    setattr(settings, key.upper(), type(current)(row.value))
                except ValueError:
                    pass
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


def register_routes():
    app.include_router(auth.router)
    app.include_router(tasks.router)
    app.include_router(runs.router)
    app.include_router(ai.router)
    app.include_router(dashboard.router)
    app.include_router(api_settings.router)
    app.include_router(agents.router)
    app.include_router(devices.router)
    app.include_router(environments.router)
    app.include_router(cases.router)
    app.include_router(reports.router)
    app.include_router(notifications.router)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        from fastapi.responses import Response
        p = Path(__file__).parent / "app" / "static" / "favicon.svg"
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/svg+xml")
        return Response(status_code=204)


def mount_static():
    static_dir = Path(__file__).parent / "app" / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    init_db()
    register_routes()
    mount_static()
    start_scheduler()
    agent_worker.start_agent_cluster()
    logger.info("自动化测试平台启动中...")
    uvicorn.run(app, host="127.0.0.1", port=settings.PORT)
