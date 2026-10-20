"""测试环境管理接口：测试服 / 预发 / 生产环境 CRUD。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import OperationLog, TestEnv, User
from ..schemas import TestEnvCreate, TestEnvOut, TestEnvUpdate
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/envs", tags=["envs"])


@router.get("", response_model=list[TestEnvOut])
def list_envs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(TestEnv).order_by(TestEnv.id.asc()).all()


@router.post("", response_model=TestEnvOut)
def create_env(
    body: TestEnvCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env = TestEnv(**body.model_dump())
    db.add(env)
    db.commit()
    db.refresh(env)
    db.add(OperationLog(username=admin.username, action="create_env",
                        detail=f"创建环境 [{env.name}] {env.env_type}"))
    db.commit()
    return env


@router.put("/{env_id}", response_model=TestEnvOut)
def update_env(
    env_id: int,
    body: TestEnvUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env = db.get(TestEnv, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(env, k, v)
    db.commit()
    db.refresh(env)
    db.add(OperationLog(username=admin.username, action="update_env",
                        detail=f"更新环境 [{env.name}]"))
    db.commit()
    return env


@router.delete("/{env_id}")
def delete_env(
    env_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    env = db.get(TestEnv, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    db.delete(env)
    db.commit()
    db.add(OperationLog(username=admin.username, action="delete_env",
                        detail=f"删除环境 [{env.name}]"))
    db.commit()
    return {"ok": True}
