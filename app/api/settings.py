"""平台设置接口：LLM / GitHub / 执行参数（页面可改，持久化到 settings 表）。"""
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..database import get_db
from ..models import OperationLog, Setting, User
from ..schemas import SettingsUpdate
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 可配置键与默认值（脱敏展示）
_KEYS = {
    "llm_base_url": ("LLM_BASE_URL", cfg.LLM_BASE_URL),
    "llm_api_key": ("LLM_API_KEY", cfg.LLM_API_KEY),
    "llm_model": ("LLM_MODEL", cfg.LLM_MODEL),
    "github_token": ("GITHUB_TOKEN", cfg.GITHUB_TOKEN),
    "max_concurrent_runs": ("MAX_CONCURRENT_RUNS", str(cfg.MAX_CONCURRENT_RUNS)),
    "default_timeout": ("DEFAULT_TIMEOUT", str(cfg.DEFAULT_TIMEOUT)),
    "llm_max_log_chars": ("LLM_MAX_LOG_CHARS", str(cfg.LLM_MAX_LOG_CHARS)),
    # 通知中心渠道（页面可配，未配置时自动 mock）
    "feishu_webhook": ("FEISHU_WEBHOOK", cfg.FEISHU_WEBHOOK),
    "dingtalk_webhook": ("DINGTALK_WEBHOOK", cfg.DINGTALK_WEBHOOK),
    "wecom_webhook": ("WECOM_WEBHOOK", cfg.WECOM_WEBHOOK),
    "smtp_host": ("SMTP_HOST", cfg.SMTP_HOST),
    "smtp_port": ("SMTP_PORT", cfg.SMTP_PORT),
    "smtp_user": ("SMTP_USER", cfg.SMTP_USER),
    "smtp_password": ("SMTP_PASSWORD", cfg.SMTP_PASSWORD),
    "smtp_to": ("SMTP_TO", cfg.SMTP_TO),
}

_SECRET_KEYS = {"llm_api_key", "github_token", "feishu_webhook", "dingtalk_webhook", "wecom_webhook", "smtp_password"}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


@router.get("")
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stored = {s.key: s.value for s in db.query(Setting).all()}
    result = {}
    for key, (env_key, env_default) in _KEYS.items():
        value = stored.get(key, env_default)
        result[key] = _mask(value) if key in _SECRET_KEYS and value else value
        if key in _SECRET_KEYS:
            result[f"{key}_configured"] = bool(value)
    return result


@router.put("")
def update_settings(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    changed = []
    for key, value in body.updates.items():
        if key not in _KEYS:
            raise HTTPException(status_code=400, detail=f"不支持的配置项: {key}")
        row = db.get(Setting, key)
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
        # 同步到进程内配置，立即生效（覆盖 .env 默认值）
        env_key = _KEYS[key][0]
        if hasattr(cfg, env_key):
            try:
                setattr(cfg, env_key, type(getattr(cfg, env_key))(str(value)))
            except ValueError:
                pass
        changed.append(key)
    db.add(OperationLog(username=admin.username, action="update_settings", detail=", ".join(changed)))
    db.commit()
    return {"ok": True, "changed": changed}
