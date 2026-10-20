"""内置规则引擎：未配置 LLM 时的降级方案，基于关键词识别常见缺陷。"""
import re
from dataclasses import dataclass, field

_RULES: list[dict] = [
    {"pattern": r"ModuleNotFoundError|ImportError:\s*No module named",
     "bug_type": "依赖缺失/环境问题", "severity": "high",
     "root_cause": "执行环境缺少脚本所需的 Python 依赖包，import 阶段失败。",
     "suggestion": "检查 requirements.txt 是否完整，在任务的环境变量或安装步骤中补充依赖安装（如 pip install -r requirements.txt）。"},
    {"pattern": r"AssertionError|assert\s",
     "bug_type": "断言失败/功能缺陷", "severity": "medium",
     "root_cause": "被测功能实际结果与预期断言不一致，多为代码逻辑缺陷或用例期望值过期。",
     "suggestion": "定位断言处的实际输出与期望值差异，确认是功能 bug 还是用例断言过期，必要时更新期望值。"},
    {"pattern": r"TimeoutError|timed out|TimeoutException",
     "bug_type": "执行超时", "severity": "medium",
     "root_cause": "请求/操作未在预期时间内完成，可能由服务阻塞、网络延迟或死循环导致。",
     "suggestion": "检查被测服务是否正常响应，确认超时阈值设置是否合理，排查潜在死循环或阻塞调用。"},
    {"pattern": r"ConnectionRefused|ConnectionError|ECONNREFUSED",
     "bug_type": "服务不可达", "severity": "high",
     "root_cause": "目标服务未启动或端口不通，被测服务连接被拒绝。",
     "suggestion": "确认被测服务已启动且监听端口正确，检查防火墙与网络连通性，验证服务地址配置。"},
    {"pattern": r"SyntaxError",
     "bug_type": "代码语法错误", "severity": "high",
     "root_cause": "脚本存在语法错误，Python 解释器无法解析代码。",
     "suggestion": "根据报错行列号修复语法，使用 linter（ruff/flake8）提前拦截语法问题。"},
    {"pattern": r"PermissionError|Access denied",
     "bug_type": "权限不足", "severity": "high",
     "root_cause": "执行用户缺少文件/网络/系统资源访问权限。",
     "suggestion": "检查执行账号权限、文件可写性及服务账号配置，必要时提升权限或调整 ACL。"},
    {"pattern": r"KeyError|IndexError",
     "bug_type": "数据缺失/越界", "severity": "medium",
     "root_cause": "脚本访问了不存在的字典键或列表越界，多为数据处理边界未覆盖。",
     "suggestion": "检查数据源字段是否缺失，增加默认值与边界校验，定位异常访问的具体位置。"},
    {"pattern": r"FileNotFoundError|No such file or directory|OSError",
     "bug_type": "文件/路径错误", "severity": "medium",
     "root_cause": "脚本引用的文件或目录不存在，路径配置与实际环境不一致。",
     "suggestion": "核对脚本引用的文件路径与仓库结构，确认工作目录与相对路径基准。"},
    {"pattern": r"RuntimeError|Exception|ERROR|Traceback|FAILED|failed",
     "bug_type": "运行异常/用例失败", "severity": "medium",
     "root_cause": "执行过程中抛出未预期异常或存在失败用例，需结合具体堆栈定位。",
     "suggestion": "查看完整日志堆栈定位首个异常点，复现并修复后重跑验证。"},
    {"pattern": r"Error|error",
     "bug_type": "未知错误", "severity": "low",
     "root_cause": "日志中出现 Error 关键字但无法精确归类，需人工查看上下文。",
     "suggestion": "查看完整执行日志，定位首个错误发生位置并复现。"},
]


@dataclass
class RuleResult:
    bug_type: str
    severity: str
    root_cause: str
    suggestion: str
    confidence: float
    matched_pattern: str = field(default="")


def analyze_by_rules(log_text: str, max_chars: int = 8000) -> RuleResult:
    """按规则表顺序匹配，返回置信度最高的结果。"""
    sample = log_text[-max_chars:]
    for rule in _RULES:
        m = re.search(rule["pattern"], sample, re.IGNORECASE | re.MULTILINE)
        if m:
            return RuleResult(
                bug_type=rule["bug_type"],
                severity=rule["severity"],
                root_cause=rule["root_cause"],
                suggestion=rule["suggestion"],
                confidence=0.45,
                matched_pattern=rule["pattern"],
            )
    return RuleResult(
        bug_type="未识别",
        severity="medium",
        root_cause="未能在日志中匹配到已知错误特征，请人工查看日志。",
        suggestion="建议人工复核日志，若属于已知问题类别可在反馈中心补充正确结论，帮助模型后续学习。",
        confidence=0.15,
    )
