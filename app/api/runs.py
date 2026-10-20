"""执行记录接口：列表 / 详情 / 日志增量读取。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import BugAnalysis, Run, User
from ..schemas import AnalysisOut, RunOut
from ..security import get_current_user

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
def list_runs(
    task_id: int | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Run)
    if task_id:
        q = q.filter(Run.task_id == task_id)
    if status:
        q = q.filter(Run.status == status)
    return q.order_by(Run.id.desc()).limit(limit).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return run


@router.get("/{run_id}/logs", response_class=PlainTextResponse)
def get_logs(
    run_id: int,
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """增量返回日志：前端用 offset 轮询，返回 (offset 之后的内容) + 结束标记头。"""
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if not run.log_path:
        return ""
    path = Path(run.log_path)
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    chunk = data[offset:]
    # 通过响应头告知前端本次读取后是否已到文件末尾（-1 表示已结束）
    end_marker = "-1" if run.status in ("success", "failed", "timeout", "error", "cancelled") else "1"
    return PlainTextResponse(chunk, headers={"X-Log-End": end_marker})


@router.get("/{run_id}/analysis", response_model=AnalysisOut | None)
def get_analysis(run_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(BugAnalysis).filter(BugAnalysis.run_id == run_id).first()


@router.post("/{run_id}/reanalyze")
def reanalyze_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重新触发 AI 分析：会带上最新的人工纠正样本（few-shot / 知识库）。

    人工数据闭环的验证入口 —— 纠正一次后重跑分析，观察 source 与结论变化。
    """
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if not run.error_brief:
        raise HTTPException(status_code=400, detail="仅失败的执行可进行分析")
    log_path = Path(run.log_path or settings.LOGS_DIR / f"run_{run_id}.log")
    from ..ai.analyzer import analyze_run_async
    from ..models import OperationLog
    analyze_run_async(run_id, log_path, run.error_brief)
    db.add(OperationLog(username=user.username, action="reanalyze",
                        detail=f"重新分析 run#{run_id}（将引用最新人工纠正样本）"))
    db.commit()
    return {"ok": True, "message": "分析已触发，稍后刷新查看结果"}
