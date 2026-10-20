"""API 冒烟测试：登录 -> 建任务 -> 触发执行 -> 轮询结果 -> 查看分析。"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000"


def req(method, path, token=None, body=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            return resp.status, payload if raw else json.loads(payload)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


# 1. 登录
code, data = req("POST", "/api/auth/login", body={"username": "admin", "password": "admin123"})
assert code == 200, f"login failed: {data}"
token = data["access_token"]
print("[OK] 登录成功 role =", data["role"])

# 2. 建任务（用本地演示仓库，无外网也能完整验证流水线；包含 1 个失败用例触发 AI 分析）
code, task = req("POST", "/api/tasks", token, {
    "name": "冒烟测试-演示任务",
    "description": "API 冒烟测试自动创建（本地演示仓库，含失败用例）",
    "repo_url": r"E:\自动化平台搭建\scripts\demo-repo",
    "branch": "master",
    "command": "python -m pytest -q",
    "timeout": 120,
    "env_vars": {},
    "enabled": 1,
})
assert code == 200, f"create task failed: {data}"
task_id = task["id"]
print("[OK] 任务创建成功 id =", task_id, "->", task["name"])

# 3. 触发执行
code, run = req("POST", f"/api/tasks/{task_id}/run", token)
assert code == 200, f"trigger failed: {data}"
run_id = run["id"]
print("[OK] 执行触发成功 run#", run_id)

# 4. 轮询执行状态
for _ in range(40):
    time.sleep(3)
    code, run = req("GET", f"/api/runs/{run_id}", token)
    if run["status"] in ("success", "failed", "timeout", "error", "cancelled"):
        break
print("[RESULT] status =", run["status"], "| exit_code =", run["exit_code"],
      "| duration_ms =", run["duration_ms"], "| commit =", run["git_commit"])

# 5. 查看日志
code, logs = req("GET", f"/api/runs/{run_id}/logs?offset=0", token, raw=True)
print("[LOG] 日志片段:")
print(logs[:800])

# 6. 查看分析结果
time.sleep(2)
code, analysis = req("GET", f"/api/runs/{run_id}/analysis", token)
if analysis:
    print("[AI] 分析 source =", analysis["source"], "| bug_type =", analysis["bug_type"],
          "| confidence =", analysis["confidence"])
else:
    print("[AI] 无分析记录（任务成功时正常）")

# 7. 看板
code, ov = req("GET", "/api/dashboard/overview", token)
print("[DASH] overview =", json.dumps(ov, ensure_ascii=False)[:400])
print("\n=== 冒烟测试完成 ===")
