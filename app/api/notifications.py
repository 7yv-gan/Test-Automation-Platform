"""通知中心接口：通知列表 / 未读数 / 已读 / 全部已读 / 重发。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..schemas import NotificationOut
from ..security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    ntype: str | None = None,
    unread_only: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Notification)
    if ntype:
        q = q.filter(Notification.ntype == ntype)
    if unread_only:
        q = q.filter(Notification.read == 0)
    return q.order_by(Notification.id.desc()).limit(limit).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": db.query(Notification).filter(Notification.read == 0).count()}


@router.post("/{notify_id}/read")
def mark_read(
    notify_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.get(Notification, notify_id)
    if not row:
        raise HTTPException(status_code=404, detail="通知不存在")
    row.read = 1
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.read == 0).update({"read": 1})
    db.commit()
    return {"ok": True}


@router.post("/{notify_id}/resend")
def resend_notify(
    notify_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重新发送：mock 或真实渠道重推，用于演示人工触发通知。"""
    row = db.get(Notification, notify_id)
    if not row:
        raise HTTPException(status_code=404, detail="通知不存在")
    from ..notify.service import notify
    new = notify(db, row.ntype, row.title, row.content, channel=row.channel)
    return {"ok": True, "new_id": new.id, "status": new.status}
