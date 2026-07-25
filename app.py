import os
import re
import secrets
import sqlite3
import uuid
from datetime import date
from difflib import SequenceMatcher
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

import click
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_from_directory,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import default_data_dir, get_db, init_app as init_db_app, init_db


RESOURCE_CATEGORIES = ("教材书籍", "实验器材", "电子设备", "文体用品", "学习资料", "技能服务", "其他")
CONDITION_LEVELS = ("全新", "九成新", "七成新", "明显使用痕迹")
PHYSICAL_MODES = ("borrow", "exchange", "gift")
SKILL_MODES = ("free_help", "skill_exchange")
MODE_LABELS = {
    "borrow": "免费借用", "exchange": "交换", "gift": "赠送",
    "free_help": "免费互助", "skill_exchange": "技能交换",
}
STATUS_LABELS = {
    "available": "可申请", "in_use": "借用中", "in_service": "服务中",
    "completed": "已完成", "withdrawn": "已下架",
}
APPLICATION_STATUS_LABELS = {
    "pending": "待审批", "borrowed": "借用中", "return_pending": "待确认归还",
    "returned": "已归还", "rejected": "已拒绝", "completed": "已完成",
    "in_service": "服务进行中", "completion_pending": "待确认完成", }
BADGE_TIERS = ("bronze", "silver", "gold")
BADGE_TIER_COLORS = {"bronze": "#cd7f32", "silver": "#8a99a5", "gold": "#daa520"}
BADGE_DEFINITIONS = [
    {"id": 1, "name": "初次分享", "description": "发布第一条资源或技能服务", "tier": "bronze", "icon": "📦"},
    {"id": 2, "name": "热心互助", "description": "完成第一次流转申请", "tier": "bronze", "icon": "🤝"},
    {"id": 3, "name": "火眼金睛", "description": "发布并解决第一条失物招领", "tier": "bronze", "icon": "🔍"},
    {"id": 4, "name": "靠谱发布者", "description": "累计完成5次以上资源流转", "tier": "silver", "icon": "⭐"},
    {"id": 5, "name": "寻物达人", "description": "解决3条以上失物招领", "tier": "silver", "icon": "🏆"},
    {"id": 6, "name": "流转达人", "description": "累计完成10次以上流转", "tier": "gold", "icon": "🏅"},
    {"id": 7, "name": "诚信之星", "description": "出借归还率100%且满5次", "tier": "gold", "icon": "💎"},
]
BADGE_BY_ID = {b["id"]: b for b in BADGE_DEFINITIONS}
def _seed_badges(db):
    for badge in BADGE_DEFINITIONS:
        db.execute(
            "INSERT OR IGNORE INTO badges(id,name,description,tier,icon) VALUES(?,?,?,?,?)",
            (badge["id"], badge["name"], badge["description"], badge["tier"], badge["icon"]),
        )
    db.commit()



def _secret_key(data_dir: Path) -> str:
    key_file = data_dir / "secret.key"
    if key_file.exists():
        if os.name != "nt":
            key_file.chmod(0o600)
        return key_file.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    if os.name != "nt":
        key_file.chmod(0o600)
    return key


