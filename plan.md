# 校园智享社区化增强 Implementation Plan

**实施状态：** 已于 2026-07-25 完成，最终验收命令为 `python -m unittest -v`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变现有资源流转和失物招领流程的前提下，增加轻量校园社区、治理闭环、备份与可解释推荐。

**Architecture:** 保持 Flask + SQLite 单体。新增 `community.py` 承载帖子、互动、评论和推荐查询，并通过工厂函数接收既有认证、上传和通知函数，避免与 `app.py` 循环导入；`app.py` 继续持有应用工厂、现有流程和通用上传能力。社区文本只以 Jinja 自动转义后的纯文本显示，不引入 Markdown、HTML 解析器、机器学习框架或异步任务队列。

**Tech Stack:** Python 3.11+、Flask、SQLite、Jinja2、Werkzeug、stdlib `sqlite3`/`zipfile`、原生 CSS/JavaScript、`unittest`。

## 已确认范围

- 产品仍以资源流转为主；社区提供资源交流、失物招领、学习问答、校园生活、建议反馈五个固定分区。
- 首期有帖子、单层评论/回复、点赞、收藏、关注用户和标签、带短评的转发、`@用户名`、举报和站内通知；不做私信、工单、用户自建分区、富文本、Markdown 或外部图床。
- 资源详情和失物详情也有统一评论区；申请、审批和联系方式继续走原有私有流程。
- 帖子每篇最多一张 JPEG/PNG/WebP，最大 5 MB，沿用受控本地上传；不支持 SVG/GIF。
- 推荐只用分区、标签/关键词、时效、热度和已登录用户行为的规则评分。不引入 `scikit-learn`、`implicit` 或 Torch-RecHub；后两者只在真实数据积累后离线评估。
- 公开注册维持不变，不记录或使用 IP；本期只支持本地/受控演示，不承诺公网部署。现有 CSRF、权限校验、参数化 SQL 和上传白名单不可削弱。
- 自动审核按“拒绝 / 待审 / 发布”三档执行，管理员可下架、恢复、禁言、封禁并审计；内容规则由管理员维护。
- 不提供“减少此类推荐”、兴趣清除或在线数据库恢复。备份可由管理员创建/下载，恢复仅允许停机 CLI；保留 7 个日备份和 4 个周备份。

## 文件结构

- 修改 `app.py`：注册社区 Blueprint、保留现有资源/失物详情并注入评论区、注册静态帮助页和备份 CLI。
- 新建 `community.py`：社区路由、表单校验、内容目标校验、互动、通知、审核前筛和规则推荐。
- 修改 `db.py`：实现 SQLite 一致性备份、归档上传目录、备份轮换和仅 CLI 的恢复。
- 修改 `schema.sql`：新增社区、治理、行为和备份表与索引；不修改既有业务表。
- 新建 `templates/community_*.html`：帖子列表、详情、表单、关注流与静态规则/帮助页。
- 修改 `templates/base.html`、`home.html`、`resource_detail.html`、`lost_found_detail.html`、`admin.html`：导航、面包屑、首页三列表、通用评论区和治理/备份区。
- 修改 `static/app.css`、`static/app.js`：移除首页 Hero、增加紧凑列表、评论与面包屑样式；只保留必要交互。
- 修改 `tests/test_app.py`：为每个新增状态、所有权边界和备份流程增加集成测试。
- 修改 `README.md`：说明社区边界、备份命令、受控演示限制和图片规则。

---

### Task 1: 社区数据模型与可重复初始化

**Files:**
- Modify: `schema.sql`, `tests/test_app.py`

**Produces:** `posts`、`tags`、`post_tags`、`comments`、`content_reactions`、`user_follows`、`tag_follows`、`reposts`、`reports`、`moderation_rules`、`account_restrictions`、`audit_logs`、`behavior_events`、`backup_records` 表及目标查询索引。

