"""数据模型：用户 / 任务 / 执行记录 / AI 分析 / 人工反馈 / 配置 / 操作日志。"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from .database import Base


def now():
    return datetime.now()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default="user")  # admin / user
    created_at = Column(DateTime, default=now)


class Task(Base):
    """一个自动化任务：绑定一个 GitHub 仓库 + 一组执行配置。"""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    repo_url = Column(String(512), nullable=False)   # GitHub 仓库地址
    branch = Column(String(64), default="main")       # 分支
    command = Column(String(512), default="pytest -q")  # 要执行的命令
    timeout = Column(Integer, default=600)            # 超时秒数
    env_vars = Column(JSON, default=dict)             # 额外环境变量
    schedule_interval_min = Column(Integer, nullable=True)  # 定时调度：每 N 分钟执行；空=仅手动
    enabled = Column(Integer, default=1)              # 是否启用
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Run(Base):
    """一次执行记录。"""

    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True, nullable=False)
    task_name = Column(String(128), default="")
    status = Column(String(16), default="pending")  # pending/running/success/failed/timeout/cancelled/error
    trigger_user = Column(String(64), default="")
    git_commit = Column(String(64), default="")     # 执行时拉到的 commit
    command = Column(String(512), default="")
    exit_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, default=0)
    log_path = Column(String(512), default="")      # 日志文件路径
    log_size = Column(Integer, default=0)           # 日志字节数
    error_brief = Column(Text, default="")          # 失败时的错误摘要（AI 输入用）
    agent_name = Column(String(64), default="")     # 执行节点（Agent 集群）
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


class BugAnalysis(Base):
    """AI / 规则引擎对一次失败执行的分析结果。"""

    __tablename__ = "bug_analyses"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, index=True, nullable=False)
    status = Column(String(16), default="pending")   # pending/analyzing/done/failed
    source = Column(String(16), default="")          # ai / rule
    bug_type = Column(String(128), default="")
    severity = Column(String(16), default="")        # low/medium/high/critical
    root_cause = Column(Text, default="")
    suggestion = Column(Text, default="")
    confidence = Column(Float, default=0.0)          # 0~1
    raw_output = Column(Text, default="")
    # 人工审核闭环
    reviewed = Column(Integer, default=0)            # 0 未审 / 1 已审
    review_result = Column(String(16), default="")   # correct / incorrect
    corrected_bug_type = Column(String(128), default="")
    corrected_root_cause = Column(Text, default="")
    corrected_suggestion = Column(Text, default="")
    reviewed_by = Column(String(64), default="")
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


class FeedbackItem(Base):
    """人工纠正后的样本：沉淀为知识，供后续 AI 分析作为 few-shot 参考。"""

    __tablename__ = "feedback_items"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, default=0)
    task_name = Column(String(128), default="")
    keywords = Column(Text, default="")       # 从日志提取的关键词（用于检索）
    sample_log = Column(Text, default="")     # 日志片段样本
    bug_type = Column(String(128), default="")
    root_cause = Column(Text, default="")
    suggestion = Column(Text, default="")
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=now)
    use_count = Column(Integer, default=0)    # 被引用次数


class Setting(Base):
    """平台级可配置项（页面可改，覆盖 .env 默认值）。"""

    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=now, onupdate=now)


class OperationLog(Base):
    """操作审计日志。"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), default="")
    action = Column(String(64), default="")
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class AgentNode(Base):
    """Agent 执行机节点：注册 / 心跳 / 负载。"""

    __tablename__ = "agent_nodes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    host = Column(String(128), default="")
    status = Column(String(16), default="online")   # online / offline
    capacity = Column(Integer, default=2)            # 最大并行任务数
    running_count = Column(Integer, default=0)       # 当前执行中任务数
    last_heartbeat = Column(DateTime, nullable=True)
    registered_at = Column(DateTime, default=now)


class Device(Base):
    """真机池（Mock 设备池）：设备登记 / 状态 / 占用。"""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    model = Column(String(128), default="")
    platform = Column(String(16), default="Android")  # Android / iOS
    os_version = Column(String(32), default="")
    adb_serial = Column(String(64), default="")        # 预留：真实 adb 序列号
    status = Column(String(16), default="available")   # available / in_use / offline
    owner_run_id = Column(Integer, nullable=True)      # 被哪个执行占用
    remark = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class TestEnv(Base):
    """测试环境管理：测试服 / 预发 / 生产。"""

    __tablename__ = "test_envs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    env_type = Column(String(16), default="测试服")    # 测试服 / 预发 / 生产
    base_url = Column(String(512), default="")
    remark = Column(Text, default="")
    status = Column(String(16), default="active")       # active / inactive
    created_at = Column(DateTime, default=now)


class TestCase(Base):
    """用例库：沉淀可复用的执行用例，一键创建任务并执行。"""

    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    module = Column(String(64), default="")
    priority = Column(String(8), default="P1")          # P0 / P1 / P2 / P3
    command = Column(String(512), default="pytest -q")
    repo_url = Column(String(512), default="")
    branch = Column(String(64), default="main")
    tags = Column(Text, default="")
    enabled = Column(Integer, default=1)
    last_result = Column(String(16), default="")        # success / failed / -
    last_run_id = Column(Integer, nullable=True)
    created_by = Column(String(64), default="")
    created_at = Column(DateTime, default=now)


class Notification(Base):
    """通知中心：失败自动通知等事件落库，渠道为飞书 Webhook（未配置时 mock）。"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    ntype = Column(String(32), default="task_failed")   # task_failed / agent_offline / system
    title = Column(String(256), default="")
    content = Column(Text, default="")
    channel = Column(String(16), default="mock")        # feishu / dingtalk / wecom / smtp / mock
    status = Column(String(16), default="success")      # success / failed / mock
    target = Column(String(256), default="")
    read = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
