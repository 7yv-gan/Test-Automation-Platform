"""报告中心接口：质量总览 / 趋势 / 失败 Top / 最近报告列表。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BugAnalysis, FeedbackItem, Run, Task, TestCase, User
from ..security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/overview")
def report_overview(
    days: int = 14,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """报告平台核心指标：执行量 / 通过率 / 平均耗时 / 失败率 / AI 效果。"""
    since = datetime.combine(datetime.now().date() - timedelta(days=days - 1), datetime.min.time())
    total = db.query(func.count(Run.id)).filter(Run.started_at >= since).scalar() or 0
    success = db.query(func.count(Run.id)).filter(Run.started_at >= since, Run.status == "success").scalar() or 0
    failed = db.query(func.count(Run.id)).filter(
        Run.started_at >= since, Run.status.in_(["failed", "timeout", "error"])).scalar() or 0
    pass_rate = round(success / total * 100, 1) if total else 0.0
    avg_duration = db.query(func.avg(Run.duration_ms)).filter(Run.started_at >= since, Run.duration_ms > 0).scalar()
    avg_duration_s = round((avg_duration or 0) / 1000, 1)

    # 失败 Top 任务（报告中心亮点：质量雷达）
    fail_top = []
    for row in (
        db.query(Run.task_name, func.count(Run.id))
        .filter(Run.started_at >= since, Run.status.in_(["failed", "timeout", "error"]))
        .group_by(Run.task_name)
        .order_by(func.count(Run.id).desc())
        .limit(8)
        .all()
    ):
        fail_top.append({"name": row[0] or "未知", "value": row[1]})

    # 用例库视角：各模块用例数
    module_dist = []
    for row in (
        db.query(func.coalesce(TestCase.module, "未分组"), func.count(TestCase.id))
        .group_by(TestCase.module)
        .order_by(func.count(TestCase.id).desc())
        .limit(10)
        .all()
    ):
        module_dist.append({"name": row[0] or "未分组", "value": row[1]})

    reviewed = db.query(BugAnalysis).filter(BugAnalysis.reviewed == 1).all()
    correct = sum(1 for a in reviewed if a.review_result == "correct")
    ai_accuracy = round(correct / len(reviewed) * 100, 1) if reviewed else None

    return {
        "days": days,
        "total_runs": total,
        "success_runs": success,
        "failed_runs": failed,
        "pass_rate": pass_rate,
        "avg_duration_s": avg_duration_s,
        "ai_accuracy": ai_accuracy,
        "feedback_count": db.query(func.count(FeedbackItem.id)).scalar() or 0,
        "fail_top": fail_top,
        "module_dist": module_dist,
    }


@router.get("/trend")
def report_trend(
    days: int = 14,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    today = datetime.now().date()
    rows = (
        db.query(
            func.date(Run.started_at).label("day"),
            Run.status,
            func.count(Run.id),
        )
        .filter(Run.started_at >= datetime.combine(today - timedelta(days=days - 1), datetime.min.time()))
        .group_by(func.date(Run.started_at), Run.status)
        .all()
    )
    bucket: dict[str, dict] = {}
    for day, status, cnt in rows:
        key = str(day or today)
        b = bucket.setdefault(key, {"total": 0, "success": 0, "failed": 0})
        b["total"] += cnt
        if status == "success":
            b["success"] += cnt
        elif status in ("failed", "timeout", "error"):
            b["failed"] += cnt
    result = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        key = day.isoformat()
        b = bucket.get(key, {"total": 0, "success": 0, "failed": 0})
        result.append({"date": key, **b})
    return result


@router.get("/recent")
def report_recent(
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    runs = db.query(Run).order_by(Run.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "task_name": r.task_name, "status": r.status,
            "agent_name": r.agent_name or "local",
            "duration_ms": r.duration_ms, "exit_code": r.exit_code,
            "trigger_user": r.trigger_user, "started_at": r.started_at,
        }
        for r in runs
    ]
