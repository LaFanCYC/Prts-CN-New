import re
import sqlite3
from datetime import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from db import get_db


SECTIONS = {
    "resource": "资源交流",
    "lost_found": "失物招领",
    "study": "学习问答",
    "campus": "校园生活",
    "feedback": "建议反馈",
}

SECTION_NEIGHBORS = {
    "resource": {"study", "feedback"},
    "lost_found": {"campus", "resource"},
    "study": {"resource", "campus"},
    "campus": {"lost_found", "study"},
    "feedback": {"campus", "resource"},
}


def record_behavior(db, user_id, event_type, target_type, target_id):
    if user_id:
        db.execute(
            "INSERT OR IGNORE INTO behavior_events(user_id,event_type,target_type,target_id) VALUES(?,?,?,?)",
            (user_id, event_type, target_type, target_id),
        )


def screen_content(db, text, has_image=False):
    normalized = text.casefold()
    result = ("review", "图片需要人工审核") if has_image else ("publish", "")
    for rule in db.execute(
        "SELECT pattern,severity,note FROM moderation_rules WHERE is_active=1 ORDER BY severity"
    ).fetchall():
        if rule["pattern"].casefold() in normalized:
            if rule["severity"] == "reject":
                return "reject", rule["note"] or "内容未通过自动审核"
            result = ("review", rule["note"] or "内容需要人工审核")
    return result


def audit(db, actor_id, action, target_type, target_id=None, detail=""):
    db.execute(
        "INSERT INTO audit_logs(actor_id,action,target_type,target_id,detail) VALUES(?,?,?,?,?)",
        (actor_id, action, target_type, target_id, detail),
    )


