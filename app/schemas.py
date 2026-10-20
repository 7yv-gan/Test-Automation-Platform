"""Pydantic 请求/响应模型。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


# ---------- User ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = "user"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- Task ----------
class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    repo_url: str = Field(min_length=5, max_length=512)
    branch: str = "main"
    command: str = "pytest -q"
    timeout: int = 600
    env_vars: dict[str, str] = {}
    schedule_interval_min: Optional[int] = None
    enabled: int = 1


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repo_url: Optional[str] = None
    branch: Optional[str] = None
    command: Optional[str] = None
    timeout: Optional[int] = None
    env_vars: Optional[dict[str, str]] = None
    schedule_interval_min: Optional[int] = None
    enabled: Optional[int] = None


class TaskOut(BaseModel):
    id: int
    name: str
    description: str
    repo_url: str
    branch: str
    command: str
    timeout: int
    env_vars: dict[str, str]
    schedule_interval_min: Optional[int] = None
    enabled: int
    created_by: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- Run ----------
class RunOut(BaseModel):
    id: int
    task_id: int
    task_name: str
    status: str
    trigger_user: str
    git_commit: str
    command: str
    exit_code: Optional[int] = None
    duration_ms: int
    log_size: int
    error_brief: str
    agent_name: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- AI Analysis ----------
class AnalysisOut(BaseModel):
    id: int
    run_id: int
    status: str
    source: str
    bug_type: str
    severity: str
    root_cause: str
    suggestion: str
    confidence: float
    reviewed: int
    review_result: str
    corrected_bug_type: str
    corrected_root_cause: str
    corrected_suggestion: str
    reviewed_by: str
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReviewRequest(BaseModel):
    result: str = Field(pattern="^(correct|incorrect)$")
    bug_type: str = ""
    root_cause: str = ""
    suggestion: str = ""


# ---------- Settings ----------
class SettingsUpdate(BaseModel):
    updates: dict[str, Any]


class OperationLogOut(BaseModel):
    id: int
    username: str
    action: str
    detail: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- Agent 集群 ----------
class AgentNodeOut(BaseModel):
    id: int
    name: str
    host: str
    status: str
    capacity: int
    running_count: int
    last_heartbeat: Optional[datetime] = None
    registered_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- 设备池 ----------
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    model: str = ""
    platform: str = "Android"
    os_version: str = ""
    adb_serial: str = ""
    status: str = "available"
    remark: str = ""


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    platform: Optional[str] = None
    os_version: Optional[str] = None
    adb_serial: Optional[str] = None
    status: Optional[str] = None
    remark: Optional[str] = None


class DeviceOut(BaseModel):
    id: int
    name: str
    model: str
    platform: str
    os_version: str
    adb_serial: str
    status: str
    owner_run_id: Optional[int] = None
    remark: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- 测试环境 ----------
class TestEnvCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    env_type: str = "测试服"
    base_url: str = ""
    remark: str = ""
    status: str = "active"


class TestEnvUpdate(BaseModel):
    name: Optional[str] = None
    env_type: Optional[str] = None
    base_url: Optional[str] = None
    remark: Optional[str] = None
    status: Optional[str] = None


class TestEnvOut(BaseModel):
    id: int
    name: str
    env_type: str
    base_url: str
    remark: str
    status: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- 用例库 ----------
class TestCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    module: str = ""
    priority: str = "P1"
    command: str = "pytest -q"
    repo_url: str = ""
    branch: str = "main"
    tags: str = ""
    enabled: int = 1


class TestCaseUpdate(BaseModel):
    name: Optional[str] = None
    module: Optional[str] = None
    priority: Optional[str] = None
    command: Optional[str] = None
    repo_url: Optional[str] = None
    branch: Optional[str] = None
    tags: Optional[str] = None
    enabled: Optional[int] = None


class TestCaseOut(BaseModel):
    id: int
    name: str
    module: str
    priority: str
    command: str
    repo_url: str
    branch: str
    tags: str
    enabled: int
    last_result: str
    last_run_id: Optional[int] = None
    created_by: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------- 通知中心 ----------
class NotificationOut(BaseModel):
    id: int
    ntype: str
    title: str
    content: str
    channel: str
    status: str
    target: str
    read: int
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
