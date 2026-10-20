# 自动化测试平台（企业级）

对标大厂测试平台能力，从零落地的自动化测试执行 + AI Bug 分析闭环平台。

## 核心能力

### 1. 任务式脚本执行（GitHub 拉取 + 一键执行）
- 每个任务绑定一个 Git 仓库（GitHub / GitLab / 本地路径）
- 点击「执行」→ 后台自动 clone/fetch 最新代码 → 运行测试命令 → 日志实时流式展示
- 支持私有仓库（GitHub Token 注入）、国内网络镜像前缀、超时自动 kill、全局并发控制（默认 3）、同任务互斥

### 2. AI 分析 Bug + 人工数据闭环
- 执行失败后自动触发 AI 分析（大模型优先，未配置 Key 时自动降级内置规则引擎）
- 分析结果含：Bug 类型、严重级别、置信度、根因分析、修复建议
- **人工审核闭环**：审核「分析正确」→ 结论沉淀为样本库；审核「分析错误」→ 人工纠正后入库。后续 AI 分析自动检索引用样本（few-shot），越用越准

### 3. 企业级平台功能
| 模块 | 能力 |
|---|---|
| 多用户与鉴权 | JWT 登录、角色（admin/user）、用户管理（增删） |
| 仪表盘 | 任务/执行/通过率/AI 分析统计卡片、14 天执行趋势图、Bug 类型分布饼图、最近执行 |
| 定时调度 | 任务级 `schedule_interval_min`，调度器每 30s 扫描自动触发（页面可配） |
| AI 反馈中心 | 待审核 / 已审核 / 样本库三视图，AI 准确率实时统计 |
| 系统设置 | AI 大模型（OpenAI 兼容）、GitHub Token、通知渠道（飞书/钉钉/企微/SMTP）、并发数、超时——配置保存即生效 |
| 执行审计 | 全部执行记录、日志落盘、触发人、commit、耗时、操作日志 |

### 4. 企业级升级（本版新增）
| 模块 | 能力 | 演示形态 |
|---|---|---|
| Agent 执行机集群 | Master-Slave 架构：节点注册 / 心跳 / 负载上报 / 最少负载抢占分配任务，节点离线自动告警 | 本机 3 个 Worker 模拟多节点（agent-01/02/03），可手动上线/下线 |
| 失败自动通知 | 任务失败自动推送（飞书群机器人 Webhook），钉钉/企微/SMTP 渠道预留 | 未配置 Webhook 时自动 mock 落库，通知中心可查看/重发 |
| 真机池 | 设备登记 / 状态（空闲/占用/离线）/ 占用释放 / 预留 adb 序列号 | Mock 设备池，可一键占用/释放演示 |
| 测试环境管理 | 测试服 / 预发 / 生产环境 CRUD | Mock 环境配置 |
| 用例库 | 用例沉淀（优先级/模块/标签），一键执行自动生成任务走完整流水线，结果回写 | 内置"登录模块冒烟用例"可一键执行 |
| 报告中心 | 执行量/通过率/平均耗时/AI 准确率总览、执行趋势、失败 Top 任务、用例模块分布、最近报告（含执行节点） | 实时聚合全部历史数据 |
| 通知中心 | 通知记录（任务失败/节点离线）、未读角标、已读/全部已读/重发 | 未配置渠道时显示"模拟"状态，可演示闭环 |

## 技术栈
- 后端：Python FastAPI + SQLAlchemy + SQLite + JWT
- 前端：Vue 3（全局构建版，In-DOM 模板）+ Element Plus + ECharts + axios
- 前端资源全部本地化（`app/static/vendor`），**不依赖任何 CDN**，断网可用