- [ ] **Step 1: 写失败测试**：新数据库初始化后断言全部社区表存在；验证同一用户不能重复点赞、收藏、关注用户或关注标签。
- [ ] **Step 2: 运行 `python -m unittest tests.test_app.CampusAppTest -v`**，确认新表断言失败。
- [ ] **Step 3: 在 `schema.sql` 创建表与约束**：帖子状态仅为 `published/pending/withdrawn`；评论状态仅为 `published/withdrawn`；评论目标仅允许 `post/resource/lost_found`；反应目标仅允许这三类内容；报告目标额外允许 `comment`；反应种类仅为 `like/favorite`；报告状态仅为 `open/resolved/rejected`。为 `(target_type,target_id,status,created_at)`、`(user_id,created_at)` 和所有唯一互动组合建索引。
- [ ] **Step 4: 实现前先明确目标完整性规则**：`comments` 和 `content_reactions` 的多态目标由服务端验证，不伪造 SQLite 外键；`posts`、`tags`、`users` 使用外键。
- [ ] **Step 5: 重跑完整测试**，确认旧数据初始化仍可工作且新约束有效。
- [ ] **Step 6: Commit**：`git commit -am "feat: add community schema"`。

### Task 2: 帖子、标签、关注与转发

**Files:**
- Create: `community.py`, `templates/community_list.html`, `templates/community_detail.html`, `templates/community_form.html`, `templates/community_following.html`
- Modify: `app.py`, `static/app.css`, `tests/test_app.py`

**Interfaces:**
- Produces: `create_community_blueprint(login_required, save_image, notify) -> Blueprint`; `validate_post_form(form) -> tuple[dict | None, str | None]`; `target_exists(db, target_type, target_id) -> bool`。
- Routes: `GET /community`、`GET|POST /community/new`、`GET /community/<int:post_id>`、`GET|POST /community/<int:post_id>/edit`、`POST /community/<int:post_id>/withdraw`、`POST /community/users/<int:user_id>/follow`、`POST /community/tags/<int:tag_id>/follow`、`GET /community/following`、`POST /community/<int:post_id>/repost`。

- [ ] **Step 1: 写失败测试**：匿名用户可浏览帖子，登录用户可在固定分区发布标题（50 字）、正文（2,000 字）及 1–5 个规范化标签；非作者编辑返回 403；已下架帖子返回 404。
- [ ] **Step 2: 写失败测试**：关注用户/标签幂等；关注流只显示所关注用户的新帖或含所关注标签的帖子；转发最多 300 字短评且只指向原帖，不创建转发链。
- [ ] **Step 3: 注册 Blueprint**：在 `create_app()` 调用 `app.register_blueprint(create_community_blueprint(login_required, save_image, _notify))`；通过参数复用认证、上传和通知，不从 `community.py` 导入 `app.py`。
- [ ] **Step 4: 实现最小帖子流程**：纯文本以 `white-space: pre-wrap` 显示；标签去空白、统一小写英文和原中文；原帖下架后转发页显示“原内容不可用”；带图片的帖子固定进入 `pending`，直到管理员人工发布。
- [ ] **Step 5: 运行新增帖子与关注测试**，确认帖子不暴露联系方式且转发不改变原帖计数。
- [ ] **Step 6: Commit**：`git add app.py community.py schema.sql templates static tests && git commit -m "feat: add community posts and follows"`。

### Task 3: 统一评论、回复、反应与通知

**Files:**
- Modify: `community.py`, `app.py`, `templates/community_detail.html`, `templates/resource_detail.html`, `templates/lost_found_detail.html`, `templates/notifications.html`, `tests/test_app.py`

**Interfaces:**
- Produces: `comments_for_target(db, target_type, target_id, order) -> list[sqlite3.Row]`; `assert_comment_target(db, target_type, target_id) -> None`。
- Routes: `POST /comments/<target_type>/<int:target_id>`、`POST /comments/<int:comment_id>/reply`、`POST /comments/<int:comment_id>/withdraw`、`POST /reactions/<target_type>/<int:target_id>/<kind>`。

