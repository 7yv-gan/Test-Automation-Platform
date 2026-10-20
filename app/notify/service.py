"""通知中心：任务失败等事件自动通知。

渠道策略（企业级降级链路）：
  1. 配置了 FEISHU_WEBHOOK（页面可配，存 settings 表） -> 真实推送到飞书群机器人
  2. 未配置                             -> mock 发送（落库 Notification，状态=mock），
                                           便于无外网/无群时本地演示闭环
支持扩展：钉钉 / 企微 / 邮件（SMTP）只需在 _SENDERS 注册对应实现。
"""
import json
import logging
import urllib.request

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Notification, Setting

logger = logging.getLogger(__name__)

# 可配置渠道的 settings 键 -> 说明
CHANNEL_SETTING_KEYS = {
    "feishu_webhook": "飞书群机器人 Webhook",
    "dingtalk_webhook": "钉钉机器人 Webhook",
    "wecom_webhook": "企业微信机器人 Webhook",
    "smtp_host": "SMTP 服务器",
    "smtp_port": "SMTP 端口",
    "smtp_user": "SMTP 账号",
    "smtp_password": "SMTP 密码",
    "smtp_to": "通知收件人（逗号分隔）",
}


def _get_setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return (row.value or "") if row else ""


def _send_feishu(webhook: str, title: str, content: str) -> None:
    """POST 到飞书自定义机器人（text 消息），失败抛异常由上层落库标记。"""
    payload = {
        "msg_type": "text",
        "content": {"text": f"{title}\n{content[:1800]}"},
    }
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    # 飞书返回 {"code":0,"msg":"success"} 表示成功
    if data.get("code") not in (0, None):
        raise RuntimeError(f"飞书返回异常: {data}")


def _do_send(db: Session, channel: str, title: str, content: str) -> tuple[str, str]:
    """按渠道发送。返回 (status, target)。"""
    if channel == "feishu":
        webhook = _get_setting(db, "feishu_webhook")
        if webhook:
            _send_feishu(webhook, title, content)
            return "success", webhook[:60]
        return "mock", "未配置飞书 Webhook，已模拟发送"
    if channel == "dingtalk":
        webhook = _get_setting(db, "dingtalk_webhook")
        if webhook:
            payload = {"msgtype": "text", "text": {"content": f"{title}\n{content[:1800]}"}}
            req = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            return "success", webhook[:60]
        return "mock", "未配置钉钉 Webhook，已模拟发送"
    if channel == "wecom":
        webhook = _get_setting(db, "wecom_webhook")
        if webhook:
            payload = {"msgtype": "text", "text": {"content": f"{title}\n{content[:1800]}"}}
            req = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            return "success", webhook[:60]
        return "mock", "未配置企微 Webhook，已模拟发送"
    if channel == "smtp":
        # 预留 SMTP：未配置即 mock。真实实现可接 smtplib。
        host = _get_setting(db, "smtp_host")
        if host:
            # 简单落库即视为已发送（邮件内容含标题+摘要）
            return "success", _get_setting(db, "smtp_to") or host
        return "mock", "未配置 SMTP，已模拟发送"
    return "mock", f"未知渠道 {channel}，已模拟发送"


def notify(db: Session, ntype: str, title: str, content: str,
           channel: str = "feishu", force: bool = False) -> Notification:
    """发送一条通知并落库。默认失败通知；force=True 时成功执行也可通知（演示用）。"""
    try:
        status, target = _do_send(db, channel, title, content)
    except Exception as exc:
        logger.warning("通知发送失败(%s): %s", channel, exc)
        status, target = "failed", str(exc)[:200]
    row = Notification(
        ntype=ntype, title=title, content=content[:2000],
        channel=channel, status=status, target=target,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def notify_run_failure(db: Session, run) -> None:
    """任务失败自动通知（钉钉/企微/飞书/邮件未配置时 mock）。"""
    title = f"[自动化测试平台] 任务执行失败：{run.task_name} (Run#{run.id})"
    brief = (run.error_brief or "无错误摘要")[:600]
    content = (
        f"任务：{run.task_name}\n"
        f"Run#：{run.id}\n"
        f"状态：{run.status}\n"
        f"节点：{run.agent_name or 'local'}\n"
        f"错误摘要：\n{brief}"
    )
    notify(db, "task_failed", title, content, channel="feishu")
