"""轻量定时调度器：扫描启用了 schedule_interval_min 的任务，到期自动触发执行。

企业级平台常见能力（类似 Jenkins 定时流水线）。后台线程每 30 秒扫描一次。
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from .database import SessionLocal
from .executor import runner
from .models import Run, Task

logger = logging.getLogger(__name__)

_STOP = threading.Event()


def _due(task: Task, last_run: Run | None) -> bool:
    interval = task.schedule_interval_min or 0
    if interval <= 0:
        return False
    if runner.is_task_running(task.id):
        return False
    if last_run is None:
        # 从未执行过：任务创建超过一个周期后开始调度
        return datetime.now() - task.created_at >= timedelta(minutes=interval)
    return datetime.now() - last_run.started_at >= timedelta(minutes=interval)


def _scan_once():
    db = SessionLocal()
    try:
        tasks = db.query(Task).filter(Task.enabled == 1, Task.schedule_interval_min.isnot(None)).all()
        for task in tasks:
            last_run = (
                db.query(Run).filter(Run.task_id == task.id)
                .order_by(Run.id.desc()).first()
            )
            if _due(task, last_run):
                run = Run(
                    task_id=task.id,
                    task_name=task.name,
                    status="pending",
                    trigger_user="scheduler",
                    command=task.command,
                )
                db.add(run)
                db.commit()
                db.refresh(run)
                ok = runner.start_run(run.id)
                logger.info("定时调度触发任务[%s] run#%s 启动=%s", task.name, run.id, ok)
    except Exception as exc:
        logger.exception("定时调度扫描异常: %s", exc)
    finally:
        db.close()


def scheduler_loop():
    logger.info("定时调度器已启动")
    while not _STOP.wait(30):
        try:
            _scan_once()
        except Exception:
            logger.exception("定时调度循环异常")


def start_scheduler():
    threading.Thread(target=scheduler_loop, daemon=True, name="scheduler").start()
