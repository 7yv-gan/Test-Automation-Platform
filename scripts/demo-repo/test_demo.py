"""本地演示仓库：用于在无外网/无 GitHub 环境下端到端验证平台流水线。

包含 1 个失败用例（触发 AI 分析）和 1 个成功用例。
使用方法：新建任务时 repo_url 填本目录路径，command 填 python -m pytest -q
"""
import sys


def test_pass():
    assert 1 + 1 == 2


def test_fail():
    """制造一个失败：模拟真实场景中的断言错误，用于演示 AI Bug 分析闭环。"""
    expected = "production"
    actual = "debug"
    assert actual == expected, f"环境配置错误: expected={expected}, actual={actual}"


if __name__ == "__main__":
    sys.exit(0)
