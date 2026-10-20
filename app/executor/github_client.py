"""GitHub 代码拉取：支持公开/私有仓库 clone、增量更新、分支切换、本地演示仓库。"""
import base64
import logging
import shutil
import subprocess
from pathlib import Path

from ..config import settings

logger = logging.getLogger(__name__)


def _auth_header(token: str) -> list[str]:
    """私有仓库：通过 http.extraheader 注入 basic 认证（避免 URL 泄露 token）。"""
    if not token:
        return []
    token_b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {token_b64}"]


def _git(*args: str, cwd: Path | None = None, timeout: int | None = None) -> str:
    cmd = ["git", *args]
    result = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
        timeout=timeout or settings.GIT_TIMEOUT, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} 失败: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def _remote_url(repo_url: str) -> str:
    """应用镜像前缀（本地路径 / file:// 不应用镜像）。"""
    prefix = settings.GIT_CLONE_PREFIX.strip()
    if not prefix:
        return repo_url
    low = repo_url.lower()
    if low.startswith(("file:", "http://localhost", "https://localhost")) or len(repo_url) > 2 and repo_url[1] == ":":
        return repo_url
    return prefix.rstrip("/") + "/" + repo_url


def _local_source(repo_url: str) -> Path | None:
    """本地演示仓库：local://xxx 映射到 scripts/xxx；Windows 盘符路径直接用。"""
    if repo_url.startswith("local://"):
        rel = repo_url[len("local://"):].lstrip("/\\")
        p = settings.BASE_DIR / "scripts" / rel
        if p.exists():
            return p
        logger.warning("本地演示仓库不存在: %s", p)
        return None
    if len(repo_url) > 2 and repo_url[1] == ":":
        p = Path(repo_url)
        if p.exists():
            return p
    return None


def sync_repo(repo_url: str, branch: str, dest: Path) -> str:
    """把仓库同步到 dest，返回当前 commit。dest 不存在则 clone，存在则 fetch+checkout。

    本地演示仓库（local://demo-repo 或盘符路径）：直接复制，保证离线可演示。
    """
    local = _local_source(repo_url)
    if local is not None:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # 忽略源仓库的 .git（GitHub 上传时 demo-repo/.git 不入库）；
        # 目标若无 git 元数据则自动初始化，保证 commit 溯源可用
        shutil.copytree(local, dest, ignore=shutil.ignore_patterns(".git"))
        if not (dest / ".git").exists():
            _git("init", cwd=dest)
            _git("add", ".", cwd=dest)
            _git("commit", "-m", "init demo repo (auto)", cwd=dest)
        return _git("rev-parse", "HEAD", cwd=dest)

    token = settings.GITHUB_TOKEN
    auth = _auth_header(token)
    branch = branch or "main"
    remote = _remote_url(repo_url)

    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        if token:
            _git(*auth, "clone", "--depth", "1", "--branch", branch, remote, str(dest), timeout=settings.GIT_TIMEOUT)
        else:
            _git("clone", "--depth", "1", "--branch", branch, remote, str(dest), timeout=settings.GIT_TIMEOUT)
    else:
        if not (dest / ".git").exists():
            raise RuntimeError(f"{dest} 目录已存在但不是 Git 仓库，请删除后重试")
        try:
            _git("fetch", "origin", branch, cwd=dest)
            _git("checkout", branch, cwd=dest)
            _git("reset", "--hard", f"origin/{branch}", cwd=dest)
        except RuntimeError:
            # 兼容浅克隆拉取失败场景：重新拉全量
            logger.warning("增量拉取失败，尝试完整拉取")
            _git("fetch", "--unshallow", "origin", cwd=dest)
            _git("checkout", branch, cwd=dest)
            _git("reset", "--hard", f"origin/{branch}", cwd=dest)

    return _git("rev-parse", "HEAD", cwd=dest)