def recommended_posts(db, user_id=None, limit=6):
    rows = db.execute(
        "SELECT p.*,u.name author_name,COALESCE(GROUP_CONCAT(t.name,' '),'') tag_names,"
        "(SELECT COUNT(*) FROM content_reactions r WHERE r.target_type='post' AND r.target_id=p.id AND r.kind='like') likes,"
        "(SELECT COUNT(*) FROM content_reactions r WHERE r.target_type='post' AND r.target_id=p.id AND r.kind='favorite') favorites,"
        "(SELECT COUNT(*) FROM comments c WHERE c.target_type='post' AND c.target_id=p.id AND c.status='published') comment_count,"
        "(SELECT COUNT(*) FROM reposts rp WHERE rp.post_id=p.id AND rp.status='published') repost_count "
        "FROM posts p JOIN users u ON u.id=p.author_id "
        "LEFT JOIN post_tags pt ON pt.post_id=p.id LEFT JOIN tags t ON t.id=pt.tag_id "
        "WHERE p.status='published' GROUP BY p.id ORDER BY p.created_at DESC,p.id DESC LIMIT 200"
    ).fetchall()
    interests = {}
    preferred_section = None
    if user_id:
        for row in db.execute(
            "SELECT t.name,e.event_type,COUNT(*) amount FROM behavior_events e "
            "JOIN post_tags pt ON e.target_type='post' AND pt.post_id=e.target_id "
            "JOIN tags t ON t.id=pt.tag_id WHERE e.user_id=? GROUP BY t.name,e.event_type",
            (user_id,),
        ).fetchall():
            weight = {"view_post": 1, "like": 5, "favorite": 7, "comment": 4, "repost": 6}.get(row["event_type"], 1)
            interests[row["name"]] = interests.get(row["name"], 0) + row["amount"] * weight
        section = db.execute(
            "SELECT p.section,COUNT(*) amount FROM behavior_events e JOIN posts p ON p.id=e.target_id "
            "WHERE e.user_id=? AND e.target_type='post' GROUP BY p.section ORDER BY amount DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        preferred_section = section["section"] if section else None
    max_interest = max(interests.values(), default=0)
    now = datetime.now()
    scored = []
    for row in rows:
        tag_score = sum(interests.get(tag, 0) for tag in row["tag_names"].split())
        content = min(60.0, 60.0 * tag_score / max_interest) if max_interest else 0.0
        created = datetime.fromisoformat(row["created_at"])
        age_days = max(0.0, (now - created).total_seconds() / 86400)
        freshness = max(0.0, 25.0 * (1 - age_days / 7))
        heat = min(15.0, row["likes"] * 2 + row["favorites"] * 3 + row["comment_count"] + row["repost_count"] * 2)
        item = dict(row)
        item["recommendation_score"] = content + freshness + heat
        scored.append(item)
    scored.sort(key=lambda item: (item["recommendation_score"], item["created_at"], item["id"]), reverse=True)
    if not preferred_section:
        return scored[:limit]
    same = [item for item in scored if item["section"] == preferred_section]
    near = [item for item in scored if item["section"] in SECTION_NEIGHBORS[preferred_section]]
    far = [item for item in scored if item not in same and item not in near]
    selected = same[: max(1, round(limit * 0.6))] + near[: max(1, round(limit * 0.3))] + far[: max(0, limit - round(limit * 0.9))]
    for item in scored:
        if item not in selected and len(selected) < limit:
            selected.append(item)
    return selected[:limit]


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

    @bp.before_request
    def enforce_restrictions():
        if request.method == "GET" or not g.user:
            return None
        endpoint = request.endpoint or ""
        restricted = endpoint in {
            "community.new_post", "community.edit_post", "community.repost",
            "community.add_comment", "community.reply_comment", "community.create_report",
        }
        if not restricted:
            return None
        row = get_db().execute(
            "SELECT kind FROM account_restrictions WHERE user_id=? AND is_active=1 "
            "AND ends_at>CURRENT_TIMESTAMP ORDER BY id DESC LIMIT 1",
            (g.user["id"],),
        ).fetchone()
        if row:
            abort(403, "账号当前被禁言或临时封禁。")

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
        if g.user and section in SECTIONS:
            record_behavior(get_db(), g.user["id"], "view_section", "section", list(SECTIONS).index(section) + 1)
            get_db().commit()
        return render_template(
            "community_list.html", posts=posts, sections=SECTIONS, selected=section
        )

    @bp.route("/community/new", methods=("GET", "POST"))
    @login_required
    def new_post():
        if request.method == "GET":
            return render_template("community_form.html", sections=SECTIONS, post=None)
        data, error = validate_post_form(request.form)
        db = get_db()
        moderation = ("publish", "")
        if not error:
            moderation = screen_content(db, f"{data['title']}\n{data['body']}")
            if moderation[0] == "reject":
                error = moderation[1]
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
        moderation = screen_content(db, f"{data['title']}\n{data['body']}", bool(image_name))
        status = "pending" if moderation[0] == "review" else "published"
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
        if g.user and post["status"] == "published":
            record_behavior(db, g.user["id"], "view_post", "post", post_id)
            db.commit()
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
        if screen_content(db, comment)[0] != "publish":
            abort(400, "转发内容需要修改或人工审核。")
        db.execute(
            "INSERT INTO reposts(author_id,post_id,comment) VALUES(?,?,?) "
            "ON CONFLICT(author_id,post_id) DO UPDATE SET comment=excluded.comment,status='published'",
            (g.user["id"], post_id, comment),
        )
        if post["author_id"] != g.user["id"]:
            notify(db, post["author_id"], f"{g.user['name']} 转发了你的帖子", url_for("community.post_detail", post_id=post_id))
        record_behavior(db, g.user["id"], "repost", "post", post_id)
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
        if screen_content(db, body)[0] != "publish":
            abort(400, "评论内容需要修改或人工审核。")
        db.execute(
            "INSERT INTO comments(author_id,target_type,target_id,body) VALUES(?,?,?,?)",
            (g.user["id"], target_type, target_id, body),
        )
        if target_type == "post":
            record_behavior(db, g.user["id"], "comment", "post", target_id)
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
        if screen_content(db, body)[0] != "publish":
            abort(400, "回复内容需要修改或人工审核。")
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
            if target_type == "post":
                record_behavior(db, g.user["id"], kind, "post", target_id)
        db.commit()
        return redirect(_target_url(target_type, target_id))

    @bp.post("/reports/<target_type>/<int:target_id>")
    @login_required
    def create_report(target_type, target_id):
        db = get_db()
        if target_type == "comment":
            exists = db.execute(
                "SELECT 1 FROM comments WHERE id=? AND status='published'", (target_id,)
            ).fetchone()
        else:
            exists = target_exists(db, target_type, target_id)
        if not exists:
            abort(404)
        reason = request.form.get("reason", "").strip()
        if not reason or len(reason) > 300:
            abort(400, "举报原因不能为空且不能超过 300 字。")
        try:
            db.execute(
                "INSERT INTO reports(reporter_id,target_type,target_id,reason) VALUES(?,?,?,?)",
                (g.user["id"], target_type, target_id, reason),
            )
            db.commit()
        except sqlite3.IntegrityError:
            abort(409, "该内容已有待处理举报。")
        flash("举报已提交。", "success")
        return redirect(_target_url(target_type, target_id) if target_type != "comment" else request.referrer or url_for("community.list_posts"))

    return bp
