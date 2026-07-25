# 校园智享——资源智能流转平台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在当天完成一个可本地运行的校园资源流转与失物招领 Web 应用，覆盖用户、资源、流转、匹配通知、管理和统计基础功能。

**架构：** 使用 Flask 单体应用同时承载 WebUI 与后端，SQLite 保存业务数据，HTML 模板与原生 CSS/JavaScript 构建响应式中文界面。图片保存在本机可写数据目录，数据库仅记录随机文件名；目录设计兼容后续 PyInstaller 打包。

**技术栈：** Python 3.11+、Flask、Waitress、SQLite、Jinja2、Werkzeug、HTML/CSS/JavaScript、`unittest`

## 全局约束

- 本期只完成已确认的基础功能，不使用 Docker，不生成 `.exe`。
- 后期使用 PyInstaller 生成 Windows `.exe`；数据库、密钥和上传图片不得写入打包资源目录。
- 不引入前端框架、ORM、AI 模型、短信、邮件、微信通知或对象存储。
- 使用 Werkzeug 密码哈希、CSRF 令牌、服务端权限校验和安全文件名，不能用前端隐藏按钮代替权限控制。
- 所有界面和提示使用中文，适配电脑与手机。
- WebUI 采用服务端表单提交，只为搜索、通知和统计提供必要 JSON 接口。

---

## 一、已确认的产品范围

### 1. 用户与权限

- 角色只有“学生”和“管理员”；资源发布者是业务身份，不增加第三种角色。
- 学生注册字段：用户名、密码、姓名、学号、年级、班级。
- 用户名和学号全局唯一。
- 学生可修改姓名、年级、班级、联系方式和密码，不能自行修改用户名与学号。
- 管理员可更正用户资料、修改学生/管理员角色、启用或禁用账号。
- 管理员账号只能由初始化命令或现有管理员创建，注册页面不能注册管理员。

### 2. 学习资源

- 发布字段：资源名称、类别、新旧程度、流转方式、描述、关键词、图片。
- 固定类别：教材书籍、实验器材、电子设备、文体用品、学习资料、技能服务、其他。
- 实体资源流转方式：免费借用、交换、赠送；技能服务流转方式：免费互助、技能交换。
- 实体资源新旧程度：全新、九成新、七成新、明显使用痕迹；技能服务为“不适用”。
- 图片可选；允许 JPG、PNG、WebP，最大 5 MB。
- 图片保存到本地可写 `uploads/` 目录，使用随机文件名，禁止按用户文件名直接落盘。
- 搜索支持名称/描述关键词，并按类别、流转方式、新旧程度和可用状态筛选；结果按发布时间倒序。
- 发布者可编辑没有待审批申请的可用资源；从未产生申请时可删除，已有历史时只能下架。

### 3. 申请与流转

- 免费借用状态：`待审批 → 借用中 → 待确认归还 → 已归还`；拒绝后为`已拒绝`。
- 借用人发起归还，资源发布者确认归还。
- 赠送、交换：申请人填写备注；发布者同意后直接进入`流转完成`，没有归还步骤。
- 同一资源允许多人提交待审批申请。
- 发布者同意一人时，在同一个数据库事务中自动拒绝该资源的其他待审批申请。
- 借用资源确认归还后重新变为可申请；赠送和交换完成后永久关闭。
- 免费借用申请必须填写预计归还日期；系统在访问页面时标记逾期并只生成一次站内提醒，不运行后台定时任务。
- 技能服务状态：`待审批 → 服务进行中 → 待对方确认 → 已完成`；发布者提交完成，申请人确认。
- 技能服务可重复提供，同一时间只接受一人，完成后自动重新开放，其他待审批申请继续保留。
- 申请人可撤销待审批申请；进入借用中或服务进行中后，只能由管理员处理异常。
- 借用和赠送备注可选，交换必须说明交换物品；发布者拒绝时必须填写原因。
- 自动记录申请、审批、开始、发起归还或完成、最终确认等时间，并展示流转时间线。
- 只有申请人、资源发布者及管理员能查看相关申请详情；审批只能由发布者执行。

