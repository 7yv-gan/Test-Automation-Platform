"""仪表盘统计接口：概览卡片、趋势、Bug 分布、AI 闭环指标。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BugAnalysis, FeedbackItem, Run, Task, User
from ..security import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total_tasks = db.query(func.count(Task.id)).scalar() or 0
    total_runs = db.query(func.count(Run.id)).scalar() or 0
    success_runs = db.query(func.count(Run.id)).filter(Run.status == "success").scalar() or 0
    failed_runs = db.query(func.count(Run.id)).filter(Run.status.in_(["failed", "timeout", "error"])).scalar() or 0
    pass_rate = round(success_runs / total_runs * 100, 1) if total_runs else 0.0

    analyses = db.query(func.count(BugAnalysis.id)).scalar() or 0
    pending_review = (
        db.query(func.count(BugAnalysis.id)).filter(BugAnalysis.reviewed == 0, BugAnalysis.status == "done").scalar() or 0
    )
    feedback_count = db.query(func.count(FeedbackItem.id)).scalar() or 0

    reviewed = db.query(BugAnalysis).filter(BugAnalysis.reviewed == 1).all()
    correct = sum(1 for a in reviewed if a.review_result == "correct")
    ai_accuracy = round(correct / len(reviewed) * 100, 1) if reviewed else None

    # 各类 Bug 数量
    bug_dist = []
    for row in (
        db.query(BugAnalysis.bug_type, func.count(BugAnalysis.id))
        .filter(BugAnalysis.status == "done")
        .group_by(BugAnalysis.bug_type)
        .order_by(func.count(BugAnalysis.id).desc())
        .limit(10)
        .all()
    ):
        bug_dist.append({"name": row[0] or "未知", "value": row[1]})

    return {
        "total_tasks": total_tasks,
        "total_runs": total_runs,
        "success_runs": success_runs,
        "failed_runs": failed_runs,
        "pass_rate": pass_rate,
        "analyses": analyses,
        "pending_review": pending_review,
        "feedback_count": feedback_count,
        "ai_accuracy": ai_accuracy,
        "reviewed_count": len(reviewed),
        "bug_distribution": bug_dist,
    }


@router.get("/trend")
def trend(
    days: int = 14,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """近 N 天执行趋势：每天执行总数 / 成功 / 失败。"""
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
    bucket: dict[str, dict[str, int]] = {}
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


@router.get("/recent-runs")
def recent_runs(
    limit: int = 10,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    runs = db.query(Run).order_by(Run.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id, "task_id": r.task_id, "task_name": r.task_name,
            "status": r.status, "trigger_user": r.trigger_user,
            "duration_ms": r.duration_ms, "exit_code": r.exit_code,
            "started_at": r.started_at, "finished_at": r.finished_at,
            "has_analysis": bool(db.query(BugAnalysis).filter(BugAnalysis.run_id == r.id).first()),
        }
        for r in runs
    ]
