"""全局配置：从 .env 读取，提供路径与运行参数。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # 项目根目录
load_dotenv(BASE_DIR / ".env")


class Settings:
    # 项目根目录
    BASE_DIR = BASE_DIR

    # 服务
    PORT = int(os.getenv("PORT", "8000"))

    # 安全
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

    # 执行
    MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))
    DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "600"))

    # GitHub
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GIT_TIMEOUT = int(os.getenv("GIT_TIMEOUT", "120"))
    # GitHub 访问镜像前缀（国内网络拉取失败时使用，例如 https://ghfast.top/ 或 https://gitclone.com/github.com/ ）
    GIT_CLONE_PREFIX = os.getenv("GIT_CLONE_PREFIX", "")

    # AI
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_MAX_LOG_CHARS = int(os.getenv("LLM_MAX_LOG_CHARS", "8000"))
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))

    # 通知中心渠道（Webhook / SMTP，页面可配覆盖）
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "")
    WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = os.getenv("SMTP_PORT", "465")
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_TO = os.getenv("SMTP_TO", "")

    # 数据目录
    DATA_DIR = BASE_DIR / "data"
    REPOS_DIR = DATA_DIR / "repos"
    LOGS_DIR = DATA_DIR / "logs"
    RUNS_DIR = DATA_DIR / "runs"
    DB_PATH = DATA_DIR / "platform.db"

    def ensure_dirs(self):
        for d in (self.DATA_DIR, self.REPOS_DIR, self.LOGS_DIR, self.RUNS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        # .env 不存在时从模板复制一份，方便首次启动
        if not (BASE_DIR / ".env").exists() and (BASE_DIR / ".env.example").exists():
            (BASE_DIR / ".env.example").read_text(encoding="utf-8")
            # 仅提示，不自动写入，避免覆盖用户配置


settings = Settings()