- [ ] **Step 1: 写失败测试**：登录用户能评论帖子、资源和失物；访客只读；回复不能再回复；评论正文最多 1,000 字；所有权以外的删除返回 403。
- [ ] **Step 2: 写失败测试**：同一用户对同一目标点赞/收藏可切换且只保留一条记录；评论、回复、`@用户名`、转发和治理结果才创建通知，点赞、收藏、关注不创建通知。
- [ ] **Step 3: 实现目标校验与评论查询**：对资源检查未下架状态，对失物检查未下架状态，对帖子检查已发布状态；资源申请和失物联系人字段不写入评论模板。
- [ ] **Step 4: 实现单层回复与排序**：评论只允许 `parent_id IS NULL`，回复的 `parent_id` 必须指向顶层评论；列表支持 `new`（创建时间倒序）和 `hot`（点赞数、回复数、创建时间）两种固定排序。
- [ ] **Step 5: 实现纯文本 `@`**：仅匹配现有用户名，通知被提及用户；显示时仍由 Jinja 转义，不能输出 HTML。
- [ ] **Step 6: 运行评论、私有申请和通知测试**，确认跨目标越权与嵌套回复均被拒绝。
- [ ] **Step 7: Commit**：`git commit -am "feat: add shared comments and reactions"`。

### Task 4: 首页重排、面包屑与静态社区文档

**Files:**
- Create: `templates/community_rules.html`, `templates/community_help.html`, `templates/questioning_guide.html`
- Modify: `app.py`, `templates/base.html`, `templates/home.html`, `static/app.css`, `static/app.js`, `tests/test_app.py`

**Interfaces:**
- Routes: `GET /rules`、`GET /help`、`GET /questioning-guide`。

- [ ] **Step 1: 写失败测试**：首页响应不含旧 Hero 标题和 `.hero`，同时含“推荐帖子”“最新资源”“失物招领”三个独立列表；每个列表最多 6 条。
- [ ] **Step 2: 在首页查询三类数据**：推荐帖子由 Task 5 的函数提供；资源和失物分别按现有可见状态与创建时间倒序查询，不能混入已下架内容。
- [ ] **Step 3: 修改基础模板**：社区、规则、帮助入口加入导航；非首页模板显示当前位置面包屑，首页不显示面包屑。
- [ ] **Step 4: 写静态页面**：规则说明发布、举报、审核、禁言和申诉；帮助页说明资源申请与失物联系边界；《提问的智慧》用本项目自己的提问清单表达，不复制外部文章。
- [ ] **Step 5: 运行模板测试和手动窄屏检查**，确认无 Hero 残留、三个列表独立且导航在手机宽度换行可用。
- [ ] **Step 6: Commit**：`git commit -am "feat: simplify home and add community guidance"`。

### Task 5: 行为记录与轻量规则推荐

**Files:**
- Modify: `community.py`, `app.py`, `templates/community_list.html`, `templates/home.html`, `tests/test_app.py`

**Interfaces:**
- Produces: `record_behavior(db, user_id, event_type, target_type, target_id) -> None`; `recommended_posts(db, user_id | None, limit=6) -> list[sqlite3.Row]`。
- Event types: `view_post`、`view_section`、`like`、`favorite`、`comment`、`repost`。

- [ ] **Step 1: 写失败测试**：未登录用户收到按近期热度排序的帖子；登录用户点赞或收藏某标签后，同标签的另一篇帖子排序更靠前；用户自己已互动过的帖子不重复计分。
- [ ] **Step 2: 实现事件去重**：同一用户对同一目标的详情浏览每天只记录一次；点赞、收藏、评论和转发在事务完成后记录一次；匿名访问不落行为表。
- [ ] **Step 3: 实现单条 SQL 可解释评分**：标签/关键词匹配 60 分、7 天内时效最高 25 分、点赞/收藏/评论/转发热度最高 15 分；没有用户事件时只使用时效与热度。查询返回各分项，页面仅显示“为你推荐”，审计日志可查看分数来源。
- [ ] **Step 4: 验证分区混排**：首页最多 6 篇推荐中，同分区、邻近分区、较远分区的候选上限按 `60% / 30% / 10%` 取整；邻近关系固定为“资源交流→学习问答/建议反馈、失物招领→校园生活/资源交流、学习问答→资源交流/校园生活、校园生活→失物招领/学习问答、建议反馈→校园生活/资源交流”，其余为较远分区；候选不足时以最新发布补齐。
- [ ] **Step 5: 运行推荐测试**，确认不新增 `requirements.txt` 依赖，也不调用网络、模型训练或 GPU。
- [ ] **Step 6: Commit**：`git commit -am "feat: add rule based recommendations"`。

