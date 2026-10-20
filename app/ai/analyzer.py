"""AI Bug 分析器 + 人工反馈闭环。

流程：失败日志 -> 提取关键词 -> 检索人工纠正样本库(相似示例) -> 调用 LLM(few-shot 注入)
      -> 解析结构化结论落库 -> 人工审核纠正 -> 纠正结论沉淀回样本库 -> 下次分析自动引用。

未配置 LLM API Key 时自动降级为内置规则引擎，并在结果中标注 source=rule。
"""
import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings
from ..database import SessionLocal
from ..models import BugAnalysis, FeedbackItem, Run
from .rules import analyze_by_rules

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "of", "in", "on", "at", "to", "for",
    "and", "or", "with", "from", "this", "that", "error", "failed", "failure",
    "exception", "traceback", "line", "file", "test", "tests", "pytest", "the",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "and", "not", "but",
}


# ---------------- 关键词与检索 ----------------

def extract_keywords(text: str, limit: int = 40) -> list[str]:
    """从日志提取检索关键词：错误类型、文件位置、失败用例名、高频词。"""
    kws: set[str] = set()
    if not text:
        return []
    for m in re.finditer(r"\b\w+(?:Error|Exception|Timeout|Warning|AssertionError)\b", text):
        kws.add(m.group(0))
    for m in re.finditer(r"[\w./\\-]+\.py:\d+", text):
        kws.add(m.group(0)[:60])
    for m in re.finditer(r"(?:FAILED|ERROR)\s+[\w/\[\]\.\-_]+", text):
        kws.add(m.group(0)[:80])
    for m in re.finditer(r"\b[A-Za-z_]\w{3,}\b", text):
        w = m.group(0)
        if w.lower() not in _STOPWORDS:
            kws.add(w)
    # 词频排序截断
    freq: dict[str, int] = {}
    for w in kws:
        freq[w] = text.count(w)
    ranked = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in ranked[:limit]]


def _overlap(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(1, min(len(sa), len(sb)))


def retrieve_feedback_scored(db, keywords: list[str], top_k: int = 3) -> list[tuple[float, "FeedbackItem"]]:
    """从人工纠正样本库检索与当前日志最相似的样本，带相似度分数。"""
    items = db.query(FeedbackItem).order_by(FeedbackItem.created_at.desc()).limit(200).all()
    scored = []
    for it in items:
        it_kws = (it.keywords or "").split("|")
        score = _overlap(keywords, it_kws)
        if score > 0:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def retrieve_feedback(db, keywords: list[str], top_k: int = 3) -> list[FeedbackItem]:
    """从人工纠正样本库检索与当前日志最相似的样本。"""
    return [it for _, it in retrieve_feedback_scored(db, keywords, top_k)]


# ---------------- LLM 调用 ----------------

_ANALYSIS_SYSTEM = (
    "你是资深测试平台缺陷分析专家。根据自动化测试失败的日志，定位缺陷根因。\n"
    "必须只输出一个 JSON 对象（不要输出其他文字），格式如下：\n"
    '{"bug_type": "缺陷类别，如 依赖缺失/断言失败/服务不可达/超时/数据异常 等", '
    '"severity": "low 或 medium 或 high 或 critical", '
    '"root_cause": "根因分析，60字以内", '
    '"suggestion": "修复建议，80字以内", '
    '"confidence": 0到1之间的数字}'
)


def _build_user_prompt(log_text: str, examples: list[FeedbackItem]) -> str:
    parts = []
    if examples:
        parts.append("以下是从历史人工审核确认过的正确分析中检索到的相似案例，请参考其结论风格与归类口径：")
        for i, ex in enumerate(examples, 1):
            sample = (ex.sample_log or "")[-600:]
            parts.append(
                f"### 相似案例{i}\n"
                f"日志片段：\n{sample}\n"
                f"人工确认结论：bug_type={ex.bug_type}；root_cause={ex.root_cause}；suggestion={ex.suggestion}\n"
            )
    parts.append("### 当前失败日志（末尾部分）")
    parts.append(log_text[-settings.LLM_MAX_LOG_CHARS:])
    return "\n\n".join(parts)


def _call_llm(prompt: str) -> dict | None:
    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": _ANALYSIS_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 600,
    }
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}", "Content-Type": "application/json"}
    resp = httpx.post(url, json=payload, headers=headers, timeout=settings.LLM_TIMEOUT)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return _parse_json(content)


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start:end + 1])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    return None


