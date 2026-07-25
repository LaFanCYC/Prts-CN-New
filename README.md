# 校园智享——资源智能流转平台

一个 Flask + SQLite 单体 Web 应用，包含学生账号、实体资源与技能服务、申请审批、借用归还、失物招领自动匹配、站内通知和管理员统计。

社区模块提供五个固定分区、纯文本帖子、单层评论/回复、点赞、收藏、关注用户与标签、转发、举报和站内通知。资源与失物详情也可公开浏览评论，发布评论仍需登录；资源申请、审批和联系方式不会进入公开评论区。

## 本地启动

需要 Python 3.11 或更高版本。

### 一键脚本

Linux：

```bash
chmod +x init_linux.sh start_linux.sh
./init_linux.sh
./start_linux.sh
```

Windows：双击或在命令提示符中依次运行：

```bat
init_windows.bat
start_windows.bat
```

初始化脚本会创建 `.venv`、安装依赖、初始化数据库，并在尚无管理员时交互创建管理员。若只用于本地演示，可执行 `./init_linux.sh --demo` 或 `init_windows.bat --demo`，写入下方演示账号。

启动脚本默认监听 `127.0.0.1:5000`。可用 `CAMPUS_DATA_DIR` 指定数据库和上传目录；局域网部署前可设置环境变量：

```bash
CAMPUS_DATA_DIR=/srv/campus-data CAMPUS_HOST=0.0.0.0 CAMPUS_PORT=8000 ./start_linux.sh
```

```bat
set CAMPUS_HOST=0.0.0.0
set CAMPUS_PORT=8000
set CAMPUS_DATA_DIR=D:\CampusSmartFlowData
start_windows.bat
```

### 手动启动

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
flask --app app init-demo
waitress-serve --host 127.0.0.1 --port 5000 --call app:create_app
```

浏览器访问 <http://127.0.0.1:5000>。局域网演示时将 `127.0.0.1` 改为 `0.0.0.0`，其他设备使用运行电脑的局域网 IP 访问；不要把本项目直接暴露到公网。

开发调试可使用：

```bash
flask --app app run --debug
```

## 演示账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 管理员 | `admin` | `admin123` |
| 学生 | `student01` | `student123` |
| 学生 | `student02` | `student123` |

`init-demo` 可重复执行，不会重复生成数据。演示密码只适用于本机展示，实际使用前请在个人中心或管理后台修改。

## 数据位置

- Windows：`%LOCALAPPDATA%\CampusSmartFlow\`
- Linux/macOS：`~/.local/share/CampusSmartFlow/`

目录内包含 `app.db`、`secret.key` 和 `uploads/`。图片支持 JPG、PNG、WebP，单次请求最大 5 MB。后续使用 PyInstaller 打包时应继续保留这个外部可写目录，不要把数据库或上传目录塞进 `.exe`。

如需完全重建本地演示环境，先关闭程序，手工移走上述数据目录，再执行 `flask --app app init-demo`。此操作会移除原有本地数据，请先自行确认。

## 备份与恢复

管理员可在管理后台创建并下载备份。命令行也可创建手动、日或周备份：

```bash
flask --app app create-backup
flask --app app create-backup --kind daily
flask --app app create-backup --kind weekly
```

备份位于数据目录的 `backups/`，包含一致性 SQLite 快照及 `uploads/`；系统保留最近 7 个日备份和 4 个周备份。自动定时执行应由操作系统计划任务调用上述 CLI，本应用不常驻调度任务。

恢复前必须停止服务，命令会先创建一份恢复前备份：

```bash
flask --app app restore-backup manual-YYYYMMDD-HHMMSS-ffffff.zip --confirm
```

管理后台故意不提供在线恢复按钮。

## 推荐与部署边界

首页推荐使用标签/关键词、时效、互动热度和当前账号行为进行可解释排序，不需要训练数据，也不依赖 `scikit-learn`、`implicit` 或 Torch-RecHub。当前版本不记录或使用 IP，仅面向本地或受控校园演示；不要直接作为无外部防护的公网社区部署。

社区帖子使用普通纯文本编辑器，每帖最多一张 JPG、PNG 或 WebP，最大 5 MB。带图片帖子进入人工审核；不支持 Markdown、原始 HTML、SVG、GIF 或外部图床。

## 功能验收

1. 使用两个学生账号分别发布资源和提交申请。
2. 发布者在“流转记录”中审批；借用人发起归还，发布者确认。
3. 发布一个技能服务，完成“服务进行中 → 待确认 → 已完成”，确认资源重新开放。
4. 两个学生分别发布关键词相近的寻物和拾物信息，在“通知”中查看双向匹配。
5. 使用管理员账号查看统计、调整角色、禁用账号及下架内容。
6. 发布社区帖子并完成评论、回复、关注、转发和举报处理。
7. 在管理后台创建备份并下载，停机后用 CLI 演练恢复。

## 自动检查

```bash
python -m unittest -v
```

测试使用临时 SQLite 数据库，不会修改本地演示数据。
