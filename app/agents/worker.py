"""Agent 执行机集群（本机多 Worker 模拟多节点）。

企业级形态：Master 调度器 + 分布在不同机器上的 Agent Worker，
每个 Worker 通过心跳向 Master 注册并上报负载，Master 按最少负载抢占分配任务。

本演示实现：
  - 启动时自动注册 3 个模拟节点（agent-01/02/03，host 取本机主机名）
  - 后台心跳线程：每 30 秒刷新所有节点 last_heartbeat（节点离线则自动剔除出调度池）
  - 任务分配由 runner 调用 pick_agent() 完成（round-robin + 最少负载）
  - 节点离线/上线可通过 API 模拟，离线会触发通知中心告警
"""
import logging
import platform
import threading
import time
from datetime import datetime, timedelta

from ..config import settings
from ..database import SessionLocal
from ..models import AgentNode, OperationLog

logger = logging.getLogger(__name__)

_STOP = threading.Event()
SIMULATED_NODES = [
    {"name": "agent-01", "capacity": 3},
    {"name": "agent-02", "capacity": 2},
    {"name": "agent-03", "capacity": 2},
]

# 保证同一时刻只有一个线程在做节点分配
_pick_lock = threading.Lock()


def ensure_nodes() -> None:
    """启动时注册模拟节点（幂等）。"""
    db = SessionLocal()
    try:
        for node in SIMULATED_NODES:
            row = db.query(AgentNode).filter(AgentNode.name == node["name"]).first()
            if not row:
                db.add(AgentNode(
                    name=node["name"],
                    host=platform.node(),
                    status="online",
                    capacity=node["capacity"],
                    running_count=0,
                    last_heartbeat=datetime.now(),
                ))
                logger.info("注册 Agent 节点: %s", node["name"])
        db.commit()
    finally:
        db.close()


def pick_agent(db) -> str:
    """分配一个在线且有空闲容量的节点（最少负载优先）。无可用节点返回 'local' 本机兜底。"""
    with _pick_lock:
        agents = (
            db.query(AgentNode)
            .filter(AgentNode.status == "online")
            .order_by(AgentNode.running_count.asc(), AgentNode.id.asc())
            .all()
        )
        for a in agents:
            if a.running_count < a.capacity:
                a.running_count += 1
                db.commit()
                return a.name
        return "local"


def release_agent(agent_name: str) -> None:
    """执行结束后释放节点负载。"""
    if not agent_name or agent_name == "local":
        return
    db = SessionLocal()
    try:
        row = db.query(AgentNode).filter(AgentNode.name == agent_name).first()
        if row:
            row.running_count = max(0, (row.running_count or 0) - 1)
            db.commit()
    finally:
        db.close()


def _heartbeat_once() -> None:
    """刷新心跳；节点超过 90 秒无心跳判离线（模拟时可手动置离线演示）。"""
    db = SessionLocal()
    try:
        threshold = datetime.now() - timedelta(seconds=90)
        offline = (
            db.query(AgentNode)
            .filter(AgentNode.status == "online", AgentNode.last_heartbeat.isnot(None))
            .filter(AgentNode.last_heartbeat < threshold)
            .all()
        )
        for node in offline:
            node.status = "offline"
            db.add(OperationLog(username="system", action="agent_offline",
                                detail=f"节点 {node.name} 心跳超时，已标记离线"))
            logger.warning("节点 %s 心跳超时，已离线", node.name)
        for node in db.query(AgentNode).all():
            node.last_heartbeat = datetime.now()
        db.commit()
    except Exception as exc:
        logger.exception("心跳刷新异常: %s", exc)
    finally:
        db.close()


def _loop() -> None:
    logger.info("Agent 集群心跳线程已启动（每 30 秒一次）")
    while not _STOP.wait(30):
        try:
            _heartbeat_once()
        except Exception:
            logger.exception("Agent 心跳循环异常")


def start_agent_cluster() -> None:
    ensure_nodes()
    threading.Thread(target=_loop, daemon=True, name="agent-heartbeat").start()