### 4. 失物招领与匹配

- 支持发布“寻物启事”和“拾物登记”。
- 字段：物品名称、描述、发生日期、地点、关键词、可选图片、状态和发布时间；关键词至少一个。
- 匹配使用关键词重合与名称相似度，不调用外部 AI。
- 新记录只与类型相反且状态为“未解决”的记录比较，达到阈值后生成匹配记录和双方站内通知。
- 记录状态为“未解决”或“已解决”；发布者和管理员可标记已解决。
- 已解决记录继续保留且可搜索，可按“全部/未解决/已解决”筛选，但不参与自动匹配。
- 匹配通知只使用站内通知；支持未读/已读和跳转到对应记录。
- 发布者可编辑未解决记录，编辑后重新匹配；已解决记录须先恢复为未解决才能编辑。
- 登录用户可查看失物详情中的联系方式并人工联系发布者，不增加认领申请流程。

### 5. 管理与统计

- 管理员可查看全部用户，修改角色，启用/禁用账号，删除违规资源和失物信息。
- 管理员以“下架”代替物理删除，保留历史记录；账号只禁用、不物理删除。
- 忘记密码由管理员重置临时密码，用户登录后自行修改。
- 统计首页显示：用户总数、资源总数、待审批数、借用中数、已完成流转数、寻物数、拾物数、成功匹配数。
- 按资源类别和流转方式显示柱状统计。
- 本期不做数据导出、自定义时间筛选和复杂分析。

### 6. 演示与运行

- 提供初始化命令，创建一个管理员、两个学生账号和少量资源、申请、失物示例。
- 演示密码只用于本地展示，README 必须列明并提示修改。
- 提供 `requirements.txt`、初始化命令、启动命令和最短验收步骤。
- 使用 Waitress 支持本机演示及校园局域网小规模访问，不宣称可直接用于公网生产环境。
- 页面使用“展开的书本 + 双向循环箭头”蓝绿 SVG Logo，并统一使用“校园智享”名称。
- 游客可浏览和搜索，但看不到联系方式，也不能发布、申请或查看通知。
- 列表每页 12 条，导航展示未读通知数并支持全部标为已读。
- 密码至少 8 位并二次确认；标题最多 50 字、描述 1000 字、备注/拒绝原因 300 字、联系方式 100 字，均由后端校验。

## 二、计划文件结构

```text
main/
├── app.py                  # 应用工厂、路由、权限、业务流程和 CLI 初始化命令
├── db.py                   # SQLite 连接、建表、事务和查询辅助函数
├── schema.sql              # 表结构、索引与唯一约束
├── requirements.txt        # Flask 与 Waitress
├── init_linux.sh           # Linux 环境、数据库与管理员初始化
├── start_linux.sh          # Linux Waitress 启动入口
├── init_windows.bat        # Windows 环境、数据库与管理员初始化
├── start_windows.bat       # Windows Waitress 启动入口
├── README.md               # 安装、初始化、启动、演示账号和打包注意事项
├── static/
│   ├── app.css             # 响应式蓝绿色校园风格
│   └── app.js              # 筛选、通知和必要的渐进增强
├── static/logo.svg         # 书本与流转箭头组成的校园智享 Logo
├── templates/
│   ├── base.html
│   ├── auth.html
│   ├── home.html
│   ├── profile.html
│   ├── resources.html
│   ├── resource_form.html
│   ├── resource_detail.html
│   ├── applications.html
│   ├── lost_found.html
│   ├── lost_found_form.html
│   ├── lost_found_detail.html
│   ├── notifications.html
│   └── admin.html
└── tests/
    └── test_app.py         # 权限、资源流转、匹配和统计的最小集成检查
```

运行期数据不提交到源码目录；由 `db.py` 统一解析可写位置：Windows 优先 `%LOCALAPPDATA%/CampusSmartFlow/`，其他系统使用用户数据目录。该目录包含 `app.db`、`secret.key` 和 `uploads/`。

## 三、数据模型

### `users`

