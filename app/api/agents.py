"""Agent 执行机集群接口：节点列表 / 上下线模拟 / 负载。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents import worker as agent_worker
from ..database import get_db
from ..models import AgentNode, OperationLog, User
from ..schemas import AgentNodeOut
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentNodeOut])
def list_agents(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(AgentNode).order_by(AgentNode.id.asc()).all()


@router.post("/{agent_id}/offline", response_model=AgentNodeOut)
def offline_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """模拟节点离线：立即停止参与任务分配，并发送通知告警。"""
    node = db.get(AgentNode, agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    node.status = "offline"
    node.last_heartbeat = datetime.now()
    db.add(OperationLog(username=admin.username, action="agent_offline",
                        detail=f"手动下线节点 {node.name}"))
    db.commit()
    db.refresh(node)
    # 离线告警 -> 通知中心（未配置飞书则 mock）
    try:
        from ..notify.service import notify
        notify(db, "agent_offline", f"[自动化测试平台] Agent 节点离线：{node.name}",
               f"节点 {node.name}（{node.host}）已下线，任务将不再分配至该节点。",
               channel="feishu")
    except Exception:
        pass
    return node


@router.post("/{agent_id}/online", response_model=AgentNodeOut)
def online_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """模拟节点上线/恢复。"""
    node = db.get(AgentNode, agent_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    node.status = "online"
    node.last_heartbeat = datetime.now()
    db.add(OperationLog(username=admin.username, action="agent_online",
                        detail=f"上线节点 {node.name}"))
    db.commit()
    db.refresh(node)
    return node


@router.post("/register")
def register_agent(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """真实 Worker 的注册入口（演示环境：确保 3 个模拟节点存在）。"""
    agent_worker.ensure_nodes()
    return {"ok": True, "message": "节点注册成功（本机模拟集群）"}
