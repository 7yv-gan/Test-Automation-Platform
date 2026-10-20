"""企业级升级端到端 API 验证：登录→节点/设备/环境/用例→一键执行→通知→报告。"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
client = httpx.Client(base_url=BASE, timeout=30)
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


def login():
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    r.raise_for_status()
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


def main():
    token = login()
    check("登录", bool(token))

    # 1. Agent 集群
    agents = client.get("/api/agents").json()
    check("Agent 节点注册", len(agents) >= 3,
          f"nodes={[a['name'] for a in agents]}")
    online = [a for a in agents if a["status"] == "online"]
    check("Agent 在线", len(online) >= 3, f"online={len(online)}")

    # 2. 设备池
    devs = client.get("/api/devices").json()
    if not devs:
        client.post("/api/devices", json={
            "name": "Mi-14-01", "model": "小米14", "platform": "Android",
            "os_version": "Android 15", "adb_serial": "adb-001",
            "remark": "Mock 设备：演示真机池", "status": "available"})
        client.post("/api/devices", json={
            "name": "iPhone-15-01", "model": "iPhone 15", "platform": "iOS",
            "os_version": "iOS 18", "adb_serial": "", "remark": "Mock 设备", "status": "available"})
        devs = client.get("/api/devices").json()
    check("设备登记", len(devs) >= 1, f"devices={len(devs)}")
    if devs:
        d0 = devs[0]
        claimed = client.post(f"/api/devices/{d0['id']}/claim").json()
        check("设备占用", claimed["status"] == "in_use", f"name={d0['name']}")
        released = client.post(f"/api/devices/{d0['id']}/release").json()
        check("设备释放", released["status"] == "available")

    # 3. 测试环境
    envs = client.get("/api/envs").json()
    if not envs:
        client.post("/api/envs", json={
            "name": "自动化测试服", "env_type": "测试服",
            "base_url": "https://test-api.example.com", "remark": "Mock 环境", "status": "active"})
        envs = client.get("/api/envs").json()
    check("测试环境管理", len(envs) >= 1, f"envs={len(envs)}")

    # 4. 用例库 + 一键执行（走完整流水线：拉取 demo 仓库→pytest→失败→AI 分析→通知）
    cases = client.get("/api/cases").json()
    case_id = None
    for c in cases:
        if c["name"] == "登录模块冒烟用例":
            case_id = c["id"]
            break
    if not case_id:
        created = client.post("/api/cases", json={
            "name": "登录模块冒烟用例", "module": "登录", "priority": "P1",
            "command": "pytest -q", "repo_url": "local://demo-repo",
            "branch": "main", "tags": "冒烟,回归", "enabled": 1}).json()
        case_id = created["id"]
    check("用例创建", case_id is not None, f"case_id={case_id}")

    run = client.post(f"/api/cases/{case_id}/run").json()
    run_id = run["id"]
    check("一键执行触发", run_id is not None and run["status"] in ("pending", "running"),
          f"run_id={run_id}")

    # 轮询执行完成
    final = None
    for _ in range(90):
        time.sleep(3)
        final = client.get(f"/api/runs/{run_id}").json()
        if final["status"] in ("success", "failed", "timeout", "error", "cancelled"):
            break
    check("执行完成", final["status"] in ("success", "failed"),
          f"status={final['status']} agent={final['agent_name']} exit={final['exit_code']}")
    check("Agent 节点分配", bool(final.get("agent_name")), f"agent={final.get('agent_name')}")

    # 5. 用例结果回写
    case_now = [c for c in client.get("/api/cases").json() if c["id"] == case_id][0]
    check("用例结果回写", case_now["last_run_id"] == run_id and case_now["last_result"] in ("success", "failed"),
          f"last_result={case_now['last_result']}")

    # 6. 通知中心（demo 仓库 1 失败 1 通过 -> 失败通知）
    notifs = client.get("/api/notifications?limit=50").json()
    task_failed = [n for n in notifs if n["ntype"] == "task_failed" and n["title"].find(f"Run#{run_id}") >= 0]
    check("失败自动通知", len(task_failed) >= 1,
          f"found={len(task_failed)} channel={task_failed[0]['channel'] if task_failed else '-'} status={task_failed[0]['status'] if task_failed else '-'}")
    unread = client.get("/api/notifications/unread-count").json()
    check("未读计数", unread["count"] >= 1, f"unread={unread['count']}")
    if task_failed:
        client.post(f"/api/notifications/{task_failed[0]['id']}/read")
        n2 = client.get("/api/notifications/unread-count").json()
        check("标记已读", n2["count"] == unread["count"] - 1)

    # 7. 报告中心
    ov = client.get("/api/reports/overview?days=14").json()
    check("报告总览", "pass_rate" in ov and "avg_duration_s" in ov,
          f"runs={ov['total_runs']} pass={ov['pass_rate']}% avg={ov['avg_duration_s']}s")
    trend = client.get("/api/reports/trend?days=14").json()
    check("报告趋势", isinstance(trend, list) and len(trend) == 14)
    recent = client.get("/api/reports/recent?limit=30").json()
    check("最近报告", isinstance(recent, list) and len(recent) >= 1)

    # 8. 节点负载恢复
    time.sleep(1)
    agents2 = client.get("/api/agents").json()
    total_running = sum(a["running_count"] for a in agents2)
    check("节点负载恢复", total_running == 0, f"running_total={total_running}")

    # 9. 节点下线告警
    target = [a for a in agents2 if a["status"] == "online"][0]
    off = client.post(f"/api/agents/{target['id']}/offline").json()
    check("节点下线", off["status"] == "offline")
    agent_notifs = [n for n in client.get("/api/notifications?limit=50").json() if n["ntype"] == "agent_offline"]
    check("节点离线告警", len(agent_notifs) >= 1)
    client.post(f"/api/agents/{target['id']}/online")

    # 10. 设置页通知渠道配置
    cfg = client.get("/api/settings").json()
    check("设置含通知渠道", "feishu_webhook" in cfg)

    failed = [r for r in results if not r[1]]
    print(f"\n===== 结果: {len(results) - len(failed)}/{len(results)} 通过 =====")
    if failed:
        print("失败项:", [r[0] for r in failed])
        sys.exit(1)


if __name__ == "__main__":
    main()
