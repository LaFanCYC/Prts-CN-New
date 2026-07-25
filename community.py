import re
import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db


SECTIONS = {
    "resource": "资源交流",
    "lost_found": "失物招领",
    "study": "学习问答",
    "campus": "校园生活",
    "feedback": "建议反馈",
}


def validate_post_form(form):
    title = form.get("title", "").strip()
    section = form.get("section", "").strip()
    body = form.get("body", "").strip()
    tags = []
    for value in re.split(r"[,，]", form.get("tags", "")):
        value = value.strip()
        if value:
            normalized = value.lower() if value.isascii() else value
            if normalized not in tags:
                tags.append(normalized)
    if not title or len(title) > 50:
        return None, "标题不能为空且不能超过 50 字。"
    if section not in SECTIONS:
        return None, "请选择有效分区。"
    if not body or len(body) > 2000:
        return None, "正文不能为空且不能超过 2000 字。"
    if not 1 <= len(tags) <= 5 or any(len(tag) > 30 for tag in tags):
        return None, "请填写 1–5 个不超过 30 字的标签。"
    return {"title": title, "section": section, "body": body, "tags": tags}, None


def target_exists(db, target_type, target_id):
    queries = {
        "post": "SELECT 1 FROM posts WHERE id=? AND status='published'",
        "resource": "SELECT 1 FROM resources WHERE id=? AND status!='withdrawn'",
        "lost_found": "SELECT 1 FROM lost_found WHERE id=? AND status!='withdrawn'",
    }
    query = queries.get(target_type)
    return bool(query and db.execute(query, (target_id,)).fetchone())


def _replace_tags(db, post_id, names):
    db.execute("DELETE FROM post_tags WHERE post_id=?", (post_id,))
    for name in names:
        db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        tag_id = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[0]
        db.execute(
            "INSERT INTO post_tags(post_id,tag_id) VALUES(?,?)", (post_id, tag_id)
        )


def _post(db, post_id, include_hidden=False):
    status = "" if include_hidden else " AND p.status='published'"
    return db.execute(
        "SELECT p.*,u.name author_name,u.username FROM posts p "
        "JOIN users u ON u.id=p.author_id WHERE p.id=?" + status,
        (post_id,),
    ).fetchone()