### Task 6: 自动审核、举报、账号限制和管理员审计

**Files:**
- Modify: `community.py`, `app.py`, `templates/admin.html`, `templates/community_detail.html`, `tests/test_app.py`

**Interfaces:**
- Produces: `screen_content(db, text, has_image=False) -> tuple[str, str]`; `audit(db, actor_id, action, target_type, target_id, detail) -> None`。
- Routes: `POST /reports/<target_type>/<int:target_id>`、`POST /admin/reports/<int:report_id>/<action>`、`POST /admin/users/<int:user_id>/restrict`、`POST /admin/users/<int:user_id>/restore`、`GET /admin/audit`。

- [ ] **Step 1: 写失败测试**：高严重度规则拒绝发布，普通风险规则令帖子进入待审，未命中规则直接发布；普通用户不能查看或处理举报。
- [ ] **Step 2: 实现规则读取**：`moderation_rules` 保存匹配词、严重度（`reject/review`）、启用状态和管理员说明；文本归一化后匹配标题、正文、评论与转发短评，命中原因只对管理员可见；任何带图片的帖子返回 `review`，不假装已有图片识别能力。
- [ ] **Step 3: 实现举报闭环**：每用户每目标只可有一个未解决举报；管理员可驳回、下架、恢复或限制账号；动作写入 `audit_logs` 并向当事人发站内通知。
- [ ] **Step 4: 实现账号限制**：禁言阻止发帖、评论、转发和举报但不阻止浏览；临时封禁阻止登录直到截止时间；永久封禁继续复用 `users.is_active=0`。所有限制仅按账号执行，不存储 IP。
- [ ] **Step 5: 管理页只展示可操作的最近记录**：举报队列、待审帖子、活跃限制、最近 100 条审计日志；不做复杂检索或在线恢复。
- [ ] **Step 6: 运行治理测试**，确认受限用户无法写入、管理员操作可追溯、最后有效管理员保护仍有效。
- [ ] **Step 7: Commit**：`git commit -am "feat: add community moderation controls"`。

### Task 7: 备份、恢复说明、演示数据与文档

**Files:**
- Modify: `db.py`, `app.py`, `templates/admin.html`, `README.md`, `tests/test_app.py`

**Interfaces:**
- CLI: `flask --app app create-backup`、`flask --app app restore-backup <archive>`。
- Produces: `create_backup(data_dir: Path, database: Path) -> Path`; `prune_backups(backup_dir: Path) -> None`。

- [ ] **Step 1: 写失败测试**：备份 archive 包含 `app.db` 和 `uploads/`；创建第 8 个日备份后最早日备份被移除；恢复命令在未显式 `--confirm` 时拒绝执行。
- [ ] **Step 2: 实现一致性备份**：使用 `sqlite3.Connection.backup()` 写入临时数据库，再用 `zipfile` 打包数据库和上传目录；完成后原子移动到 `DATA_DIR/backups/` 并写入 `backup_records`。
- [ ] **Step 3: 实现保留规则**：保留最近 7 个按日创建的 archive，以及最近 4 个按周创建的 archive；删除前只处理该备份目录下匹配命名规则的文件。
- [ ] **Step 4: 实现恢复 CLI**：仅在应用停止时运行；先创建恢复前备份，再解压指定 archive 覆盖数据库与上传目录；`--confirm` 缺失时退出非零。管理员后台只提供创建和下载，不提供恢复按钮。
- [ ] **Step 5: 更新演示和 README**：演示数据包含五分区帖子、标签、关注、评论和举报；README 写明备份、恢复、图片上限、无公网部署承诺及推荐算法边界。
- [ ] **Step 6: 运行 `python -m unittest -v`**，确认全部集成测试通过，并用空数据目录执行 `init-demo`、创建备份和恢复演练。
- [ ] **Step 7: Commit**：`git commit -am "feat: add backups and community operations"`。

## 验收标准