`id, username, password_hash, name, student_no, grade, class_name, contact, role, is_active, must_change_password, created_at`

- `username`、`student_no` 唯一。
- `role` 只允许 `student/admin`。
- 禁用用户不能登录；现有数据保留。

### `resources`

`id, owner_id, name, category, condition_level, transfer_mode, description, keywords, image_name, status, created_at`

- `transfer_mode`：`borrow/exchange/gift/free_help/skill_exchange`。
- `status`：`available/in_use/in_service/completed/withdrawn`。

### `applications`

`id, resource_id, applicant_id, note, rejection_reason, expected_return_date, applied_at, approved_at, action_at, completed_at, status, created_at, updated_at`

- `status`：`pending/borrowed/return_pending/returned/rejected/completed/in_service/completion_pending/withdrawn`。
- 禁止用户申请自己的资源，禁止同一用户对同一资源重复提交待处理申请。

### `lost_found`

`id, user_id, kind, title, description, occurred_on, location, keywords, image_name, status, created_at`

- `kind`：`lost/found`。
- `status`：`open/resolved`。

### `matches`

`id, lost_id, found_id, score, created_at`

- `(lost_id, found_id)` 唯一，防止重复通知。

### `notifications`

`id, user_id, message, target_url, is_read, created_at`

## 四、实施任务

### Task 1：应用骨架、数据库和身份系统

**文件：** `app.py`、`db.py`、`schema.sql`、`requirements.txt`、`templates/base.html`、`templates/auth.html`、`templates/profile.html`、`tests/test_app.py`

**产出接口：**

- `create_app(test_config=None) -> Flask`
- `get_db() -> sqlite3.Connection`
- `init_db() -> None`
- `login_required(view)`、`admin_required(view)`
- CLI：`flask --app app init-demo`

- [ ] 先写集成检查：注册成功、重复学号失败、密码以哈希保存、禁用账号不能登录、学生不能访问管理页。
- [ ] 运行 `python -m unittest tests.test_app -v`，确认检查失败。
- [ ] 建立六张业务表、必要索引、外键与唯一约束。
- [ ] 实现注册、登录、退出、资料修改、修改密码、会话和 CSRF 校验。
- [ ] 实现学生/管理员装饰器与每个写操作的服务端所有权检查。
- [ ] 再次运行测试，以上身份与权限检查必须通过。

### Task 2：资源发布、图片与搜索

**文件：** `app.py`、`templates/resources.html`、`templates/resource_form.html`、`templates/resource_detail.html`、`static/app.css`、`tests/test_app.py`

**产出接口：**

- `save_image(file) -> str | None`
- `GET /resources`
- `GET|POST /resources/new`
- `GET /resources/<int:id>`

- [ ] 添加检查：匿名用户不能发布；合法图片可保存；扩展名伪装或超过 5 MB 被拒绝；组合筛选返回正确资源。
- [ ] 实现发布校验、图片头检测、随机文件名和受控图片读取路由。
- [ ] 实现关键词、类别、方式、新旧程度、状态筛选及倒序分页列表。
- [ ] 完成响应式资源卡片、详情页和空结果提示。
- [ ] 运行 `python -m unittest tests.test_app -v`，确认资源检查通过。

### Task 3：申请、审批和归还事务

**文件：** `app.py`、`templates/resource_detail.html`、`templates/applications.html`、`tests/test_app.py`

**产出接口：**

- `POST /resources/<int:id>/apply`
- `POST /applications/<int:id>/approve`
- `POST /applications/<int:id>/reject`
- `POST /applications/<int:id>/request-return`
- `POST /applications/<int:id>/confirm-return`

- [ ] 添加完整流程检查：借用申请、审批、发起归还、确认归还和资源重新开放。
- [ ] 添加并发规则检查：批准一名申请人后，其余待审批申请自动拒绝。
- [ ] 添加交换/赠送检查：同意后直接完成且资源关闭。
- [ ] 在事务中实现状态机，只允许合法的下一步状态；非法越权或重复请求返回 403/409。
- [ ] 为申请人和发布者生成审批、拒绝、归还相关站内通知。
- [ ] 运行全部测试，确认三类流转均通过。

