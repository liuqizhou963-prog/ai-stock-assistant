# D:\桌面agent 从零重构计划

## 定位

构建一个本地 Electron + React 桌面 Agent 平台，第一套领域能力为 A 股分析。

旧项目只作为产品、交互和数据源参考；不复制旧 HTML、Python 后端、Agent、数据库、状态或启动脚本。

桌面应用有三个核心入口：

```text
时事雷达
股票 Agent
股票工作台
```

## 行业与资讯分类

首页采用三层体系：

```text
一级导航：10 个大板块
二级分类：申万一级 31 行业
标签体系：跨行业主题
```

一级导航与申万行业映射固定如下：

| 一级导航 | 申万一级行业 |
|---|---|
| 农业与消费 | 农林牧渔、食品饮料、家用电器、纺织服饰、轻工制造、商贸零售、社会服务、美容护理 |
| 能源与资源 | 煤炭、石油石化、基础化工、钢铁、有色金属 |
| 科技与传媒 | 电子、计算机、通信、传媒 |
| 高端制造 | 机械设备、国防军工、汽车、建筑材料、建筑装饰 |
| 电力与环保 | 电力设备、公用事业、环保 |
| 医药健康 | 医药生物 |
| 金融与地产 | 银行、非银金融、房地产 |
| 交通与物流 | 交通运输 |
| 综合 | 综合 |
| 宏观与市场 | 宏观、政策、利率、汇率、市场制度、海外市场事件，不属于申万行业 |

跨行业主题以标签方式存在，不作为底层行业分类，例如：

```text
AI
芯片
机器人
新能源车
低空经济
算力
创新药
消费电子
军工信息化
新型电力系统
```

新闻可以同时具备：

```text
一个一级导航
+ 一个或多个申万行业
+ 多个主题标签
```

例如一篇 AI 服务器新闻可归入：

```text
科技与传媒
-> 电子 / 计算机
-> AI、算力、芯片
```

首版先建立全部 31 行业和 10 大板块的结构，但新闻来源分批启用。未验证或暂未接入来源的行业显示“数据源待接入”，不伪造内容。

现有项目的 12 类科技产业资讯，作为新系统初始数据源候选；需要按新分类重新归属和逐个验证，不直接复制旧配置。

## 工程结构

```text
D:\桌面agent\
  apps\
    desktop\                 Electron 主进程、Preload、打包
    renderer\                React 前端
    backend\                 全新 Python API
  packages\
    agent-runtime\           Provider、会话、工具循环、事件、权限
    domain-stock\            A股领域规则、工具、数据模型
    news-core\               新闻抓取、分类、去重、存储
    skill-runtime\           Skill 发现、加载、匹配
    mcp-runtime\             MCP Client、工具注册、调用管理
    shared\                  共享类型、事件协议、错误码
  skills\
    a-stock-data\
      SKILL.md
  config\
    providers.example.json
    news-taxonomy.json
    news-sources.json
  data\
  state\
    app.db
  tests\
  README.md
```

新项目不迁移旧项目的历史记忆、自选股、提醒、SQLite 数据、日志、缓存、截图或启动脚本。

## 时事雷达首页

首页用 React 从零实现，视觉目标是保留当前项目的“打开即可浏览产业时事”的体验，但不复用旧 HTML。

首屏包含：

- 10 个大板块导航。
- 二级申万行业筛选。
- 跨行业主题标签筛选。
- 最新新闻流。
- 来源、发布时间、行业归属、主题标签。
- 来源健康状态。
- 刷新按钮和最近更新时间。
- 原文跳转。
- 后续可加入“今日重点”和“行业热度”。

新闻后端负责：

```text
抓取
-> 解析
-> 规范化
-> 去重
-> 分类
-> 存储
-> 提供查询接口
```

使用 SQLite 保存新闻、来源状态、分类结果和抓取日志。

## 通用 Agent Runtime

从零实现，不沿用旧项目规则 Agent。

第一版流程：

```text
用户消息
-> 加载会话、模型和股票领域规则
-> LLM 判断是否调用工具
-> 执行白名单工具
-> 返回工具结果
-> LLM 继续分析或调用下一工具
-> 输出分析与证据
```

统一事件：

```text
run_start
plan_step
thinking_summary
tool_call_start
tool_result
approval_required
answer_delta
run_complete
run_error
```

界面只展示可审计的执行摘要、工具调用、数据来源和耗时，不展示或伪造完整隐藏思维链。

模型层：

- 默认 DeepSeek。
- 统一 Provider 接口。
- 设置页预留 OpenAI、Claude。
- 支持流式输出、工具调用、推理等级和上下文能力声明。
- API Key 只保存于本地安全配置或环境变量，不进入前端和 Git。