# ---------------- 主流程 ----------------

def _read_log_tail(log_path: Path) -> str:
    try:
        data = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return data[-settings.LLM_MAX_LOG_CHARS:]


def analyze_run_async(run_id: int, log_path: Path, brief: str):
    """后台线程入口：创建分析记录并执行分析。"""
    def _run():
        try:
            analyze_run(run_id, log_path, brief)
        except Exception as exc:
            logger.exception("分析 run %s 失败: %s", run_id, exc)
            db = SessionLocal()
            try:
                db.query(BugAnalysis).filter(BugAnalysis.run_id == run_id).update(
                    {"status": "failed", "raw_output": f"分析器异常: {exc}"}
                )
                db.commit()
            finally:
                db.close()

    threading.Thread(target=_run, daemon=True, name=f"ai-run-{run_id}").start()


def analyze_run(run_id: int, log_path: Path, brief: str):
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return
        log_text = _read_log_tail(log_path) or brief
        if not log_text.strip():
            log_text = run.error_brief or "无可用日志"
        keywords = extract_keywords(log_text)
        scored = retrieve_feedback_scored(db, keywords)
        examples = [it for _, it in scored]

        # 已有分析记录则复用，否则新建
        analysis = db.query(BugAnalysis).filter(BugAnalysis.run_id == run_id).first()
        if analysis:
            analysis.status = "analyzing"
        else:
            analysis = BugAnalysis(run_id=run_id, status="analyzing")
            db.add(analysis)
        db.commit()

        result: dict | None = None
        source = "rule"
        if settings.LLM_API_KEY:
            try:
                result = _call_llm(_build_user_prompt(log_text, examples))
            except Exception as exc:
                logger.warning("LLM 调用失败，降级规则引擎: %s", exc)
                result = None
            if result:
                source = "ai"

        if result is None:
            # 知识库优先：与某条人工确认结论高度相似时直接采用（闭环生效的直接证据），
            # 置信度按相似度加成，未命中再降级关键词规则引擎。
            if scored and scored[0][0] >= 0.40:
                top_score, best = scored[0]
                result = {
                    "bug_type": best.bug_type,
                    "severity": "medium",
                    "root_cause": best.root_cause,
                    "suggestion": best.suggestion,
                    "confidence": min(0.9, 0.5 + top_score * 0.4),
                }
                source = "knowledge"
            if result is None:
                rr = analyze_by_rules(log_text)
                result = {
                    "bug_type": rr.bug_type, "severity": rr.severity,
                    "root_cause": rr.root_cause, "suggestion": rr.suggestion,
                    "confidence": rr.confidence,
                }

        for ex in examples:
            ex.use_count = (ex.use_count or 0) + 1

        analysis.source = source
        analysis.status = "done"
        analysis.bug_type = str(result.get("bug_type", ""))[:128]
        analysis.severity = str(result.get("severity", "medium"))[:16]
        analysis.root_cause = str(result.get("root_cause", ""))[:2000]
        analysis.suggestion = str(result.get("suggestion", ""))[:2000]
        analysis.confidence = float(result.get("confidence", 0) or 0)
        analysis.raw_output = json.dumps(result, ensure_ascii=False)[:4000]
        db.commit()
        logger.info("run %s 分析完成 source=%s bug_type=%s", run_id, source, analysis.bug_type)
    finally:
        db.close()


def log_sample_for_feedback(brief: str, max_chars: int = 1200) -> str:
    """从错误摘要中截取适合沉淀为样本的日志片段。"""
    if not brief:
        return ""
    return brief[-max_chars:]