### Task 4：失物招领、自动匹配与通知

**文件：** `app.py`、`templates/lost_found.html`、`templates/lost_found_form.html`、`templates/lost_found_detail.html`、`templates/notifications.html`、`tests/test_app.py`

**产出接口：**

- `match_score(left, right) -> float`
- `create_matches(record_id) -> list[int]`
- `GET /lost-found`
- `GET|POST /lost-found/new/<kind>`
- `POST /lost-found/<int:id>/resolve`
- `GET /notifications`、`POST /notifications/<int:id>/read`、`POST /notifications/read-all`

- [ ] 添加确定性检查：相同关键词及相似名称超过阈值；无关记录低于阈值；同类记录不匹配；已解决记录不匹配。
- [ ] 使用标准库归一化文本、关键词集合重合和 `difflib.SequenceMatcher` 计算固定分数。
- [ ] 新建记录后匹配相反类型的未解决记录，并依靠唯一约束防止重复匹配。
- [ ] 为双方创建带详情链接的通知，实现已读/未读状态。
- [ ] 实现关键词和“全部/未解决/已解决”筛选。
- [ ] 运行全部测试，确认匹配与通知检查通过。

### Task 5：管理员管理与统计报表

**文件：** `app.py`、`templates/admin.html`、`static/app.css`、`tests/test_app.py`

**产出接口：**

- `GET /admin`
- `POST /admin/users/<int:id>/role`
- `POST /admin/users/<int:id>/active`
- `POST /admin/resources/<int:id>/delete`
- `POST /admin/lost-found/<int:id>/delete`
- `GET /api/admin/stats`

- [ ] 添加检查：学生访问所有管理写接口均为 403；管理员可禁用用户和删除内容；不能禁用或降级最后一个有效管理员。
- [ ] 使用聚合 SQL 生成已确认的八项总数、类别分组和流转方式分组。
- [ ] 用 HTML/CSS 绘制统计卡片和柱状图，不增加图表依赖。
- [ ] 实现用户表、内容管理操作和二次确认。
- [ ] 运行全部测试，确认权限和统计数值正确。

### Task 6：演示数据、整体验收与文档

**文件：** `app.py`、`README.md`、`static/app.css`、`static/app.js`、`tests/test_app.py`

**产出接口：** CLI `flask --app app init-demo`

- [ ] 初始化管理员、两个学生、示例资源、申请、寻物、拾物和通知；重复执行不能重复插入。
- [ ] 统一中文导航、状态标签、表单错误、403/404/413 页面和手机布局。
- [ ] README 写明 Python 环境、安装、初始化、启动、演示账号、数据目录、5 MB 限制及未来 PyInstaller 数据路径要求。
- [ ] 运行 `python -m unittest -v`，所有检查通过。
- [ ] 从空数据目录执行初始化并启动，手工完成一次“注册→发布→申请→审批→归还”和一次“寻物→拾物→匹配通知”。

## 五、验收标准

- 未登录用户可浏览和搜索，但发布、申请及个人页必须登录。
- 学生无法通过直接构造请求访问管理员操作或审批他人资源。
- 三类资源流转均遵循已确认状态，不能跳过或倒退状态。
- 同一资源最多有一个获批申请，审批不会留下多个有效申请。
- 图片限制、密码哈希、CSRF、账号禁用和最后管理员保护均有效。
- 新寻物/拾物能自动生成不重复的双向站内通知；已解决记录可筛选但不再匹配。
- 管理报表数字与数据库实际数据一致。
- 在全新环境按 README 可完成安装、初始化和启动。

## 六、明确不做

- Docker、Windows `.exe` 打包、云部署、对象存储、数据备份与在线恢复。
- 邮件、短信、微信或推送服务。
- AI 大模型、向量数据库、复杂推荐系统。
- 多图、聊天、支付、信用积分、数据导出、自定义报表时间范围、失物认领申请。
- 未经确认的完整前后端分离与全量 REST API。
