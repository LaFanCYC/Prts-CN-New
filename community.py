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


def comments_for_target(db, target_type, target_id, order="new"):
    secondary = "reply_count DESC,c.created_at DESC" if order == "hot" else "c.created_at DESC"
    return db.execute(
        "SELECT c.*,u.name author_name,u.username,"
        "(SELECT COUNT(*) FROM comments r WHERE r.parent_id=c.id AND r.status='published') reply_count "
        "FROM comments c JOIN users u ON u.id=c.author_id "
        "WHERE c.target_type=? AND c.target_id=? AND c.status='published' "
        "ORDER BY CASE WHEN c.parent_id IS NULL THEN c.id ELSE c.parent_id END DESC,"
        f"c.parent_id IS NOT NULL,{secondary}",
        (target_type, target_id),
    ).fetchall()


def _target(db, target_type, target_id):
    queries = {
        "post": "SELECT author_id owner_id,title FROM posts WHERE id=? AND status='published'",
        "resource": "SELECT owner_id,name title FROM resources WHERE id=? AND status!='withdrawn'",
        "lost_found": "SELECT user_id owner_id,title FROM lost_found WHERE id=? AND status!='withdrawn'",
    }
    query = queries.get(target_type)
    return db.execute(query, (target_id,)).fetchone() if query else None


def _target_url(target_type, target_id):
    endpoints = {
        "post": ("community.post_detail", "post_id"),
        "resource": ("resource_detail", "resource_id"),
        "lost_found": ("lost_found_detail", "item_id"),
    }
    endpoint, key = endpoints[target_type]
    return url_for(endpoint, **{key: target_id})


def _mentioned_user_ids(db, body):
    usernames = set(re.findall(r"@([A-Za-z0-9_]{1,30})", body))
    if not usernames:
        return set()
    placeholders = ",".join("?" for _ in usernames)
    return {
        row[0]
        for row in db.execute(
            f"SELECT id FROM users WHERE username IN ({placeholders})", tuple(usernames)
        ).fetchall()
    }


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
    bp = Blueprint("community", __name__)

    @bp.get("/community")
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

    @bp.route("/community/new", methods=("GET", "POST"))
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

    @bp.get("/community/<int:post_id>")
    def post_detail(post_id):
        db = get_db()
        post = _post(db, post_id, bool(g.user and g.user["role"] == "admin"))
        viewer_id = g.user["id"] if g.user else None
        if post is None or (post["status"] != "published" and post["author_id"] != viewer_id):
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
        comments = comments_for_target(db, "post", post_id, request.args.get("order", "new"))
        return render_template(
            "community_detail.html", post=post, tags=tags, reposts=reposts,
            comments=comments, target_type="post", target_id=post_id,
        )

    @bp.route("/community/<int:post_id>/edit", methods=("GET", "POST"))
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

    @bp.post("/community/<int:post_id>/withdraw")
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

    @bp.post("/community/users/<int:user_id>/follow")
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

    @bp.post("/community/tags/<int:tag_id>/follow")
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

    @bp.get("/community/following")
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

    @bp.post("/community/<int:post_id>/repost")
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

    @bp.post("/comments/<target_type>/<int:target_id>")
    @login_required
    def add_comment(target_type, target_id):
        db = get_db()
        target = _target(db, target_type, target_id)
        if target is None:
            abort(404)
        body = request.form.get("body", "").strip()
        if not body or len(body) > 1000:
            abort(400, "评论不能为空且不能超过 1000 字。")
        db.execute(
            "INSERT INTO comments(author_id,target_type,target_id,body) VALUES(?,?,?,?)",
            (g.user["id"], target_type, target_id, body),
        )
        url = _target_url(target_type, target_id)
        recipients = _mentioned_user_ids(db, body)
        if target["owner_id"] != g.user["id"]:
            recipients.add(target["owner_id"])
        recipients.discard(g.user["id"])
        for user_id in recipients:
            notify(db, user_id, f"{g.user['name']} 评论了“{target['title']}”", url)
        db.commit()
        return redirect(url)

    @bp.post("/comments/<int:comment_id>/reply")
    @login_required
    def reply_comment(comment_id):
        db = get_db()
        parent = db.execute(
            "SELECT * FROM comments WHERE id=? AND status='published'", (comment_id,)
        ).fetchone()
        if parent is None:
            abort(404)
        if parent["parent_id"] is not None:
            abort(400, "回复只允许一层。")
        if not target_exists(db, parent["target_type"], parent["target_id"]):
            abort(404)
        body = request.form.get("body", "").strip()
        if not body or len(body) > 1000:
            abort(400, "回复不能为空且不能超过 1000 字。")
        db.execute(
            "INSERT INTO comments(author_id,target_type,target_id,parent_id,body) VALUES(?,?,?,?,?)",
            (g.user["id"], parent["target_type"], parent["target_id"], comment_id, body),
        )
        url = _target_url(parent["target_type"], parent["target_id"])
        recipients = _mentioned_user_ids(db, body) | {parent["author_id"]}
        recipients.discard(g.user["id"])
        for user_id in recipients:
            notify(db, user_id, f"{g.user['name']} 回复了你的评论", url)
        db.commit()
        return redirect(url)

    @bp.post("/comments/<int:comment_id>/withdraw")
    @login_required
    def withdraw_comment(comment_id):
        db = get_db()
        comment = db.execute("SELECT * FROM comments WHERE id=?", (comment_id,)).fetchone()
        if comment is None:
            abort(404)
        if comment["author_id"] != g.user["id"] and g.user["role"] != "admin":
            abort(403)
        db.execute(
            "UPDATE comments SET status='withdrawn',updated_at=CURRENT_TIMESTAMP "
            "WHERE id=? OR parent_id=?",
            (comment_id, comment_id),
        )
        db.commit()
        return redirect(_target_url(comment["target_type"], comment["target_id"]))

    @bp.post("/reactions/<target_type>/<int:target_id>/<kind>")
    @login_required
    def react(target_type, target_id, kind):
        if kind not in {"like", "favorite"}:
            abort(404)
        db = get_db()
        if not target_exists(db, target_type, target_id):
            abort(404)
        existing = db.execute(
            "SELECT id FROM content_reactions WHERE user_id=? AND target_type=? AND target_id=? AND kind=?",
            (g.user["id"], target_type, target_id, kind),
        ).fetchone()
        if existing:
            db.execute("DELETE FROM content_reactions WHERE id=?", (existing["id"],))
        else:
            db.execute(
                "INSERT INTO content_reactions(user_id,target_type,target_id,kind) VALUES(?,?,?,?)",
                (g.user["id"], target_type, target_id, kind),
            )
        db.commit()
        return redirect(_target_url(target_type, target_id))

    return bp
