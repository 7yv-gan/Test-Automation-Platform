"""执行引擎：异步拉取代码 -> 执行命令 -> 流式日志 -> 结果判定 -> 触发 AI 分析。

并发控制：全局信号量限制同时执行的任务数；同一任务不允许并发执行。
日志：写入 data/logs/run_{id}.log，前端按 offset 轮询增量读取。
"""
import logging
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Run, Task
from .github_client import sync_repo
from ..agents import worker as agent_worker

logger = logging.getLogger(__name__)

_semaphore = threading.BoundedSemaphore(settings.MAX_CONCURRENT_RUNS)
_lock = threading.Lock()
_running_by_task: dict[int, int] = {}  # task_id -> run_id


def is_task_running(task_id: int) -> bool:
    with _lock:
        return task_id in _running_by_task


def _log_line(stream, line: str):
    ts = datetime.now().strftime("%H:%M:%S")
    stream.write(f"[{ts}] {line}\n")
    stream.flush()


def _run_shell(command: str, cwd: Path, env: dict, log_path: Path, timeout: int):
    """执行命令，流式写日志。返回 (exit_code, error_brief)。

    输出读取放在独立线程，经队列传递给主循环；主循环按剩余超时轮询——
    避免进程长时间无输出时 readline 阻塞导致超时机制失效。
    """
    merged_env = os.environ.copy()
    merged_env.update(env)
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=str(cwd),
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    out_q: "queue.Queue[bytes | None]" = queue.Queue()

    def _reader():
        assert proc.stdout is not None
        try:
            for raw in iter(proc.stdout.readline, b""):
                out_q.put(raw)
        finally:
            out_q.put(None)  # 流结束哨兵

    threading.Thread(target=_reader, daemon=True, name="run-reader").start()

    brief_lines: list[str] = []
    brief_max = 60
    timed_out = False
    deadline = time.monotonic() + timeout
    with open(log_path, "w", encoding="utf-8", errors="replace") as f:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                proc.kill()
                _log_line(f, "[执行] 超过超时时间，已强制终止")
                break
            try:
                raw = out_q.get(timeout=min(0.5, max(remaining, 0.05)))
            except queue.Empty:
                continue
            if raw is None:
                break
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if text:
                _log_line(f, text)
                brief_lines.append(text)
                if len(brief_lines) > brief_max:
                    brief_lines.pop(0)
        # 兜底：等进程完全退出
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

    exit_code = proc.returncode
    if timed_out:
        exit_code = -9
    error_brief = "\n".join(brief_lines[-brief_max:]) if exit_code not in (0, None) else ""
    return exit_code, error_brief


def _mark(db: Session, run: Run, **fields):
    for k, v in fields.items():
        setattr(run, k, v)
    db.commit()


def execute_run(run_id: int):
    """在后台线程中执行一次任务（完整流水线）。"""
    with _semaphore:
        db = SessionLocal()
        try:
            run = db.get(Run, run_id)
            if not run:
                logger.error("run %s 不存在", run_id)
                return
            task_id = run.task_id  # 先取出，保证 finally 中清理互斥锁不因提前 return 而 NameError
            task = db.get(Task, run.task_id)
            if not task:
                _mark(db, run, status="error", error_brief="任务已被删除", finished_at=datetime.now())
                return

            started = datetime.now()
            # Agent 集群：分配执行节点（最少负载），失败时节点可追溯
            agent_name = agent_worker.pick_agent(db)
            _mark(db, run, status="running", started_at=started, agent_name=agent_name)
            log_path = settings.LOGS_DIR / f"run_{run_id}.log"
            _mark(db, run, log_path=str(log_path))

            # 1. 拉取代码
            repo_dir = settings.REPOS_DIR / f"task_{task.id}"
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    _log_line(f, f"==> 拉取代码: {task.repo_url} (分支: {task.branch})")
                commit = sync_repo(task.repo_url, task.branch, repo_dir)
                with open(log_path, "a", encoding="utf-8") as f:
                    _log_line(f, f"==> 拉取完成，commit: {commit[:12]}")
                _mark(db, run, git_commit=commit[:12], task_name=task.name, command=task.command)
            except Exception as exc:
                with open(log_path, "a", encoding="utf-8") as f:
                    _log_line(f, f"[拉取失败] {exc}")
                _mark(
                    db, run, status="error", exit_code=-1,
                    error_brief=f"[拉取失败] {exc}",
                    finished_at=datetime.now(),
                    duration_ms=int((datetime.now() - started).total_seconds() * 1000),
                )
                _finish_then_analyze(run_id, log_path)
                return

            # 2. 执行命令
            env = dict(task.env_vars or {})
            exit_code, brief = _run_shell(
                task.command, repo_dir, env, log_path, timeout=task.timeout or settings.DEFAULT_TIMEOUT
            )
            duration_ms = int((datetime.now() - started).total_seconds() * 1000)
            status = "success" if exit_code == 0 else ("timeout" if exit_code == -9 else "failed")
            _mark(
                db, run,
                status=status, exit_code=exit_code, duration_ms=duration_ms,
                finished_at=datetime.now(),
                error_brief=brief,
                log_size=log_path.stat().st_size if log_path.exists() else 0,
            )

            # 3. 失败 -> 触发 AI 分析 + 失败自动通知
            if status != "success":
                _trigger_analysis(run_id, log_path, brief)
                try:
                    from ..notify.service import notify_run_failure
                    notify_run_failure(db, run)
                except Exception as exc:
                    logger.warning("失败通知发送异常: %s", exc)

            # 4. 用例库结果回写（一键执行生成的用例任务）
            try:
                from ..api.cases import refresh_case_result
                refresh_case_result(db, run)
            except Exception as exc:
                logger.warning("用例结果回写异常: %s", exc)
        finally:
            with _lock:
                _running_by_task.pop(task_id, None)
            # 释放节点负载
            try:
                agent_worker.release_agent(run.agent_name if 'run' in dir() else None)
            except Exception:
                pass
            db.close()


def _finish_then_analyze(run_id: int, log_path: Path):
    """拉取失败分支的收尾 + 分析。"""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run:
            run.log_size = log_path.stat().st_size if log_path.exists() else 0
            db.commit()
            if run.error_brief:
                _trigger_analysis(run_id, log_path, run.error_brief)
    finally:
        db.close()


def _trigger_analysis(run_id: int, log_path: Path, brief: str):
    """延迟导入避免循环依赖；分析在独立线程执行，不阻塞执行流水线。"""
    try:
        from ..ai.analyzer import analyze_run_async
        analyze_run_async(run_id, log_path, brief)
    except Exception as exc:
        logger.error("触发 AI 分析失败: %s", exc)


def start_run(run_id: int) -> bool:
    """校验并发约束并启动后台执行线程。返回是否成功启动。"""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return False
        with _lock:
            if run.task_id in _running_by_task:
                return False
            _running_by_task[run.task_id] = run_id
    finally:
        db.close()
    threading.Thread(target=execute_run, args=(run_id,), daemon=True, name=f"run-{run_id}").start()
    return True
