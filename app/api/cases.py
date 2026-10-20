"""用例库接口：用例 CRUD + 一键创建任务执行 + 结果回写。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..executor import runner
from ..models import OperationLog, Run, Task, TestCase, User
from ..schemas import RunOut, TestCaseCreate, TestCaseOut, TestCaseUpdate
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("", response_model=list[TestCaseOut])
def list_cases(
    module: str | None = None,
    priority: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(TestCase)
    if module:
        q = q.filter(TestCase.module == module)
    if priority:
        q = q.filter(TestCase.priority == priority)
    return q.order_by(TestCase.id.desc()).all()


@router.post("", response_model=TestCaseOut)
def create_case(
    body: TestCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = TestCase(**body.model_dump(), created_by=user.username)
    db.add(case)
    db.commit()
    db.refresh(case)
    db.add(OperationLog(username=user.username, action="create_case",
                        detail=f"新建用例 [{case.name}] P{case.priority}"))
    db.commit()
    return case


@router.put("/{case_id}", response_model=TestCaseOut)
def update_case(
    case_id: int,
    body: TestCaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = db.get(TestCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(case, k, v)
    db.commit()
    db.refresh(case)
    db.add(OperationLog(username=user.username, action="update_case",
                        detail=f"更新用例 [{case.name}]"))
    db.commit()
    return case


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    case = db.get(TestCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    db.delete(case)
    db.commit()
    db.add(OperationLog(username=user.username, action="delete_case",
                        detail=f"删除用例 [{case.name}]"))
    db.commit()
    return {"ok": True}


@router.post("/{case_id}/run", response_model=RunOut)
def run_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """一键执行：由用例动态生成任务并触发，执行后回写用例最近结果。"""
    case = db.get(TestCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="用例不存在")
    if not case.enabled:
        raise HTTPException(status_code=400, detail="用例已停用")
    if not case.command:
        raise HTTPException(status_code=400, detail="用例缺少执行命令")
    if runner.is_task_running(case.id):
        raise HTTPException(status_code=400, detail="该用例已有执行在进行中")

    # 用例即任务：repo_url 为空时使用平台默认演示仓库
    repo_url = case.repo_url or "local://demo-repo"
    task = Task(
        name=f"[用例] {case.name}",
        description=f"由用例库 #{case.id} 一键执行生成",
        repo_url=repo_url,
        branch=case.branch or "main",
        command=case.command,
        timeout=600,
        env_vars={"TEST_CASE_ID": str(case.id), "TEST_CASE_NAME": case.name},
        created_by=user.username,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    # local://demo-repo 在 sync_repo 中会映射到本地演示仓库（见 github_client）
    run = Run(
        task_id=task.id,
        task_name=task.name,
        status="pending",
        trigger_user=user.username,
        command=case.command,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    started = runner.start_run(run.id)
    if not started:
        run.status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail="执行启动失败")
    db.add(OperationLog(username=user.username, action="run_case",
                        detail=f"一键执行用例 [{case.name}] run#{run.id}"))
    db.commit()
    return run


def refresh_case_result(db: Session, run: Run) -> None:
    """执行结束后回写用例最近结果（由任务侧回调或报告中心兜底扫描）。"""
    # 通过任务描述反查用例
    if not run.task_name.startswith("[用例] "):
        return
    case = (
        db.query(TestCase)
        .filter(TestCase.name == run.task_name[len("[用例] "):])
        .order_by(TestCase.id.desc())
        .first()
    )
    if not case:
        return
    case.last_result = "success" if run.status == "success" else "failed"
    case.last_run_id = run.id
    db.commit()
