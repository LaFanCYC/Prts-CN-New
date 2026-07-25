# AI 助手悬浮球方案

## 概述

在页面右下角添加 AI 搜索助手悬浮球。用户输入自然语言描述想找的内容，系统先执行 SQL 关键词搜索，若管理员已配置 AI 则将搜索结果发给 AI 进行智能整理和摘要，否则直接展示原始搜索命中。AI 配置（endpoint、key、model、system prompt、开关）由管理员在后台统一管理。

## 核心变更

**数据库**
- 新增 `ai_config` 表（单行配置），字段：`enabled`、`api_endpoint`、`api_key`、`model`、`system_prompt`、`max_results`、`updated_at`

**后端 — `app.py`**
- 新增路由 `POST /api/ai/search`：接收 `{"query": "..."}`，返回 `{"results": [...], "mode": "ai"|"keyword"}`
- `search_content()` 函数：对 posts（title+body）、resources（name+description）、lost_found（title+description）执行 `LIKE` 搜索，按相关度 + 时效排序，返回最多 15 条
- `ai_enhance_results()` 函数：将 top N 条结果序列化为文本，调用配置的 OpenAI-compatible API，返回 JSON 格式的增强结果
- 新增路由 `GET/POST /admin/ai-config`：管理员表单（`@admin_required`），保存/读取 `ai_config` 表
- 新增 `requirements.txt` 依赖：`requests>=2.32,<3`

**后端 — 上下文注入**
- 在 `shared_template_values()` 中将 `ai_enabled` 注入所有模板，控制悬浮球渲染

**前端 — 悬浮球组件**
- 新增 `static/ai-assistant.js`：悬浮球 DOM 创建、展开/收起、搜索请求、结果渲染、loading 骨架
- 新增 `static/ai-assistant.css`：悬浮球定位（fixed bottom-right）、面板动画、搜索结果卡片、loading 脉冲
- 修改 `templates/base.html`：引入 ai-assistant.css + ai-assistant.js，在 `</body>` 前渲染悬浮球标记

**管理后台**
- 修改 `templates/admin.html`：在审计日志 section 后新增 "AI 助手配置" section
- 表单字段：启用开关、API 地址、API Key（password 输入）、模型名、系统提示词、最大结果数

## 搜索流程

```
用户输入 → 前端 POST /api/ai/search → 后端 SQL LIKE 搜索 → 
  ├─ AI 未启用 → 返回原始结果列表
  └─ AI 启用 → 拼装 prompt → 调用 AI API →
       ├─ 成功 → 返回 AI 整理后的结果
       └─ 失败/超时(5s) → 回退原始结果
```

## AI Prompt 设计

系统提示词由管理员自定义，默认值：
> "你是一个校园资源共享平台的搜索助手。根据用户的搜索描述和平台内匹配到的内容列表，帮助用户整理最相关的结果，用简洁的中文说明每个结果为什么可能符合他的需求。只返回 JSON 数组，不要额外解释。"

发给 AI 的 user message 包含：用户原始查询 + 匹配到的内容列表（每项含类型、标题、摘要、链接标记）

## 测试场景

- 管理员配置 AI 参数后，悬浮球显示并可用
- 管理员关闭 AI 后，悬浮球仍可搜索但返回原始结果
- 用户输入中文自然语言查询，返回相关帖子/资源/失物
- AI API 不可达时自动降级为关键词搜索
- 访客（未登录）也可使用搜索
- 空查询返回空结果而非报错

## 假设与默认值

| 项 | 默认值 |
|---|---|
| AI 默认未启用 | `enabled = 0` |
| 模型 | 空（管理员首次配置时填入，如 `gpt-4o-mini`） |
| API 超时 | 5 秒 |
| 关键词搜索最大结果 | 15 条 |
| 发给 AI 的结果条数 | 最多 10 条（`max_results` 可配，默认 10） |
| AI API 格式 | OpenAI Chat Completions 兼容（`/v1/chat/completions`） |
| 悬浮球位置 | 右下角，距离边缘 24px |