## 目录结构
```
E:\自动化平台搭建\
├── main.py                  # 入口：初始化库 → 注册路由 → 挂载前端 → 启动调度 → 起服务
├── requirements.txt         # Python 依赖
├── .env / .env.example      # 环境配置
├── start.bat                # 一键启动
├── app\
│   ├── config.py            # 配置读取（.env）
│   ├── database.py          # SQLite 连接
│   ├── models.py            # User/Task/Run/BugAnalysis/FeedbackItem/Setting/OperationLog
│   ├── security.py          # PBKDF2 密码哈希 + JWT
│   ├── schemas.py           # Pydantic 模型
│   ├── executor\
│   │   ├── github_client.py # Git 拉取（clone/fetch/checkout、Token 注入、镜像前缀、local:// 演示仓库）
│   │   └── runner.py        # 执行引擎（并发信号量、Popen 流式日志、超时 kill、Agent 分配、失败通知）
│   ├── agents\
│   │   └── worker.py        # Agent 集群（本机多 Worker 模拟：注册/心跳/负载/抢占）
│   ├── notify\
│   │   └── service.py       # 通知中心（飞书/钉钉/企微/SMTP 渠道 + mock 降级）
│   ├── ai\
│   │   ├── rules.py         # 10 条关键词规则引擎（降级兜底）
│   │   └── analyzer.py      # AI 分析编排（LLM 优先 → 规则降级 → few-shot 样本检索）
│   ├── api\                 # auth/tasks/runs/ai/dashboard/settings/agents/devices/envs/cases/reports/notifications 路由
│   ├── scheduler.py         # 定时调度器
│   └── static\              # 前端（index.html + css/js/vendor）
├── data\
│   ├── platform.db          # SQLite 数据库
│   ├── logs\run_{id}.log    # 每次执行的完整日志
│   └── repos\task_{id}\     # 任务拉取的代码仓库
└── scripts\
    ├── demo-repo\           # 本地演示仓库（离线跑通全流程用）
    └── smoke_test.py        # 端到端冒烟测试
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置（可选）
复制 `.env.example` 为 `.env`，按需修改：
- `PORT` 服务端口（默认 8000）
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` 默认管理员（首次启动自动创建）
- `GITHUB_TOKEN` 私有仓库拉取用
- `GIT_CLONE_PREFIX` 国内拉 GitHub 失败时填镜像前缀（如 `https://ghfast.top/`）
- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 配置大模型后 AI 分析走 LLM，否则走规则引擎

### 3. 启动
```bash
python main.py
```
浏览器访问 http://127.0.0.1:8000 ，默认账号 `admin / admin123`。

（Windows 双击 `start.bat` 亦可。）

## 使用指南

1. **创建任务**：任务管理 → 新建任务 → 填仓库地址（GitHub URL / 本地路径 / `local://demo-repo`）+ 执行命令（如 `python -m pytest -q`）
2. **执行**：任务列表 → 点「执行」→ 执行记录页实时查看日志流（执行会分配 Agent 节点）
3. **看 AI 分析**：执行记录 → 点「详情」→ 日志下方 AI Bug 分析卡片
4. **人工审核闭环**：AI 反馈中心 → 待审核 → 审核 → 「分析正确」或「分析错误，纠正」→ 提交后自动沉淀样本、刷新准确率
5. **失败自动通知**：任务执行失败 → 通知中心自动生成通知（配置了飞书 Webhook 则真实推送，否则 mock 模拟）→ 可标记已读/重发
6. **节点管理**：资源域 → 节点管理 → 查看节点心跳/负载 → 可模拟下线（触发离线告警）与上线
7. **真机池 / 环境**：资源域 → 真机池/环境 → 登记 Mock 设备、占用/释放演示；维护测试服/预发/生产环境
8. **用例库**：资源域 → 用例库 → 新建用例 → 一键执行（自动生成任务走完整流水线，结果回写）
9. **报告中心**：执行域 → 报告中心 → 查看质量总览、失败 Top 任务、模块分布、最近报告（点击行直达执行详情）

## 离线演示（无需外网、无需 Key）
直接使用内置演示仓库：
- 仓库地址：`E:\自动化平台搭建\scripts\demo-repo`（或任务仓库填 `local://demo-repo`）
- 执行命令：`python -m pytest -q`
- 该仓库含 1 个故意失败的用例（`AssertionError: 环境配置错误`），可完整演示「执行 → 失败 → Agent 分配 → AI 分析 → 人工审核 → 样本沉淀 → 失败自动通知」全链路

## 接真实数据（三步切换生产）
1. `.env` 填 `GITHUB_TOKEN`（私有仓库）和 `GIT_CLONE_PREFIX`（国内镜像）
2. 系统设置页填 `LLM_API_KEY`，AI 分析从规则引擎切换到大模型
3. 系统设置页填 `FEISHU_WEBHOOK`（飞书群机器人 Webhook），失败通知从 mock 切换为真实推送
4. 任务仓库地址改为真实仓库 URL，执行命令改为真实测试命令

## 已知限制
- 未配置 LLM Key 时 AI 分析使用内置规则引擎（10 条关键词规则），识别精度有限
- Agent 集群为「本机多 Worker 模拟」，真实分布式需在多台机器各起一个 Worker（代码已按注册/心跳/抢占协议实现，Worker 侧仅需接入 `pick_agent` 队列）
- 真机池为 Mock 设备，接真实设备时在设备登记处填 adb 序列号即可对接 adb 自动化
- SQLite 单机存储，适合中小团队；大规模并发可平滑迁移 PostgreSQL
