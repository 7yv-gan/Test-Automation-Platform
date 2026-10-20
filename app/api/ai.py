"""AI 分析结果与人工审核闭环接口。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai.analyzer import extract_keywords, log_sample_for_feedback
from ..database import get_db
from ..models import BugAnalysis, FeedbackItem, OperationLog, Run, User
from ..schemas import AnalysisOut, ReviewRequest
from ..security import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _log(db: Session, username: str, action: str, detail: str = ""):
    db.add(OperationLog(username=username, action=action, detail=detail))
    db.commit()


@router.get("/analyses", response_model=list[AnalysisOut])
def list_analyses(
    reviewed: int | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(BugAnalysis)
    if reviewed is not None:
        q = q.filter(BugAnalysis.reviewed == reviewed)
    return q.order_by(BugAnalysis.id.desc()).limit(limit).all()


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    a = db.get(BugAnalysis, analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析记录不存在")
    return a


@router.post("/analyses/{analysis_id}/review", response_model=AnalysisOut)
def review_analysis(
    analysis_id: int,
    body: ReviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """人工审核：correct 表示 AI 结论正确；incorrect 表示错误并提交纠正结论。
    纠正结论自动沉淀为 FeedbackItem，供后续分析 few-shot 引用 —— 数据闭环核心。
    """
    a = db.get(BugAnalysis, analysis_id)
    if not a:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    a.reviewed = 1
    a.review_result = body.result
    a.reviewed_by = user.username
    a.reviewed_at = datetime.now()

    if body.result == "correct":
        # 采纳 AI 原结论，也沉淀为一条正样本（提升同类日志召回）
        bug_type = body.bug_type or a.bug_type
        root_cause = body.root_cause or a.root_cause
        suggestion = body.suggestion or a.suggestion
    else:
        if not (body.bug_type or body.root_cause):
            raise HTTPException(status_code=400, detail="标记 incorrect 时必须填写纠正后的 bug_type 或 root_cause")
        bug_type = body.bug_type or a.bug_type
        root_cause = body.root_cause or a.root_cause
        suggestion = body.suggestion or a.suggestion
        a.corrected_bug_type = bug_type
        a.corrected_root_cause = root_cause
        a.corrected_suggestion = suggestion

    # 沉淀样本
    run = db.get(Run, a.run_id)
    sample = log_sample_for_feedback(run.error_brief if run else "")
    keywords = "|".join(extract_keywords(sample or (run.error_brief if run else ""), limit=30))
    db.add(FeedbackItem(
        run_id=a.run_id,
        task_name=run.task_name if run else "",
        keywords=keywords,
        sample_log=sample,
        bug_type=bug_type,
        root_cause=root_cause,
        suggestion=suggestion,
        created_by=user.username,
    ))
    _log(db, user.username, "review_analysis",
         f"审核分析#{a.id} run#{a.run_id} 结果={body.result} bug_type={bug_type}")
    db.commit()
    db.refresh(a)
    return a


@router.get("/feedback", response_model=list[dict])
def list_feedback(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    items = db.query(FeedbackItem).order_by(FeedbackItem.id.desc()).limit(limit).all()
    return [
        {
            "id": it.id, "run_id": it.run_id, "task_name": it.task_name,
            "bug_type": it.bug_type, "root_cause": it.root_cause,
            "suggestion": it.suggestion, "created_by": it.created_by,
            "use_count": it.use_count, "created_at": it.created_at,
        }
        for it in items
    ]


@router.delete("/feedback/{item_id}")
def delete_feedback(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    it = db.get(FeedbackItem, item_id)
    if not it:
        raise HTTPException(status_code=404, detail="样本不存在")
    db.delete(it)
    _log(db, user.username, "delete_feedback", f"删除反馈样本#{item_id}")
    db.commit()
    return {"ok": True}