金融安全边界：

```text
允许：行情、基本面、技术指标、行业、风险、情景和数据对比分析
禁止：未来涨跌预测、目标价、买卖指令、仓位、止盈止损指令
```

最终回答必须经过金融输出安全层。

## 股票 Agent 与工具

股票 Agent 首版提供：

- 多会话聊天。
- 流式中文回答。
- 行情、K 线、基本面、资讯、公告、研报查询。
- 工具调用与结果展示。
- 数据来源、更新时间、缓存状态和警告。
- 股票名称和代码识别。
- 工具失败后的结构化降级说明。

统一工具接口：

```json
{
  "name": "get_kline",
  "description": "获取A股历史K线",
  "risk": "low",
  "inputSchema": {},
  "handler": "stock.get_kline"
}
```

首批工具：

```text
get_market_quote
get_kline
get_intraday
get_fundamentals
get_stock_news
get_company_announcements
get_research_reports
get_sector_membership
get_sector_ranking
get_fund_flow
get_limitup_pool
```

每个工具返回：

```json
{
  "data": {},
  "source": "provider-name",
  "fetchedAt": "ISO-8601",
  "cached": false,
  "stale": false,
  "warnings": []
}
```

工具执行必须具备白名单、参数验证、超时、调用轮数上限和错误隔离。付费或高成本数据必须先确认。

## a-stock-data Skill 集成

将仓库的 `SKILL.md` 放入：

```text
D:\桌面agent\skills\a-stock-data\SKILL.md
```

Skill Runtime 负责：

- 发现所有 `SKILL.md`。
- 提取名称、描述、适用场景和版本。
- 只把 Skill 摘要放入模型上下文。
- 任务匹配时按需加载完整内容。
- 将 Skill 数据能力封装成标准 Tool。
- 禁止模型直接执行任意代码或任意 URL。

首批接入 `a-stock-data`：

```text
A股实时行情
K线与分时
五档盘口
基本面快照
研报与公告
行业与概念归属
资金流
涨停池
```

后续接入：

```text
龙虎榜
两融
大宗交易
股东户数
分红
ETF
期权
```

## 股票工作台

第一阶段只实现泰深的“数据层”，不实现策略层和决策层。

首批工作台视图：

```text
自选股
市场概览
单股详情
K线
分时
基本面
公告与研报
行业与概念
资金流
涨停池
```

统一画布协议：

```json
{
  "view": "kline",
  "mode": "replace",
  "data": {}
}
```

预留但暂不实施：

```text
图表标记
策略条件与调度
自动提醒
综合评分
决策树
多 Agent 分工
```

后续按泰深的具体模块逐项对比、筛选和实现。

## 桌面运行方式

Electron 主进程负责：

- 自动启动全新 Python 后端。
- 检查后端健康状态。
- 管理可用本地端口。
- 关闭窗口时停止本次启动的后端。
- 使用受限 IPC。
- 禁止前端直接执行系统命令。
- 后续管理 MCP、文件权限和系统通知。

个人本地版不需要服务器。成本只包括 LLM API 和可选付费数据。

## 实施顺序

1. 初始化全新 Electron + React + Python 工程。
2. 建立桌面壳、左侧导航、后端自动启动和健康检查。
3. 定义 10 大板块、申万 31 行业与主题标签数据模型。
4. 从零实现新闻抓取、来源健康、分类、去重与 SQLite 存储。
5. 用 React 实现时事雷达首页。
6. 将当前 12 类资讯源按新体系逐个验证并接入。
7. 建立 Provider 接口、DeepSeek 配置和流式聊天。
8. 建立 Agent Runtime、Tool Contract 与事件流。
9. 接入 `a-stock-data` 第一批 A 股工具。
10. 实现股票 Agent 聊天界面。
11. 实现股票工作台数据层。
12. 按你的筛选，继续增加泰深的策略、决策、MCP 管理和其他领域模块。

## 验收

- 打开桌面程序直接进入时事雷达。
- 首页可按 10 大板块、31 个申万行业和主题标签筛选。
- 已启用来源可刷新，失效来源不阻塞其他来源。
- 股票 Agent 支持流式输出和真实工具调用。
- Agent 可调用行情、K线、基本面三类以上工具。
- 每项股票数据都显示来源和更新时间。
- 不输出预测、买卖、目标价或仓位建议。
- 股票工作台显示自选、单股 K 线与基本面。
- 新项目不依赖旧网页项目的运行代码。
- 只有刷新新闻、请求行情或调用模型时需要网络。