def create_community_blueprint(login_required, save_image, notify):
    bp = Blueprint("community", __name__, url_prefix="/community")

    @bp.get("")
    def list_posts():
        section = request.args.get("section", "").strip()
        params = []
        where = ["p.status='published'"]
        if section in SECTIONS:
            where.append("p.section=?")
            params.append(section)
        posts = get_db().execute(
            "SELECT p.*,u.name author_name FROM posts p JOIN users u ON u.id=p.author_id "
            "WHERE " + " AND ".join(where) + " ORDER BY p.created_at DESC,p.id DESC LIMIT 24",
            params,
        ).fetchall()
        return render_template(
            "community_list.html", posts=posts, sections=SECTIONS, selected=section
        )

    @bp.route("/new", methods=("GET", "POST"))
    @login_required
    def new_post():
        if request.method == "GET":
            return render_template("community_form.html", sections=SECTIONS, post=None)
        data, error = validate_post_form(request.form)
        image_name = None
        image = request.files.get("image")
        if not error and image and image.filename:
            try:
                image_name = save_image(image)
            except ValueError as exc:
                error = str(exc)
        if error:
            return render_template(
                "community_form.html", sections=SECTIONS, post=request.form, error=error
            ), 400
        status = "pending" if image_name else "published"
        db = get_db()
        cursor = db.execute(
            "INSERT INTO posts(author_id,section,title,body,image_name,status) VALUES(?,?,?,?,?,?)",
            (g.user["id"], data["section"], data["title"], data["body"], image_name, status),
        )
        _replace_tags(db, cursor.lastrowid, data["tags"])
        db.commit()
        flash("帖子已提交审核。" if status == "pending" else "帖子发布成功。", "success")
        return redirect(url_for("community.post_detail", post_id=cursor.lastrowid))

    @bp.get("/<int:post_id>")
    def post_detail(post_id):
        db = get_db()
        post = _post(db, post_id, bool(g.user and g.user["role"] == "admin"))
        if post is None or (post["status"] != "published" and post["author_id"] != g.user["id"]):
            abort(404)
        tags = db.execute(
            "SELECT t.* FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=? ORDER BY t.name",
            (post_id,),
        ).fetchall()
        reposts = db.execute(
            "SELECT r.*,u.name author_name FROM reposts r JOIN users u ON u.id=r.author_id "
            "WHERE r.post_id=? AND r.status='published' ORDER BY r.created_at DESC",
            (post_id,),
        ).fetchall()
        return render_template("community_detail.html", post=post, tags=tags, reposts=reposts)

    @bp.route("/<int:post_id>/edit", methods=("GET", "POST"))
    @login_required
    def edit_post(post_id):
        db = get_db()
        post = _post(db, post_id, True)
        if post is None:
            abort(404)
        if post["author_id"] != g.user["id"]:
            abort(403)
        if request.method == "GET":
            tags = ",".join(
                row[0]
                for row in db.execute(
                    "SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=?",
                    (post_id,),
                )
            )
            return render_template(
                "community_form.html", sections=SECTIONS, post=post, tags=tags, editing=True
            )
        data, error = validate_post_form(request.form)
        if error:
            return render_template(
                "community_form.html", sections=SECTIONS, post=request.form, error=error, editing=True
            ), 400
        db.execute(
            "UPDATE posts SET section=?,title=?,body=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (data["section"], data["title"], data["body"], post_id),
        )
        _replace_tags(db, post_id, data["tags"])
        db.commit()
        return redirect(url_for("community.post_detail", post_id=post_id))

    @bp.post("/<int:post_id>/withdraw")
    @login_required
    def withdraw_post(post_id):
        db = get_db()
        post = _post(db, post_id, True)
        if post is None:
            abort(404)
        if post["author_id"] != g.user["id"] and g.user["role"] != "admin":
            abort(403)
        db.execute(
            "UPDATE posts SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (post_id,),
        )
        db.commit()
        return redirect(url_for("community.list_posts"))

    @bp.post("/users/<int:user_id>/follow")
    @login_required
    def follow_user(user_id):
        if user_id == g.user["id"]:
            abort(400, "不能关注自己。")
        db = get_db()
        if db.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone() is None:
            abort(404)
        existing = db.execute(
            "SELECT 1 FROM user_follows WHERE follower_id=? AND followed_id=?",
            (g.user["id"], user_id),
        ).fetchone()
        if existing:
            db.execute(
                "DELETE FROM user_follows WHERE follower_id=? AND followed_id=?",
                (g.user["id"], user_id),
            )
        else:
            db.execute(
                "INSERT INTO user_follows(follower_id,followed_id) VALUES(?,?)",
                (g.user["id"], user_id),
            )
        db.commit()
        return redirect(request.referrer or url_for("community.list_posts"))

    @bp.post("/tags/<int:tag_id>/follow")
    @login_required
    def follow_tag(tag_id):
        db = get_db()
        if db.execute("SELECT 1 FROM tags WHERE id=?", (tag_id,)).fetchone() is None:
            abort(404)
        existing = db.execute(
            "SELECT 1 FROM tag_follows WHERE user_id=? AND tag_id=?",
            (g.user["id"], tag_id),
        ).fetchone()
        if existing:
            db.execute("DELETE FROM tag_follows WHERE user_id=? AND tag_id=?", (g.user["id"], tag_id))
        else:
            db.execute("INSERT INTO tag_follows(user_id,tag_id) VALUES(?,?)", (g.user["id"], tag_id))
        db.commit()
        return redirect(request.referrer or url_for("community.list_posts"))

    @bp.get("/following")
    @login_required
    def following():
        posts = get_db().execute(
            "SELECT DISTINCT p.*,u.name author_name FROM posts p JOIN users u ON u.id=p.author_id "
            "LEFT JOIN post_tags pt ON pt.post_id=p.id "
            "WHERE p.status='published' AND (p.author_id IN "
            "(SELECT followed_id FROM user_follows WHERE follower_id=?) OR pt.tag_id IN "
            "(SELECT tag_id FROM tag_follows WHERE user_id=?)) "
            "ORDER BY p.created_at DESC,p.id DESC LIMIT 24",
            (g.user["id"], g.user["id"]),
        ).fetchall()
        return render_template(
            "community_following.html", posts=posts, sections=SECTIONS
        )

    @bp.post("/<int:post_id>/repost")
    @login_required
    def repost(post_id):
        db = get_db()
        post = _post(db, post_id)
        if post is None:
            abort(404)
        comment = request.form.get("comment", "").strip()
        if len(comment) > 300:
            abort(400, "转发评论不能超过 300 字。")
        db.execute(
            "INSERT INTO reposts(author_id,post_id,comment) VALUES(?,?,?) "
            "ON CONFLICT(author_id,post_id) DO UPDATE SET comment=excluded.comment,status='published'",
            (g.user["id"], post_id, comment),
        )
        if post["author_id"] != g.user["id"]:
            notify(db, post["author_id"], f"{g.user['name']} 转发了你的帖子", url_for("community.post_detail", post_id=post_id))
        db.commit()
        return redirect(url_for("community.post_detail", post_id=post_id))

    return bp
