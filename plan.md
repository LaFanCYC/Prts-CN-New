# 前端优化计划 — 社区规范、用户文档、UX 提升

> 状态：待审核  
> 基于提交 `8c9c602`

---

## 1. 社区规范页面 `/guidelines`

**新增文件：** `templates/guidelines.html`  
**路由变更：** `app.py` 新增 `@app.route("/guidelines")`  
**CSS 变更：** 新增 `.guidelines` 样式（有序列表、引用块）  
**页脚入口：** `base.html` 页脚加 `社区规范` 链接  
**注册引用：** `auth.html` 注册表单底部加 "注册即表示同意社区规范"

预估：+80 行模板，+5 行 Python，+30 行 CSS

---

## 2. 用户帮助中心 `/help`

**新增文件：** `templates/help.html`  
**路由变更：** `app.py` 新增 `@app.route("/help")`  
**JS 变更：** `app.js` 新增 FAQ 折叠/展开（`<details>` 或自定义 toggle）  
**入口：** 页脚 + 侧边栏「帮助」链接

预估：+120 行模板，+5 行 Python，+20 行 JS

---

## 3. 面包屑导航

**变更文件：** `base.html`（新增 `{% block breadcrumb %}`）  
**更新模板：** `resource_detail.html`、`lost_found_detail.html`、`admin.html`、`applications.html`、`notifications.html`、`profile.html`（各加一行面包屑）  
**CSS 变更：** `.breadcrumb` 样式（小号灰色文字，`>` 分隔符）

格式：`首页 > 资源大厅 > 高等数学第七版`

预估：+10 行 base，+20 行各模板，+15 行 CSS

---

## 4. 徽章系统完善

### 4a. Profile 徽章 tab 改为全部展示
**变更文件：** `profile.html`  
将「我的徽章」tab 改为显示全部 7 枚徽章，已获得的带 `earned` 高亮 + 授予时间，未获得的灰色半透明 + 「未获得」标签

### 4b. 首页侧边面板加徽章进度
**变更文件：** `home.html`  
登录用户右侧面板显示 `已获得 2/7 枚徽章` + 进度条 + 徽章墙链接  
**后端变更：** `app.py` index 路由需传 `user_badge_count`

预估：+20 行模板，+2 行 Python

---

## 5. UX 优化

### 5a. 空状态优化
**变更文件：** `home.html`、`resources.html`、`lost_found.html`、`applications.html`、`notifications.html`、`badges.html`  
当前 `class="empty"` 纯文字 → 改为 emoji + 引导文案 + 行动按钮

### 5b. 表单验证内联提示
**变更文件：** `resource_form.html`、`lost_found_form.html`、`auth.html`  
当前错误通过 flash 顶部显示 → 加字段级 `class="field-error"` 红色边框 + 提示文字

### 5c. 筛选无结果引导
**变更文件：** `resources.html`、`lost_found.html`  
无结果时显示「换个条件试试」+ 「清除所有筛选」链接

### 5d. 移动端遮罩动画
**变更文件：** `app.css`  
`.sidebar-overlay` 加 `opacity` 过渡动画

预估：+60 行模板变动，+25 行 CSS

---

## 6. 界面统一整理

### 6a. 间距标准化
**变更文件：** `app.css`  
统一 `.card`、`.panel`、`.discussion-item` 内边距为 `20px`，卡片间距为 `16px`

### 6b. 颜色微调
**变更文件：** `app.css`  
给 `--blue` 加一点饱和度（`#4f6f8f` → `#3d5a80`），增加视觉层次

### 6c. 字体层级
**变更文件：** `app.css`  
h3 从 14px 调整为 15px，card title 等关键文字加粗

### 6d. SVG 图标补位
**变更文件：** `base.html`、`app.css`  
导航链接前加简洁 SVG 图标（首页 🏠 → `<svg>` house icon），保持一致性

预估：+30 行 CSS，+10 行模板

---

## 改动范围汇总

| 模块 | 新增文件 | 修改文件 | 预估行数 |
|---|---|---|---|
| 社区规范 | `guidelines.html` | `app.py`, `base.html`, `auth.html`, `app.css` | +120 |
| 帮助中心 | `help.html` | `app.py`, `base.html`, `app.js` | +150 |
| 面包屑 | - | `base.html`, 6 个模板, `app.css` | +45 |
| 徽章完善 | - | `profile.html`, `home.html`, `app.py` | +25 |
| UX 优化 | - | 8 个模板, `app.css` | +85 |
| 界面统一 | - | `app.css`, `base.html` | +40 |
| **总计** | **2** | **~14** | **~465** |

---

## 执行顺序建议

1. 界面统一整理（CSS 先行，后续改动基于稳定样式）
2. 面包屑导航（base.html 结构改动）
3. UX 优化（模板层面改动）
4. 徽章完善
5. 社区规范 + 帮助中心（新页面，最后加）

---

> 审核通过后按顺序执行，每步完成后本地 git commit。