- 首页没有大彩色 Hero，且“推荐帖子 / 最新资源 / 失物招领”三个列表独立显示。
- 帖子、资源和失物都有登录可写、访客可读的单层评论；申请数据和联系方式不通过评论泄露。
- 五个固定分区、用户/标签关注、点赞、收藏、受限转发和 `@` 通知均可用；点赞、收藏、关注不会制造通知。
- 社区内容仅支持纯文本和一张受控图片；Jinja 渲染不执行用户输入的 HTML。
- 推荐在无行为数据时可用，登录用户的标签互动会影响排序，且不依赖训练数据或新增 ML 依赖。
- 自动审核、举报、下架/恢复、禁言/封禁、审计和账号通知形成闭环；不记录或使用 IP。
- 管理员可创建/下载备份；恢复只能通过带 `--confirm` 的停机 CLI；旧的资源流转、失物匹配和管理员保护测试继续通过。

---

## 信用机制增量实施计划

> 适用范围：在保留现有数据、图片与流转记录的前提下，新增信用评分、申诉和权限控制；不追溯历史流转。

### 目标与固定规则

- 新用户及迁移前的全部用户初始信用分为 **100**，分数范围 **0–120**。
- 分档：100–120 优先、80–99 正常、60–79 靠后、0–59 受限。
- 物品按时归还 +2；逾期第 1 / 4 / 8 天累计为 -5 / -10 / -20；借用方责任的管理员终止 -15。
- 技能服务双方确认完成各 +1；经管理员裁定，服务方或申请方爽约各 -10。
- 正向流转奖励按中国时区限制为每日最多 +2、自然周最多 +6；未发放部分写入 +0 记录。分数低于 100 且无逾期借用时，每日恢复 +1，最多恢复到 100。
- 所有扣分可在 30 天内申诉一次；管理员维持或撤销。撤销写入补偿事件，不删除原始记录。管理员手动调整范围 -20 到 +20，理由必填。

### 实施步骤

- [ ] **Step 1：测试先行**：为积分边界、每日/每周奖励上限、逾期分段、自然恢复、补偿事件和权限档位编写最小可运行测试。
- [ ] **Step 2：数据库与迁移**：增加 `users.credit_score`、恢复日期，以及不可变的 `credit_events`、`credit_appeals`；在 `init_db()` 中执行可重复的加列迁移，旧用户统一保留为 100 分。
- [ ] **Step 3：信用服务**：新增单一 `credit.py`，集中保存规则常量、分档、奖励限制、事件写入、逾期/恢复结算和折线图数据计算；使用标准库 `zoneinfo.ZoneInfo('Asia/Shanghai')`。
- [ ] **Step 4：接入流转**：申请前检查发布/申请权限及受限档位的待审批、进行中上限；发布者候选列表按信用档位与申请时间排序并仅展示分数、档位、近 90 天扣分类型；归还、完成和管理员归责在同一事务写入信用事件。
- [ ] **Step 5：个人中心**：将个人资料扩展为概览、我的发布、我的流转、信用中心四个入口；信用中心提供 30/90 天原生 SVG 折线图、事件列表、申诉表单和规则说明；顶栏个人中心改为键盘可达的悬浮/点击快捷菜单，退出登录保留 CSRF POST。
- [ ] **Step 6：管理端与通知**：管理后台增加信用概览、待处理申诉、用户信用明细、手工调整和终止归责表单；重要扣分、档位变化和申诉结果发送站内通知并写入现有审计日志。
- [ ] **Step 7：验证**：运行完整单元测试，并验证历史数据库启动迁移、归还积分、申诉补偿、低分权限和个人中心图表接口。

### 验收标准

- 旧数据库升级后不丢失任何资源、流转或图片，且存量用户信用分均为 100。
- 借用方实际发起归还的时间决定是否准时；逾期不会重复扣分，管理员归责和申诉补偿均可追溯。
- 用户只能看到自己的完整信用信息；资源发布者仅能看到候选人的允许披露字段；管理员可审计所有操作。
- 低信用用户仍可完成已开始的归还/确认和申诉，但会按已确认分档被限制发布或新申请。
