"""真机池（Mock 设备池）接口：设备 CRUD + 占用/释放。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Device, OperationLog, User
from ..schemas import DeviceCreate, DeviceOut, DeviceUpdate
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(
    platform: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Device)
    if platform:
        q = q.filter(Device.platform == platform)
    if status:
        q = q.filter(Device.status == status)
    return q.order_by(Device.id.asc()).all()


@router.post("", response_model=DeviceOut)
def create_device(
    body: DeviceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    dev = Device(**body.model_dump())
    db.add(dev)
    db.commit()
    db.refresh(dev)
    db.add(OperationLog(username=admin.username, action="create_device",
                        detail=f"登记设备 [{dev.name}] {dev.model}"))
    db.commit()
    return dev


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    body: DeviceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(dev, k, v)
    db.commit()
    db.refresh(dev)
    db.add(OperationLog(username=admin.username, action="update_device",
                        detail=f"更新设备 [{dev.name}]"))
    db.commit()
    return dev


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    db.delete(dev)
    db.commit()
    db.add(OperationLog(username=admin.username, action="delete_device",
                        detail=f"删除设备 [{dev.name}]"))
    db.commit()
    return {"ok": True}


@router.post("/{device_id}/claim")
def claim_device(
    device_id: int,
    run_id: int | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """模拟占用设备（如真机自动化执行前抢占设备）。"""
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    if dev.status == "in_use":
        raise HTTPException(status_code=400, detail="设备已被占用")
    dev.status = "in_use"
    dev.owner_run_id = run_id
    db.commit()
    db.refresh(dev)
    return dev


@router.post("/{device_id}/release")
def release_device(
    device_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    dev = db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在")
    dev.status = "available"
    dev.owner_run_id = None
    db.commit()
    db.refresh(dev)
    return dev
