"""任务管理接口：CRUD + 触发执行。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..executor import runner
from ..models import OperationLog, Run, Task, User
from ..schemas import RunOut, TaskCreate, TaskOut, TaskUpdate
from ..security import get_current_user

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _log(db: Session, username: str, action: str, detail: str = ""):
    db.add(OperationLog(username=username, action=action, detail=detail))
    db.commit()


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Task).order_by(Task.id.desc()).all()


@router.post("", response_model=TaskOut)
def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = Task(
        name=body.name,
        description=body.description,
        repo_url=body.repo_url,
        branch=body.branch or "main",
        command=body.command or "pytest -q",
        timeout=body.timeout or 600,
        env_vars=body.env_vars or {},
        schedule_interval_min=body.schedule_interval_min,
        enabled=body.enabled,
        created_by=user.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _log(db, user.username, "create_task", f"创建任务 [{task.name}] 仓库={task.repo_url}")
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.put("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(task, k, v)
    task.updated_at = datetime.now()
    db.commit()
    db.refresh(task)
    _log(db, user.username, "update_task", f"更新任务 [{task.name}]")
    return task


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if runner.is_task_running(task_id):
        raise HTTPException(status_code=400, detail="任务正在执行中，不能删除")
    db.delete(task)
    db.commit()
    _log(db, user.username, "delete_task", f"删除任务 [{task.name}]")
    return {"ok": True}


@router.post("/{task_id}/run", response_model=RunOut)
def trigger_run(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not task.enabled:
        raise HTTPException(status_code=400, detail="任务已停用，请先启用")
    if runner.is_task_running(task_id):
        raise HTTPException(status_code=400, detail="该任务已有执行在进行中")

    run = Run(
        task_id=task.id,
        task_name=task.name,
        status="pending",
        trigger_user=user.username,
        command=task.command,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    started = runner.start_run(run.id)
    if not started:
        run.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail="执行启动失败")
    _log(db, user.username, "trigger_run", f"触发任务 [{task.name}] 执行 run#{run.id}")
    return run