def create_app(test_config=None) -> Flask:
    app = Flask(__name__)
    data_dir = Path(
        (test_config or {}).get("DATA_DIR")
        or os.environ.get("CAMPUS_DATA_DIR")
        or default_data_dir()
    )
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        data_dir.chmod(0o700)
    upload_dir = Path((test_config or {}).get("UPLOAD_FOLDER", data_dir / "uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        upload_dir.chmod(0o700)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CAMPUS_SECRET_KEY") or _secret_key(data_dir),
        DATABASE=str(data_dir / "app.db"),
        DATA_DIR=str(data_dir),
        UPLOAD_FOLDER=str(upload_dir),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        CSRF_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    init_db_app(app)
    with app.app_context():
        init_db()

    @app.before_request
    def load_user_and_check_csrf():
        user_id = session.get("user_id")
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_id
            else None
        )
        if g.user is not None and not g.user["is_active"]:
            session.clear()
            g.user = None
        if g.user is not None:
            _check_overdue(g.user["id"])
            if g.user["must_change_password"] and request.endpoint not in {
                "profile", "logout", "static"
            }:
                return redirect(url_for("profile"))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and app.config.get(
            "CSRF_ENABLED", True
        ):
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(
                supplied, session.get("csrf_token", "")
            ):
                abort(400, "请求已过期，请刷新页面后重试。")

    @app.context_processor
    def shared_template_values():
        token = session.setdefault("csrf_token", secrets.token_urlsafe(32))
        unread = 0
        if g.get("user"):
            unread = get_db().execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
                (g.user["id"],),
            ).fetchone()[0]
        return {
            "csrf_token": token,
            "unread_count": unread,
            "mode_labels": MODE_LABELS,
            "status_labels": STATUS_LABELS,
            "application_status_labels": APPLICATION_STATUS_LABELS,
            "today": date.today().isoformat(),
        }

    @app.cli.command("init-demo")
    def init_demo_command():
        _seed_demo()
        click.echo("演示数据已就绪。管理员：admin / admin123")

    @app.cli.command("create-admin")
    def create_admin_command():
        db = get_db()
        if _active_admins(db):
            click.echo("已有有效管理员，跳过创建。")
            return
        username = click.prompt("管理员用户名").strip()
        password = click.prompt("管理员密码", hide_input=True, confirmation_prompt="再次输入密码")
        name = click.prompt("姓名").strip()
        student_no = click.prompt("工号/学号").strip()
        grade = click.prompt("年级/身份").strip()
        class_name = click.prompt("班级/部门").strip()
        contact = click.prompt("联系方式", default="", show_default=False).strip()
        if not all((username, name, student_no, grade, class_name)) or len(password) < 8:
            raise click.ClickException("必填项不能为空，密码至少 8 位。")
        try:
            db.execute(
                "INSERT INTO users(username,password_hash,name,student_no,grade,class_name,contact,role) VALUES(?,?,?,?,?,?,?,'admin')",
                (username, generate_password_hash(password), name, student_no, grade, class_name, contact),
            )
            db.commit()
        except sqlite3.IntegrityError as exc:
            raise click.ClickException("用户名或工号/学号已存在。") from exc
        click.echo(f"管理员 {username} 已创建。")

    @app.route("/")
    def index():
        resources = get_db().execute(
            "SELECT r.*, u.name owner_name, (SELECT COUNT(*) FROM applications a WHERE a.resource_id=r.id) app_count FROM resources r JOIN users u ON u.id = r.owner_id "
            "WHERE r.status != 'withdrawn' ORDER BY r.created_at DESC LIMIT 6"
        ).fetchall()
        categories = get_db().execute("SELECT category,COUNT(*) cnt FROM resources WHERE status!='withdrawn' GROUP BY category ORDER BY cnt DESC").fetchall()
        return render_template("home.html", resources=resources, category_counts=categories)

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if request.method == "GET":
            return render_template("auth.html", mode="register")
        values = {key: request.form.get(key, "").strip() for key in (
            "username", "name", "student_no", "grade", "class_name"
        )}
        password = request.form.get("password", "")
        error = None
        if not all(values.values()):
            error = "请完整填写注册信息。"
        elif len(values["username"]) > 30 or len(values["student_no"]) > 30:
            error = "用户名或学号过长。"
        elif len(password) < 8:
            error = "密码至少需要 8 位。"
        elif password != request.form.get("password_confirm"):
            error = "两次输入的密码不一致。"
        if error:
            return render_template("auth.html", mode="register", error=error), 400
        db = get_db()
        try:
            db.execute(
                "INSERT INTO users(username,password_hash,name,student_no,grade,class_name) VALUES(?,?,?,?,?,?)",
                (
                    values["username"], generate_password_hash(password), values["name"],
                    values["student_no"], values["grade"], values["class_name"],
                ),
            )
            db.commit()
        except sqlite3.IntegrityError as exc:
            if "users.username" in str(exc):
                error = "用户名已存在。"
            elif "users.student_no" in str(exc):
                error = "学号已存在。"
            else:
                raise
            return render_template("auth.html", mode="register", error=error), 400
        flash("注册成功，请登录。", "success")
        return redirect(url_for("login"))

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if request.method == "GET":
            return render_template("auth.html", mode="login")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username", "").strip(),)
        ).fetchone()
        if user and not user["is_active"]:
            return render_template("auth.html", mode="login", error="账号已被禁用。"), 403
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            return render_template("auth.html", mode="login", error="用户名或密码错误。"), 400
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        if user["must_change_password"]:
            flash("请立即修改临时密码。", "warning")
            return redirect(url_for("profile"))
        return redirect(_safe_next(request.args.get("next")) or url_for("index"))

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("index"))

    @app.route("/profile", methods=("GET", "POST"))
    @login_required
    def profile():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            grade = request.form.get("grade", "").strip()
            class_name = request.form.get("class_name", "").strip()
            contact = request.form.get("contact", "").strip()
            password = request.form.get("new_password", "")
            if not name or not grade or not class_name or len(contact) > 100:
                return render_template("profile.html", error="资料不完整或联系方式超过 100 字。"), 400
            if password and (len(password) < 8 or password != request.form.get("password_confirm")):
                return render_template("profile.html", error="新密码至少 8 位且两次输入必须一致。"), 400
            db = get_db()
            db.execute(
                "UPDATE users SET name=?, grade=?, class_name=?, contact=? WHERE id=?",
                (name, grade, class_name, contact, g.user["id"]),
            )
            if password:
                db.execute(
                    "UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?",
                    (generate_password_hash(password), g.user["id"]),
                )
            db.commit()
            flash("个人资料已更新。", "success")
            return redirect(url_for("profile"))
        db = get_db()
        stats = {
            "resources": db.execute("SELECT COUNT(*) FROM resources WHERE owner_id=? AND status!='withdrawn'", (g.user["id"],)).fetchone()[0],
            "applications": db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=?", (g.user["id"],)).fetchone()[0],
            "completed": db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=? AND status IN ('returned','completed')", (g.user["id"],)).fetchone()[0],
        }
        score = stats["resources"] * 2 + stats["completed"] * 3 + stats["applications"]
        if score >= 50: level, next_at = "核心贡献者", 50
        elif score >= 30: level, next_at = "可信用户", 50
        elif score >= 15: level, next_at = "活跃成员", 30
        elif score >= 5: level, next_at = "普通用户", 15
        else: level, next_at = "新用户", 5
        trust = {"level": level, "score": score, "percent": min(int(score / next_at * 100), 100)}
        my_badges = [dict(b) for b in db.execute(
            "SELECT ub.*,bd.name,bd.description,bd.tier,bd.icon FROM user_badges ub JOIN badges bd ON bd.id=ub.badge_id WHERE ub.user_id=?", (g.user["id"],)).fetchall()]
        earned_ids = {b["badge_id"] for b in my_badges}
        return render_template("profile.html", stats=stats, trust=trust, my_badges=my_badges, all_badges=BADGE_DEFINITIONS, earned_ids=earned_ids)

    @app.route("/resources")
    def resources():
        page = max(request.args.get("page", 1, type=int), 1)
        filters = {
            key: request.args.get(key, "").strip()
            for key in ("q", "category", "transfer_mode", "condition_level", "status")
        }
        where = ["r.status != 'withdrawn'"]
        params = []
        if filters["q"]:
            term = f"%{filters['q']}%"
            where.append("(r.name LIKE ? OR r.description LIKE ? OR r.keywords LIKE ?)")
            params.extend((term, term, term))
        for key in ("category", "transfer_mode", "condition_level", "status"):
            if filters[key]:
                where.append(f"r.{key} = ?")
                params.append(filters[key])
        db = get_db()
        rows = db.execute(
            "SELECT r.*,u.name owner_name,(SELECT COUNT(*) FROM applications a WHERE a.resource_id=r.id) app_count FROM resources r JOIN users u ON u.id=r.owner_id WHERE "
            + " AND ".join(where)
            + " ORDER BY r.created_at DESC,r.id DESC LIMIT 12 OFFSET ?",
            (*params, (page - 1) * 12),
        ).fetchall()
        total = db.execute(
            "SELECT COUNT(*) FROM resources r WHERE " + " AND ".join(where), params
        ).fetchone()[0]
        return render_template(
            "resources.html", resources=rows, filters=filters, page=page,
            has_next=page * 12 < total, categories=RESOURCE_CATEGORIES,
            conditions=CONDITION_LEVELS,
        )

    @app.route("/resources/new", methods=("GET", "POST"))
    @login_required
    def resource_new():
        if request.method == "GET":
            return render_template(
                "resource_form.html", categories=RESOURCE_CATEGORIES,
                conditions=CONDITION_LEVELS, resource=None,
            )
        data, error = _resource_form_data(request.form)
        image_name = None
        if not error:
            try:
                image_name = save_image(request.files.get("image"))
            except ValueError as exc:
                error = str(exc)
        if error:
            return render_template(
                "resource_form.html", categories=RESOURCE_CATEGORIES,
                conditions=CONDITION_LEVELS, resource=request.form, error=error,
            ), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO resources(owner_id,name,category,condition_level,transfer_mode,description,keywords,image_name) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (g.user["id"], data["name"], data["category"], data["condition_level"],
             data["transfer_mode"], data["description"], data["keywords"], image_name),
        )
        db.commit()
        flash("资源发布成功。", "success")
        return redirect(url_for("resource_detail", resource_id=cursor.lastrowid))

    @app.route("/resources/<int:resource_id>")
    def resource_detail(resource_id):
        resource = get_db().execute(
            "SELECT r.*,u.name owner_name,u.grade,u.class_name FROM resources r "
            "JOIN users u ON u.id=r.owner_id WHERE r.id=? AND r.status!='withdrawn'",
            (resource_id,),
        ).fetchone()
        if resource is None:
            abort(404)
        application = None
        owner_applications = []
        if g.user:
            application = get_db().execute(
                "SELECT * FROM applications WHERE resource_id=? AND applicant_id=? ORDER BY id DESC LIMIT 1",
                (resource_id, g.user["id"]),
            ).fetchone()
            if g.user["id"] == resource["owner_id"]:
                owner_applications = get_db().execute(
                    "SELECT a.*,u.name applicant_name,u.contact applicant_contact FROM applications a "
                    "JOIN users u ON u.id=a.applicant_id WHERE a.resource_id=? ORDER BY a.applied_at DESC",
                    (resource_id,),
                ).fetchall()
        return render_template(
            "resource_detail.html", resource=resource, application=application,
            owner_applications=owner_applications,
        )

    @app.route("/resources/<int:resource_id>/edit", methods=("GET", "POST"))
    @login_required
    def resource_edit(resource_id):
        db = get_db()
        resource = db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if resource is None:
            abort(404)
        if resource["owner_id"] != g.user["id"]:
            abort(403)
        pending = db.execute(
            "SELECT 1 FROM applications WHERE resource_id=? AND status='pending'", (resource_id,)
        ).fetchone()
        if resource["status"] != "available" or pending:
            abort(409, "当前资源存在待处理或进行中的流转，不能编辑。")
        if request.method == "GET":
            return render_template(
                "resource_form.html", categories=RESOURCE_CATEGORIES,
                conditions=CONDITION_LEVELS, resource=resource, editing=True,
            )
        data, error = _resource_form_data(request.form)
        image_name = resource["image_name"]
        replacement = request.files.get("image")
        if not error and replacement and replacement.filename:
            try:
                image_name = save_image(replacement)
            except ValueError as exc:
                error = str(exc)
        if error:
            return render_template(
                "resource_form.html", categories=RESOURCE_CATEGORIES,
                conditions=CONDITION_LEVELS, resource=request.form, editing=True, error=error,
            ), 400
        db.execute(
            "UPDATE resources SET name=?,category=?,condition_level=?,transfer_mode=?,description=?,keywords=?,image_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data["name"], data["category"], data["condition_level"], data["transfer_mode"],
             data["description"], data["keywords"], image_name, resource_id),
        )
        db.commit()
        if image_name != resource["image_name"]:
            _remove_image(resource["image_name"])
        flash("资源已更新。", "success")
        return redirect(url_for("resource_detail", resource_id=resource_id))

    @app.post("/resources/<int:resource_id>/withdraw")
    @login_required
    def resource_withdraw(resource_id):
        db = get_db()
        resource = db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if resource is None:
            abort(404)
        is_admin = g.user["role"] == "admin"
        if resource["owner_id"] != g.user["id"] and not is_admin:
            abort(403)
        if resource["status"] in {"in_use", "in_service"} and not is_admin:
            abort(409, "进行中的资源不能下架。")
        has_history = db.execute(
            "SELECT 1 FROM applications WHERE resource_id=?", (resource_id,)
        ).fetchone()
        if has_history or is_admin:
            affected = db.execute(
                "SELECT applicant_id FROM applications WHERE resource_id=? AND status IN ('pending','borrowed','return_pending','in_service','completion_pending')",
                (resource_id,),
            ).fetchall()
            db.execute("UPDATE resources SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE id=?", (resource_id,))
            db.execute(
                "UPDATE applications SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE resource_id=? AND status IN ('pending','borrowed','return_pending','in_service','completion_pending')",
                (resource_id,),
            )
            for applicant in affected:
                _notify(db, applicant["applicant_id"], f"“{resource['name']}”已下架，相关流转已结束", url_for("applications"))
        else:
            db.execute("DELETE FROM resources WHERE id=?", (resource_id,))
        db.commit()
        if not has_history and not is_admin:
            _remove_image(resource["image_name"])
        flash("资源已下架。", "success")
        return redirect(url_for("resources"))

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @app.post("/resources/<int:resource_id>/apply")
    @login_required
    def application_create(resource_id):
        db = get_db()
        resource = db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
        if resource is None or resource["status"] == "withdrawn":
            abort(404)
        if resource["owner_id"] == g.user["id"]:
            abort(400, "不能申请自己发布的资源。")
        if resource["status"] != "available":
            abort(409, "该资源当前不可申请。")
        note = request.form.get("note", "").strip()
        if len(note) > 300:
            abort(400, "申请备注不能超过 300 字。")
        if resource["transfer_mode"] in {"exchange", "skill_exchange"} and not note:
            abort(400, "交换申请必须说明可交换的物品或技能。")
        expected_return_date = request.form.get("expected_return_date", "").strip() or None
        if resource["transfer_mode"] == "borrow":
            try:
                expected = date.fromisoformat(expected_return_date or "")
            except ValueError:
                abort(400, "请选择有效的预计归还日期。")
            if expected <= date.today():
                abort(400, "预计归还日期必须晚于今天。")
        try:
            db.execute(
                "INSERT INTO applications(resource_id,applicant_id,note,expected_return_date) VALUES(?,?,?,?)",
                (resource_id, g.user["id"], note, expected_return_date),
            )
            _notify(db, resource["owner_id"], f"{g.user['name']} 申请了“{resource['name']}”", url_for("resource_detail", resource_id=resource_id))
            db.commit()
        except sqlite3.IntegrityError as exc:
            if "UNIQUE constraint" in str(exc):
                abort(409, "你已有一条待审批申请。")
            raise
        flash("申请已提交。", "success")
        return redirect(url_for("resource_detail", resource_id=resource_id))

    @app.route("/applications")
    @login_required
    def applications():
        db = get_db()
        sent = db.execute(
            "SELECT a.*,r.name resource_name,r.transfer_mode,r.owner_id,u.name owner_name,u.contact owner_contact "
            "FROM applications a JOIN resources r ON r.id=a.resource_id JOIN users u ON u.id=r.owner_id "
            "WHERE a.applicant_id=? ORDER BY a.applied_at DESC", (g.user["id"],)
        ).fetchall()
        received_sql = (
            "SELECT a.*,r.name resource_name,r.transfer_mode,u.name applicant_name,u.contact applicant_contact "
            "FROM applications a JOIN resources r ON r.id=a.resource_id JOIN users u ON u.id=a.applicant_id "
        )
        if g.user["role"] == "admin":
            received = db.execute(received_sql + "ORDER BY a.applied_at DESC").fetchall()
        else:
            received = db.execute(
                received_sql + "WHERE r.owner_id=? ORDER BY a.applied_at DESC", (g.user["id"],)
            ).fetchall()
        return render_template("applications.html", sent=sent, received=received)

    @app.post("/applications/<int:application_id>/approve")
    @login_required
    def application_approve(application_id):
        db = get_db()
        db.execute("BEGIN IMMEDIATE")
        item = _application(db, application_id)
        if item["owner_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "pending" or item["resource_status"] != "available":
            abort(409, "该申请当前不能审批。")
        mode = item["transfer_mode"]
        if mode == "borrow":
            application_status, resource_status = "borrowed", "in_use"
        elif mode in SKILL_MODES:
            application_status, resource_status = "in_service", "in_service"
        else:
            application_status, resource_status = "completed", "completed"
        updated = db.execute(
            "UPDATE applications SET status=?,approved_at=CURRENT_TIMESTAMP,completed_at=CASE WHEN ?='completed' THEN CURRENT_TIMESTAMP ELSE completed_at END,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
            (application_status, application_status, application_id),
        )
        resource_updated = db.execute(
            "UPDATE resources SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='available'",
            (resource_status, item["resource_id"]),
        )
        if updated.rowcount != 1 or resource_updated.rowcount != 1:
            db.rollback()
            abort(409, "申请状态已变化，请刷新后重试。")
        if mode not in SKILL_MODES:
            other_applicants = db.execute(
                "SELECT applicant_id FROM applications WHERE resource_id=? AND status='pending' AND id!=?",
                (item["resource_id"], application_id),
            ).fetchall()
            db.execute(
                "UPDATE applications SET status='rejected',rejection_reason='其他申请已获批准',updated_at=CURRENT_TIMESTAMP WHERE resource_id=? AND status='pending' AND id!=?",
                (item["resource_id"], application_id),
            )
            for other in other_applicants:
                _notify(
                    db, other["applicant_id"], f"“{item['resource_name']}”的其他申请已获批准，你的申请已结束",
                    url_for("applications"),
                )
        _notify(db, item["applicant_id"], f"你对“{item['resource_name']}”的申请已获批准", url_for("applications"))
        db.commit()
        flash("申请已批准。", "success")
        return redirect(url_for("resource_detail", resource_id=item["resource_id"]))

    @app.post("/applications/<int:application_id>/reject")
    @login_required
    def application_reject(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["owner_id"] != g.user["id"]:
            abort(403)
        reason = request.form.get("reason", "").strip()
        if item["status"] != "pending" or not reason or len(reason) > 300:
            abort(400, "拒绝原因必填且不能超过 300 字。")
        db.execute(
            "UPDATE applications SET status='rejected',rejection_reason=?,action_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (reason, application_id),
        )
        _notify(db, item["applicant_id"], f"你对“{item['resource_name']}”的申请未获批准：{reason}", url_for("applications"))
        db.commit()
        return redirect(url_for("resource_detail", resource_id=item["resource_id"]))

    @app.post("/applications/<int:application_id>/withdraw")
    @login_required
    def application_withdraw(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["applicant_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "pending":
            abort(409)
        db.execute("UPDATE applications SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE id=?", (application_id,))
        db.commit()
        return redirect(url_for("applications"))

    @app.post("/applications/<int:application_id>/request-return")
    @login_required
    def application_request_return(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["applicant_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "borrowed":
            abort(409)
        db.execute("UPDATE applications SET status='return_pending',action_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (application_id,))
        _notify(db, item["owner_id"], f"“{item['resource_name']}”已发起归还，请确认", url_for("applications"))
        db.commit()
        return redirect(url_for("applications"))

    @app.post("/applications/<int:application_id>/confirm-return")
    @login_required
    def application_confirm_return(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["owner_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "return_pending":
            abort(409)
        db.execute("UPDATE applications SET status='returned',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (application_id,))
        db.execute("UPDATE resources SET status='available',updated_at=CURRENT_TIMESTAMP WHERE id=?", (item["resource_id"],))
        _notify(db, item["applicant_id"], f"“{item['resource_name']}”归还已确认", url_for("applications"))
        db.commit()
        return redirect(url_for("applications"))

    @app.post("/applications/<int:application_id>/request-completion")
    @login_required
    def application_request_completion(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["owner_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "in_service":
            abort(409)
        db.execute("UPDATE applications SET status='completion_pending',action_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (application_id,))
        _notify(db, item["applicant_id"], f"“{item['resource_name']}”服务已提交完成，请确认", url_for("applications"))
        db.commit()
        return redirect(url_for("applications"))

    @app.post("/applications/<int:application_id>/confirm-completion")
    @login_required
    def application_confirm_completion(application_id):
        db = get_db()
        item = _application(db, application_id)
        if item["applicant_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "completion_pending":
            abort(409)
        db.execute("UPDATE applications SET status='completed',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (application_id,))
        db.execute("UPDATE resources SET status='available',updated_at=CURRENT_TIMESTAMP WHERE id=?", (item["resource_id"],))
        _notify(db, item["owner_id"], f"“{item['resource_name']}”服务完成已确认", url_for("applications"))
        db.commit()
        return redirect(url_for("applications"))

    @app.route("/lost-found")
    def lost_found():
        page = max(request.args.get("page", 1, type=int), 1)
        filters = {key: request.args.get(key, "").strip() for key in ("q", "kind", "status")}
        where = ["lf.status != 'withdrawn'"]
        params = []
        if filters["q"]:
            term = f"%{filters['q']}%"
            where.append("(lf.title LIKE ? OR lf.description LIKE ? OR lf.location LIKE ? OR lf.keywords LIKE ?)")
            params.extend((term, term, term, term))
        if filters["kind"] in {"lost", "found"}:
            where.append("lf.kind=?")
            params.append(filters["kind"])
        if filters["status"] in {"open", "resolved"}:
            where.append("lf.status=?")
            params.append(filters["status"])
        db = get_db()
        items = db.execute(
            "SELECT lf.*,u.name owner_name FROM lost_found lf JOIN users u ON u.id=lf.user_id WHERE "
            + " AND ".join(where) + " ORDER BY lf.created_at DESC,lf.id DESC LIMIT 12 OFFSET ?",
            (*params, (page - 1) * 12),
        ).fetchall()
        total = db.execute(
            "SELECT COUNT(*) FROM lost_found lf WHERE " + " AND ".join(where), params
        ).fetchone()[0]
        return render_template(
            "lost_found.html", items=items, filters=filters, page=page, has_next=page*12 < total
        )

    @app.route("/lost-found/new/<kind>", methods=("GET", "POST"))
    @login_required
    def lost_found_new(kind):
        if kind not in {"lost", "found"}:
            abort(404)
        if request.method == "GET":
            return render_template("lost_found_form.html", kind=kind, item=None)
        data, error = _lost_found_form_data(request.form)
        image_name = None
        if not error:
            try:
                image_name = save_image(request.files.get("image"))
            except ValueError as exc:
                error = str(exc)
        if error:
            return render_template("lost_found_form.html", kind=kind, item=request.form, error=error), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO lost_found(user_id,kind,title,description,occurred_on,location,keywords,image_name) VALUES(?,?,?,?,?,?,?,?)",
            (g.user["id"], kind, data["title"], data["description"], data["occurred_on"],
             data["location"], data["keywords"], image_name),
        )
        create_matches(cursor.lastrowid)
        db.commit()
        flash("失物信息发布成功，系统已完成自动匹配。", "success")
        return redirect(url_for("lost_found_detail", item_id=cursor.lastrowid))

    @app.route("/lost-found/<int:item_id>")
    def lost_found_detail(item_id):
        item = get_db().execute(
            "SELECT lf.*,u.name owner_name,u.grade,u.class_name,u.contact FROM lost_found lf "
            "JOIN users u ON u.id=lf.user_id WHERE lf.id=? AND lf.status!='withdrawn'", (item_id,)
        ).fetchone()
        if item is None:
            abort(404)
        related = get_db().execute(
            "SELECT lf.*,m.score FROM matches m JOIN lost_found lf ON lf.id=CASE WHEN m.lost_id=? THEN m.found_id ELSE m.lost_id END "
            "WHERE (m.lost_id=? OR m.found_id=?) AND lf.status!='withdrawn' ORDER BY m.score DESC",
            (item_id, item_id, item_id),
        ).fetchall()
        return render_template("lost_found_detail.html", item=item, related=related)

    @app.route("/lost-found/<int:item_id>/edit", methods=("GET", "POST"))
    @login_required
    def lost_found_edit(item_id):
        db = get_db()
        item = db.execute("SELECT * FROM lost_found WHERE id=?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        if item["user_id"] != g.user["id"]:
            abort(403)
        if item["status"] != "open":
            abort(409, "已解决信息恢复后才能编辑。")
        if request.method == "GET":
            return render_template("lost_found_form.html", kind=item["kind"], item=item, editing=True)
        data, error = _lost_found_form_data(request.form)
        image_name = item["image_name"]
        replacement = request.files.get("image")
        if not error and replacement and replacement.filename:
            try:
                image_name = save_image(replacement)
            except ValueError as exc:
                error = str(exc)
        if error:
            return render_template("lost_found_form.html", kind=item["kind"], item=request.form, editing=True, error=error), 400
        db.execute(
            "UPDATE lost_found SET title=?,description=?,occurred_on=?,location=?,keywords=?,image_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data["title"], data["description"], data["occurred_on"], data["location"], data["keywords"], image_name, item_id),
        )
        db.execute("DELETE FROM matches WHERE lost_id=? OR found_id=?", (item_id, item_id))
        create_matches(item_id)
        db.commit()
        if image_name != item["image_name"]:
            _remove_image(item["image_name"])
        flash("信息已更新并重新匹配。", "success")
        return redirect(url_for("lost_found_detail", item_id=item_id))

    @app.post("/lost-found/<int:item_id>/<action>")
    @login_required
    def lost_found_status(item_id, action):
        if action not in {"resolve", "restore", "withdraw"}:
            abort(404)
        db = get_db()
        item = db.execute("SELECT * FROM lost_found WHERE id=?", (item_id,)).fetchone()
        if item is None:
            abort(404)
        if item["user_id"] != g.user["id"] and g.user["role"] != "admin":
            abort(403)
        allowed = {
            "resolve": item["status"] == "open",
            "restore": item["status"] == "resolved",
            "withdraw": item["status"] in {"open", "resolved"},
        }
        if not allowed[action]:
            abort(409, "当前状态不能执行此操作。")
        new_status = {"resolve": "resolved", "restore": "open", "withdraw": "withdrawn"}[action]
        db.execute("UPDATE lost_found SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, item_id))
        if new_status == "open":
            create_matches(item_id)
        db.commit()
        flash("状态已更新。", "success")
        return redirect(url_for("lost_found_detail", item_id=item_id) if new_status != "withdrawn" else url_for("lost_found"))

    @app.route("/notifications")
    @login_required
    def notifications():
        items = get_db().execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC,id DESC",
            (g.user["id"],),
        ).fetchall()
        return render_template("notifications.html", notifications=items)

    @app.post("/notifications/<int:notification_id>/read")
    @login_required
    def notification_read(notification_id):
        db = get_db()
        item = db.execute(
            "SELECT * FROM notifications WHERE id=? AND user_id=?", (notification_id, g.user["id"])
        ).fetchone()
        if item is None:
            abort(404)
        db.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        db.commit()
        return redirect(_safe_next(item["target_url"]) or url_for("notifications"))

    @app.post("/notifications/read-all")
    @login_required
    def notifications_read_all():
        db = get_db()
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (g.user["id"],))
        db.commit()
        return redirect(url_for("notifications"))

    @app.route("/admin")
    @admin_required
    def admin():
        db = get_db()
        return render_template(
            "admin.html",
            stats=_admin_stats(db),
            users=db.execute("SELECT * FROM users ORDER BY created_at DESC,id DESC").fetchall(),
            resources=db.execute(
                "SELECT r.*,u.name owner_name FROM resources r JOIN users u ON u.id=r.owner_id "
                "WHERE r.status!='withdrawn' ORDER BY r.created_at DESC"
            ).fetchall(),
            lost_items=db.execute(
                "SELECT lf.*,u.name owner_name FROM lost_found lf JOIN users u ON u.id=lf.user_id "
                "WHERE lf.status!='withdrawn' ORDER BY lf.created_at DESC"
            ).fetchall(),
        )

    @app.route("/api/admin/stats")
    @admin_required
    def admin_stats_api():
        return jsonify(_admin_stats(get_db()))

    @app.post("/admin/users/<int:user_id>/role")
    @admin_required
    def admin_user_role(user_id):
        role = request.form.get("role")
        if role not in {"student", "admin"}:
            abort(400, "角色无效。")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None:
            abort(404)
        if user["role"] == "admin" and role != "admin" and user["is_active"] and _active_admins(db) == 1:
            abort(409, "必须保留至少一名有效管理员。")
        db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        db.commit()
        flash("用户角色已更新。", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/users/<int:user_id>/active")
    @admin_required
    def admin_user_active(user_id):
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None:
            abort(404)
        if user["role"] == "admin" and user["is_active"] and _active_admins(db) == 1:
            abort(409, "必须保留至少一名有效管理员。")
        db.execute("UPDATE users SET is_active=? WHERE id=?", (0 if user["is_active"] else 1, user_id))
        db.commit()
        flash("账号状态已更新。", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/users/<int:user_id>/reset-password")
    @admin_required
    def admin_user_reset_password(user_id):
        password = request.form.get("password", "")
        if len(password) < 8:
            abort(400, "临时密码至少 8 位。")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
            abort(404)
        db.execute(
            "UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?",
            (generate_password_hash(password), user_id),
        )
        db.commit()
        flash("临时密码已设置。", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/users/<int:user_id>/edit")
    @admin_required
    def admin_user_edit(user_id):
        values = {key: request.form.get(key, "").strip() for key in (
            "username", "name", "student_no", "grade", "class_name", "contact"
        )}
        if not all(values[key] for key in ("username", "name", "student_no", "grade", "class_name")) or len(values["contact"]) > 100:
            abort(400, "用户资料不完整或过长。")
        db = get_db()
        try:
            cursor = db.execute(
                "UPDATE users SET username=?,name=?,student_no=?,grade=?,class_name=?,contact=? WHERE id=?",
                (values["username"], values["name"], values["student_no"], values["grade"], values["class_name"], values["contact"], user_id),
            )
            if cursor.rowcount == 0:
                abort(404)
            db.commit()
        except sqlite3.IntegrityError as exc:
            if "users.student_no" in str(exc) or "users.username" in str(exc):
                abort(409, "用户名或学号已存在。")
            raise
        flash("用户资料已更正。", "success")
        return redirect(url_for("admin"))

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    def friendly_error(error):
        return render_template("error.html", error=error), error.code

    @app.route("/badges")
    def badges():
        db = get_db()
        all_badges = [dict(b) for b in db.execute("SELECT * FROM badges ORDER BY tier,id").fetchall()]
        user_badge_map = {}
        for ub in db.execute("SELECT ub.*,u.name FROM user_badges ub JOIN users u ON u.id=ub.user_id ORDER BY ub.granted_at DESC").fetchall():
            row = dict(ub)
            user_badge_map.setdefault(row["badge_id"], []).append(row)
        return render_template("badges.html", badges=all_badges, user_badge_map=user_badge_map, BADGE_TIER_COLORS=BADGE_TIER_COLORS)

    return app


def _safe_next(value):
    if not value:
        return None
    parts = urlsplit(value)
    return value if not parts.scheme and not parts.netloc and value.startswith("/") else None


def _resource_form_data(form):
    data = {key: form.get(key, "").strip() for key in (
        "name", "category", "condition_level", "transfer_mode", "description", "keywords"
    )}
    if not data["name"] or not data["description"]:
        return data, "请填写资源名称和描述。"
    if len(data["name"]) > 50 or len(data["description"]) > 1000:
        return data, "资源名称或描述超过长度限制。"
    if data["category"] not in RESOURCE_CATEGORIES:
        return data, "资源类别无效。"
    if data["category"] == "技能服务":
        data["condition_level"] = "不适用"
        if data["transfer_mode"] not in SKILL_MODES:
            return data, "技能服务的流转方式无效。"
    elif data["condition_level"] not in CONDITION_LEVELS or data["transfer_mode"] not in PHYSICAL_MODES:
        return data, "资源的新旧程度或流转方式无效。"
    return data, None


def save_image(file):
    if file is None or not file.filename:
        return None
    extension = Path(file.filename).suffix.lower()
    signatures = {
        ".png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        ".webp": lambda value: value.startswith(b"RIFF") and value[8:12] == b"WEBP",
    }
    header = file.stream.read(16)
    file.stream.seek(0)
    if extension not in signatures or not signatures[extension](header):
        raise ValueError("图片格式无效，仅支持 JPG、PNG、WebP。")
    stored_extension = ".jpg" if extension == ".jpeg" else extension
    filename = f"{uuid.uuid4().hex}{stored_extension}"
    file.save(Path(current_app.config["UPLOAD_FOLDER"], filename))
    return filename


def _remove_image(filename):
    if filename:
        Path(current_app.config["UPLOAD_FOLDER"], filename).unlink(missing_ok=True)


def _application(db, application_id):
    item = db.execute(
        "SELECT a.*,r.owner_id,r.name resource_name,r.transfer_mode,r.status resource_status "
        "FROM applications a JOIN resources r ON r.id=a.resource_id WHERE a.id=?",
        (application_id,),
    ).fetchone()
    if item is None:
        abort(404)
    return item


def _notify(db, user_id, message, target_url, dedupe_key=None):
    db.execute(
        "INSERT OR IGNORE INTO notifications(user_id,message,target_url,dedupe_key) VALUES(?,?,?,?)",
        (user_id, message, target_url, dedupe_key),
    )


def _check_overdue(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT a.id,r.name FROM applications a JOIN resources r ON r.id=a.resource_id "
        "WHERE a.applicant_id=? AND a.status='borrowed' AND a.expected_return_date < ?",
        (user_id, date.today().isoformat()),
    ).fetchall()
    for row in rows:
        _notify(
            db, user_id, f"“{row['name']}”已超过预计归还日期", url_for("applications"),
            f"overdue:{row['id']}",
        )
    if rows:
        db.commit()

def _check_and_award_badges(db, user_id):
    """Auto-award badges based on user activity."""
    awarded = []
    def grant(badge_id):
        cur = db.execute("INSERT OR IGNORE INTO user_badges(user_id,badge_id) VALUES(?,?)", (user_id, badge_id))
        if cur.rowcount:
            awarded.append(BADGE_BY_ID[badge_id]["name"])
    # Bronze: first resource
    count = db.execute("SELECT COUNT(*) FROM resources WHERE owner_id=? AND status!='withdrawn'", (user_id,)).fetchone()[0]
    if count >= 1: grant(1)
    # Bronze: first completed application as applicant
    count = db.execute("SELECT COUNT(*) FROM applications WHERE applicant_id=? AND status IN ('returned','completed')", (user_id,)).fetchone()[0]
    if count >= 1: grant(2)
    # Bronze: first lost & found resolved
    count = db.execute("SELECT COUNT(*) FROM lost_found WHERE user_id=? AND status='resolved'", (user_id,)).fetchone()[0]
    if count >= 1: grant(3)
    # Silver: 5+ completed resources as owner
    count = db.execute("SELECT COUNT(*) FROM resources WHERE owner_id=? AND status IN ('completed','in_use','in_service')", (user_id,)).fetchone()[0]
    if count >= 5: grant(4)
    # Silver: 3+ lost & found resolved
    lf_count = db.execute("SELECT COUNT(*) FROM lost_found WHERE user_id=? AND status='resolved'", (user_id,)).fetchone()[0]
    if lf_count >= 3: grant(5)
    # Gold: 10+ completed applications
    if count >= 10: grant(6)
    # Gold: 100% return rate with 5+ borrows as owner
    total = db.execute("SELECT COUNT(*) FROM applications WHERE resource_id IN (SELECT id FROM resources WHERE owner_id=?) AND status!='withdrawn'", (user_id,)).fetchone()[0]
    on_time = db.execute("SELECT COUNT(*) FROM applications WHERE resource_id IN (SELECT id FROM resources WHERE owner_id=?) AND status='returned' AND expected_return_date >= date(completed_at,'+0 days')", (user_id,)).fetchone()[0]
    if total >= 5 and on_time == total: grant(7)
    if awarded:
        db.commit()
    return awarded



def _lost_found_form_data(form):
    data = {key: form.get(key, "").strip() for key in (
        "title", "description", "occurred_on", "location", "keywords"
    )}
    if not all(data.values()):
        return data, "请完整填写名称、描述、日期、地点和关键词。"
    if len(data["title"]) > 50 or len(data["description"]) > 1000:
        return data, "名称或描述超过长度限制。"
    try:
        occurred = date.fromisoformat(data["occurred_on"])
    except ValueError:
        return data, "日期格式无效。"
    if occurred > date.today():
        return data, "发生日期不能晚于今天。"
    if not _keyword_set(data["keywords"]):
        return data, "请至少填写一个有效关键词。"
    return data, None


def _keyword_set(value):
    return {part.strip().lower() for part in re.split(r"[,，、;；\s]+", value or "") if part.strip()}


def match_score(left_title, right_title, left_keywords, right_keywords):
    left = _keyword_set(left_keywords)
    right = _keyword_set(right_keywords)
    keyword_score = len(left & right) / len(left | right) if left | right else 0
    title_score = SequenceMatcher(
        None, re.sub(r"\s+", "", left_title.lower()), re.sub(r"\s+", "", right_title.lower())
    ).ratio()
    return round(keyword_score * 0.65 + title_score * 0.35, 4)


def create_matches(record_id):
    db = get_db()
    item = db.execute("SELECT * FROM lost_found WHERE id=?", (record_id,)).fetchone()
    if item is None or item["status"] != "open":
        return []
    candidates = db.execute(
        "SELECT * FROM lost_found WHERE kind!=? AND status='open' AND id!=? AND user_id!=?",
        (item["kind"], record_id, item["user_id"]),
    ).fetchall()
    created = []
    for other in candidates:
        score = match_score(item["title"], other["title"], item["keywords"], other["keywords"])
        if score < 0.45:
            continue
        lost = item if item["kind"] == "lost" else other
        found = item if item["kind"] == "found" else other
        cursor = db.execute(
            "INSERT OR IGNORE INTO matches(lost_id,found_id,score) VALUES(?,?,?)",
            (lost["id"], found["id"], score),
        )
        if not cursor.rowcount:
            continue
        created.append(cursor.lastrowid)
        for target in (lost, found):
            opposite = found if target["id"] == lost["id"] else lost
            _notify(
                db, target["user_id"], f"发现可能匹配的信息：“{opposite['title']}”",
                url_for("lost_found_detail", item_id=opposite["id"]),
                f"match:{lost['id']}:{found['id']}:{target['user_id']}",
            )
    return created


def _active_admins(db):
    return db.execute(
        "SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1"
    ).fetchone()[0]


def _admin_stats(db):
    scalar_queries = {
        "users": "SELECT COUNT(*) FROM users",
        "resources": "SELECT COUNT(*) FROM resources WHERE status!='withdrawn'",
        "pending": "SELECT COUNT(*) FROM applications WHERE status='pending'",
        "borrowing": "SELECT COUNT(*) FROM applications WHERE status IN ('borrowed','return_pending')",
        "completed": "SELECT COUNT(*) FROM applications WHERE status IN ('returned','completed')",
        "lost": "SELECT COUNT(*) FROM lost_found WHERE kind='lost' AND status!='withdrawn'",
        "found": "SELECT COUNT(*) FROM lost_found WHERE kind='found' AND status!='withdrawn'",
        "matches": "SELECT COUNT(*) FROM matches",
    }
    summary = {key: db.execute(sql).fetchone()[0] for key, sql in scalar_queries.items()}
    categories = [
        {"label": row[0], "value": row[1]}
        for row in db.execute(
            "SELECT category,COUNT(*) FROM resources WHERE status!='withdrawn' GROUP BY category ORDER BY COUNT(*) DESC"
        ).fetchall()
    ]
    modes = [
        {"label": MODE_LABELS.get(row[0], row[0]), "value": row[1]}
        for row in db.execute(
            "SELECT transfer_mode,COUNT(*) FROM resources WHERE status!='withdrawn' GROUP BY transfer_mode ORDER BY COUNT(*) DESC"
        ).fetchall()
    ]
    return {"summary": summary, "categories": categories, "modes": modes}


def _seed_demo():
    db = get_db()
    users = (
        ("admin", "admin123", "系统管理员", "ADMIN001", "教师", "管理组", "admin"),
        ("student01", "student123", "张同学", "2024001", "2024级", "软件1班", "student"),
        ("student02", "student123", "李同学", "2024002", "2024级", "设计2班", "student"),
    )
    for username, password, name, student_no, grade, class_name, role in users:
        db.execute(
            "INSERT OR IGNORE INTO users(username,password_hash,name,student_no,grade,class_name,contact,role) VALUES(?,?,?,?,?,?,?,?)",
            (username, generate_password_hash(password), name, student_no, grade, class_name,
             "13800000000" if username != "admin" else "", role),
        )
    ids = {
        row["username"]: row["id"]
        for row in db.execute("SELECT id,username FROM users WHERE username IN ('admin','student01','student02')")
    }
    demo_resources = (
        (ids["student01"], "高等数学教材（第七版）", "教材书籍", "九成新", "borrow", "课本保存完好，适合大一同学借阅。", "高数,教材"),
        (ids["student02"], "Arduino 入门套件", "实验器材", "七成新", "exchange", "含开发板、面包板和常用传感器。", "Arduino,开发板"),
        (ids["student01"], "Python 编程互助", "技能服务", "不适用", "free_help", "可帮助解决 Python 入门和课程作业中的问题。", "Python,编程"),
    )
    for values in demo_resources:
        if db.execute("SELECT 1 FROM resources WHERE owner_id=? AND name=?", (values[0], values[1])).fetchone() is None:
            db.execute(
                "INSERT INTO resources(owner_id,name,category,condition_level,transfer_mode,description,keywords) VALUES(?,?,?,?,?,?,?)",
                values,
            )
    textbook = db.execute("SELECT id FROM resources WHERE name='高等数学教材（第七版）'").fetchone()[0]
    if db.execute("SELECT 1 FROM applications WHERE resource_id=? AND applicant_id=?", (textbook, ids["student02"])).fetchone() is None:
        db.execute(
            "INSERT INTO applications(resource_id,applicant_id,note,expected_return_date) VALUES(?,?,?,?)",
            (textbook, ids["student02"], "期中复习需要", date.today().replace(day=28).isoformat() if date.today().day < 28 else (date.today().isoformat())),
        )
    lost_values = (
        (ids["student01"], "lost", "蓝色校园卡", "蓝色卡套，背面有贴纸", date.today().isoformat(), "图书馆二楼", "校园卡,蓝色"),
        (ids["student02"], "found", "捡到蓝色校园卡", "在阅览区捡到一张蓝色卡套校园卡", date.today().isoformat(), "图书馆二楼", "蓝色,校园卡"),
    )
    lost_ids = []
    for values in lost_values:
        row = db.execute("SELECT id FROM lost_found WHERE user_id=? AND title=?", (values[0], values[2])).fetchone()
        if row is None:
            row_id = db.execute(
                "INSERT INTO lost_found(user_id,kind,title,description,occurred_on,location,keywords) VALUES(?,?,?,?,?,?,?)", values
            ).lastrowid
        else:
            row_id = row[0]
        lost_ids.append(row_id)
    lost_id, found_id = lost_ids
    db.execute("INSERT OR IGNORE INTO matches(lost_id,found_id,score) VALUES(?,?,?)", (lost_id, found_id, 0.86))
    for user_id, target_id in ((ids["student01"], found_id), (ids["student02"], lost_id)):
        _notify(
            db, user_id, "演示：发现一条可能匹配的校园卡信息",
            f"/lost-found/{target_id}", f"demo-match:{user_id}",
        )
    db.commit()


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.get("user") is None:
            return redirect(url_for("login", next=request.path))
        return view(**kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.get("user") is None:
            return redirect(url_for("login", next=request.path))
        if g.user["role"] != "admin":
            abort(403)
        return view(**kwargs)
    return wrapped


if __name__ == "__main__":
    create_app().run(debug=True)
