## 测试数据填充方案

### 概述

通过 Python 脚本模拟用户行为（HTTP 请求），为项目批量注入测试账号、帖子、评论和互动数据，用于功能演示和开发调试。所有操作通过运行中的 Flask 服务完成，不直接操作数据库。

### 脚本结构

```
scripts/
├── clean_db.py      # 清库脚本（sqlite3 直连）—— 保留管理员
└── seed_test_data.py  # 数据填充脚本（HTTP 调用）
```

### 执行流程

```
1. 启动 Flask 开发服务器  python app.py
2. 清库（保留管理员）    python scripts/clean_db.py
3. 填充测试数据          python scripts/seed_test_data.py --users 80
```

### clean_db.py — 清库脚本

| 项 | 说明 |
|---|---|
| 运行方式 | `python scripts/clean_db.py` |
| 操作数据库 | SQLite3 直连（不依赖 Flask 运行） |
| 保留数据 | `users` 表中 `role = 'admin'` 的行 |
| 清空表 | posts, resources, lost_found, comments, reactions, follows, notifications, applications, reports, audit_logs, credit_events, credit_appeals, account_restrictions, login_attempts, login_audit, moderation_rules（保留表结构） |
| 保留表结构 | 全部 DROP + 重新执行 schema.sql CREATE |
| 额外操作 | 插入预设敏感词库（300-500条），插入公告示例 |

**实现要点：**

- 读取 `schema.sql` 用 `sqlite3` 标准库执行建表
- 管理员账号：硬编码默认管理员（username=admin），INSERT 回 users 表
- 所有 DELETE/TRUNCATE 不依赖外键级联，逐表清理以控制顺序
- 运行结束输出清理的表名和保留的管理员信息

### seed_test_data.py — 数据填充脚本

**命令行接口：**

```bash
python scripts/seed_test_data.py --users 80 --base-url http://127.0.0.1:5000
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--users` | 80 | 测试用户数量（50-100） |
| `--base-url` | `http://127.0.0.1:5000` | Flask 服务地址 |
| `--seed` | 42 | 随机种子（可复现） |

**依赖：**

```text
requests>=2.32,<3
```

脚本自带（不写入项目 requirements.txt），因为仅开发用途。

#### 阶段1：注册测试用户

- 中文姓名库：内置 100 个中文姓名，每个带性别标记
- 学号：按 `20XX01XX` 格式生成（年级 + 班级 + 序号）
- 年级/班级：随机分配高一到高三（2024/2025/2026 级），每级 1-8 班
- 统一密码：`Test1234`
- 注册方式：`POST /register`，先 GET `/register` 获取 CSRF token
- 冲突处理：用户名已存在则跳过（幂等）
- 进度输出：每注册 10 个用户打印一行

#### 阶段2：登录并缓存 session

- 所有已注册用户依次 `POST /login`
- 维持 `requests.Session()` 对象，自动携带 cookie
- 登录失败重试 1 次，仍失败则跳过该用户后续操作
- 每个 session 对象存入 `{user_id: session}` 字典

#### 阶段3：发布帖子

**帖子模板池**（30 条，由我负责编写）：

覆盖 6 个板块，每板块 5 条模板：

- **学习交流**：求笔记、分享学习方法、考试经验、题库推荐
- **二手交易**：出售/求购教材、电子产品、生活用品
- **失物招领**：捡到/丢失物品描述
- **活动组织**：社团招新、比赛组队、志愿者招募
- **吐槽灌水**：食堂评价、校园趣事、作业吐槽
- **技术讨论**：编程求助、工具推荐、项目合作

每条模板含：`title`（15-30字）、`body`（80-200字）、`section`（板块名）、`tags`（1-3个标签）。

**分配规则：**

- 用户帖子数服从 `randint(0, 10)`，总上限 600
- 6 个板块每板块约 100 帖，实际按模运算平摊
- 模板随机抽取，不重复使用同一用户

#### 阶段4：添加评论

- 每帖评论数：幂律分布 `max(0, int(expovariate(1/3)) - 1)`（期望 2 条）
- 评论内容：从 30 条中文评论模板库随机选取
- 50% 概率一条评论被回复（reply，仅一级嵌套）
- 评论者：随机选择已登录用户（避开帖子作者本人）
- 端点：`POST /comments/post/<post_id>`, `POST /comments/<comment_id>/reply`

#### 阶段5：互动操作

- **点赞**：每帖赞数幂律 `expovariate(1/5)`（期望 5），20% 的帖子聚集 80% 的赞
- **收藏**：每帖 `expovariate(1/10)`（期望 0.1），大部分为 0
- **转发**：每帖 `expovariate(1/20)`，极少数帖子被转发
- 操作者：随机用户，不能是帖子作者
- 端点：`POST /reactions/post/<id>/like`, `POST /reactions/post/<id>/favorite`, `POST /community/<id>/repost`

#### 阶段6：生成失物招领与资源共享

- 失物：15 条 "lost" + 15 条 "found"，端点 `POST /lost-found/new/lost` 和 `POST /lost-found/new/found`
- 资源：30 条学习资源，端点 `POST /resources/new`
- 每条附带申请和审批记录（2-3条申请/资源）

### 幂等性设计

- 重复运行前必须先执行 `clean_db.py`
- 用户名冲突时注册跳过（不报错）
- 随机种子固定，相同参数产生相同数据
- 所有 HTTP 请求加入 `timeout=10`，超时打印警告继续

### 进度输出示例

```
[1/4] 注册用户...  80/80 完成 (跳过 0)
[2/4] 登录...      80/80 完成
[3/4] 发布内容...  社区 99 | 资源 30 | 失物 30 | 评论 158 | 互动 247
[4/4] 完成。http://127.0.0.1:5000
```

### 实施步骤

- [ ] Step 1 — 创建 `scripts/` 目录
- [ ] Step 2 — 编写 `clean_db.py`（sqlite3 直连，保留管理员）
- [ ] Step 3 — 编写 `seed_test_data.py` 骨架（CLI 参数、session 管理）
- [ ] Step 4 — 编写帖子模板池（30 条）和评论模板池（30 条）
- [ ] Step 5 — 实现注册 + 登录阶段
- [ ] Step 6 — 实现帖子/资源/失物发布阶段
- [ ] Step 7 — 实现评论和互动阶段
- [ ] Step 8 — 端到端测试（清库 → 填充 → 验证页面显示正常）

