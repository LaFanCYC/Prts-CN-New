import io
import base64
import json
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from app import create_app, match_score
from credit import credit_tier, permission_for_score


class CampusAppTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.database = data_dir / "test.db"
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": str(self.database),
                "DATA_DIR": str(data_dir),
                "UPLOAD_FOLDER": str(data_dir / "uploads"),
                "SECRET_KEY": "test-secret",
                "CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def db(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def register(self, username="alice", student_no="S001", password="password1"):
        return self.client.post(
            "/register",
            data={
                "username": username,
                "password": password,
                "password_confirm": password,
                "name": username.title(),
                "student_no": student_no,
                "grade": "2024级",
                "class_name": "软件1班",
            },
        )

    def login(self, username="alice", password="password1"):
        return self.client.post(
            "/login", data={"username": username, "password": password}
        )

    def publish_resource(self, **overrides):
        data = {
            "name": "Python 入门教材",
            "category": "教材书籍",
            "condition_level": "九成新",
            "transfer_mode": "borrow",
            "description": "适合零基础同学",
            "keywords": "Python,教材",
        }
        data.update(overrides)
        return self.client.post("/resources/new", data=data)

    def publish_post(self, **overrides):
        data = {
            "title": "Python 学习小组招募",
            "section": "study",
            "body": "每周三一起复习基础知识。",
            "tags": " Python, 学习,python ",
        }
        data.update(overrides)
        return self.client.post("/community/new", data=data)

    def switch_user(self, username, student_no):
        self.client.post("/logout")
        self.register(username=username, student_no=student_no)
        self.login(username=username)

    def resource_id(self, name=None):
        with self.db() as db:
            if name:
                return db.execute("SELECT id FROM resources WHERE name=?", (name,)).fetchone()[0]
            return db.execute("SELECT id FROM resources ORDER BY id DESC").fetchone()[0]

    def application_id(self, username):
        with self.db() as db:
            return db.execute(
                "SELECT a.id FROM applications a JOIN users u ON u.id=a.applicant_id WHERE u.username=? ORDER BY a.id DESC",
                (username,),
            ).fetchone()[0]

    def test_registration_hashes_password_and_rejects_duplicate_identity(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)

        with self.db() as db:
            user = db.execute(
                "SELECT username, password_hash FROM users WHERE username = 'alice'"
            ).fetchone()
        self.assertEqual(user["username"], "alice")
        self.assertNotEqual(user["password_hash"], "password1")

        response = self.register(username="alice2", student_no="S001")
        self.assertEqual(response.status_code, 400)
        self.assertIn("学号已存在", response.get_data(as_text=True))

    def test_legacy_admin_schema_upgrades_first_admin_to_owner(self):
        legacy_db = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_db)
        connection.executescript("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT UNIQUE, username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, name TEXT NOT NULL, student_no TEXT NOT NULL UNIQUE,
                grade TEXT NOT NULL, class_name TEXT NOT NULL, contact TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','admin')),
                is_active INTEGER NOT NULL DEFAULT 1, must_change_password INTEGER NOT NULL DEFAULT 0,
                credit_score INTEGER NOT NULL DEFAULT 100, credit_recovered_on TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users(username,password_hash,name,student_no,grade,class_name,role)
            VALUES('legacy','hash','Legacy','A001','教师','管理组','admin');
        """)
        connection.close()
        app = create_app({"TESTING": True, "DATABASE": str(legacy_db), "DATA_DIR": self.temp_dir.name,
                          "UPLOAD_FOLDER": str(Path(self.temp_dir.name) / "uploads"), "SECRET_KEY": "legacy"})
        with app.app_context():
            with sqlite3.connect(legacy_db) as upgraded:
                self.assertEqual(upgraded.execute("SELECT role FROM users WHERE username='legacy'").fetchone()[0], "owner")

    def test_credit_tiers_and_permissions_have_fixed_boundaries(self):
        self.assertEqual(credit_tier(100)["name"], "优先")
        self.assertEqual(credit_tier(80)["name"], "正常")
        self.assertEqual(credit_tier(60)["name"], "靠后")
        self.assertEqual(credit_tier(59)["name"], "受限")
        self.assertTrue(permission_for_score(60)["can_apply"])
        self.assertFalse(permission_for_score(59)["can_apply"])
        self.assertFalse(permission_for_score(39)["can_publish"])

    def test_disabled_user_cannot_login_and_student_cannot_open_admin(self):
        self.register()
        with self.db() as db:
            db.execute("UPDATE users SET is_active = 0 WHERE username = 'alice'")
            db.commit()

        response = self.login()
        self.assertEqual(response.status_code, 403)

        with self.db() as db:
            db.execute("UPDATE users SET is_active = 1 WHERE username = 'alice'")
            db.commit()
        self.login()
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_resource_publish_validates_image_and_normalizes_skill_fields(self):
        self.assertEqual(self.publish_resource().status_code, 302)
        self.register()
        self.login()
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        response = self.publish_resource(
            name="视频剪辑互助",
            category="技能服务",
            condition_level="全新",
            transfer_mode="free_help",
            image=(io.BytesIO(tiny_png), "skill.png"),
        )
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            resource = db.execute(
                "SELECT * FROM resources WHERE name = '视频剪辑互助'"
            ).fetchone()
        self.assertEqual(resource["condition_level"], "不适用")
        self.assertTrue(resource["image_name"].endswith(".png"))
        self.assertTrue((Path(self.app.config["UPLOAD_FOLDER"]) / resource["image_name"]).exists())

        response = self.publish_resource(
            name="伪造图片", image=(io.BytesIO(b"not-an-image"), "fake.png")
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("图片格式", response.get_data(as_text=True))

    def test_resource_search_combines_category_and_keyword(self):
        self.register()
        self.login()
        self.publish_resource()
        self.publish_resource(
            name="摄影入门互助",
            category="技能服务",
            condition_level="不适用",
            transfer_mode="free_help",
            description="一起学习构图",
            keywords="摄影,构图",
        )

        response = self.client.get("/resources?category=技能服务&q=摄影")
        text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("摄影入门互助", text)
        self.assertNotIn("Python 入门教材", text)

    def test_ai_search_is_available_to_visitors_and_falls_back_to_keyword_results(self):
        self.register()
        self.login()
        self.publish_resource(name="Python 算法教材", description="适合算法课复习")
        self.client.post("/logout")

        response = self.client.post("/api/ai/search", json={"query": "算法教材"})
        data = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "keyword")
        self.assertEqual(data["results"][0]["title"], "Python 算法教材")
        self.assertIn("data-ai-assistant", self.client.get("/").get_data(as_text=True))

        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.commit()
        self.login()
        self.assertEqual(
            self.client.post(
                "/admin/ai-config",
                data={
                    "enabled": "on",
                    "api_endpoint": "https://ai.example/v1/chat/completions",
                    "api_key": "secret",
                    "model": "test-model",
                    "system_prompt": "只返回 JSON。",
                    "max_results": "5",
                },
            ).status_code,
            302,
        )
        with patch("app.urlopen", side_effect=URLError("offline")):
            response = self.client.post("/api/ai/search", json={"query": "算法教材"})
        self.assertEqual(response.get_json()["mode"], "keyword")

    def test_ai_search_rejects_empty_and_oversized_queries(self):
        self.assertEqual(
            self.client.post("/api/ai/search", json={"query": "  "}).get_json(),
            {"mode": "keyword", "results": []},
        )
        self.assertEqual(
            self.client.post("/api/ai/search", json={"query": "x" * 101}).status_code,
            400,
        )

    def test_ai_search_accepts_markdown_wrapped_json(self):
        self.register()
        self.login()
        self.publish_resource(name="Python 算法教材", description="适合算法课复习")
        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.commit()
        self.login()
        self.client.post("/admin/ai-config", data={
            "enabled": "on", "api_endpoint": "https://ai.example/v1/chat/completions",
            "api_key": "secret", "model": "test-model", "system_prompt": "只返回 JSON。",
            "max_results": "5",
        })
        response_body = json.dumps({"choices": [{"message": {"content": (
            "```json\n[{\"id\": \"resource:1\", \"reason\": \"适合算法复习\"}]\n```"
        )}}]}).encode()
        with patch("app.urlopen") as urlopen_mock:
            urlopen_mock.return_value.__enter__.return_value.read.return_value = response_body
            response = self.client.post("/api/ai/search", json={"query": "算法教材"})
        self.assertEqual(response.get_json()["mode"], "ai")
        self.assertEqual(response.get_json()["results"][0]["reason"], "适合算法复习")

    def test_lost_found_filters_by_occurred_date(self):
        self.register()
        self.login()
        common = {"description": "测试物品", "location": "图书馆", "keywords": "测试"}
        self.client.post("/lost-found/new/lost", data={
            "title": "旧物品", "occurred_on": "2026-01-01", **common
        })
        self.client.post("/lost-found/new/found", data={
            "title": "新物品", "occurred_on": "2026-02-01", **common
        })
        page = self.client.get("/lost-found?date_from=2026-02-01&date_to=2026-02-01").get_data(as_text=True)
        self.assertIn("新物品", page)
        self.assertNotIn("旧物品", page)

    def test_owner_can_edit_and_withdraw_resource_while_other_users_cannot(self):
        self.register()
        self.login()
        self.publish_resource()
        with self.db() as db:
            resource_id = db.execute("SELECT id FROM resources").fetchone()[0]

        response = self.client.post(
            f"/resources/{resource_id}/edit",
            data={
                "name": "Python 教材第二版",
                "category": "教材书籍",
                "condition_level": "七成新",
                "transfer_mode": "borrow",
                "description": "补充了习题",
                "keywords": "Python,教材",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.client.post("/logout")
        self.register(username="bob", student_no="S002")
        self.login(username="bob")
        self.assertEqual(
            self.client.post(f"/resources/{resource_id}/edit", data={}).status_code, 403
        )

        self.client.post("/logout")
        self.login()
        response = self.client.post(f"/resources/{resource_id}/withdraw")
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            self.assertIsNone(
                db.execute("SELECT id FROM resources WHERE id=?", (resource_id,)).fetchone()
            )

    def test_borrow_flow_rejects_other_candidates_and_reopens_after_return(self):
        self.register()
        self.login()
        self.publish_resource()
        resource_id = self.resource_id()
        due = (date.today() + timedelta(days=7)).isoformat()

        self.switch_user("bob", "S002")
        self.assertEqual(
            self.client.post(
                f"/resources/{resource_id}/apply",
                data={"note": "课程需要", "expected_return_date": due},
            ).status_code,
            302,
        )
        bob_application = self.application_id("bob")

        self.switch_user("carol", "S003")
        self.client.post(
            f"/resources/{resource_id}/apply",
            data={"note": "复习使用", "expected_return_date": due},
        )
        carol_application = self.application_id("carol")

        self.client.post("/logout")
        self.login()
        self.assertEqual(
            self.client.post(f"/applications/{bob_application}/approve").status_code, 302
        )
        with self.db() as db:
            statuses = {
                row["id"]: row["status"]
                for row in db.execute("SELECT id,status FROM applications").fetchall()
            }
            resource_status = db.execute(
                "SELECT status FROM resources WHERE id=?", (resource_id,)
            ).fetchone()[0]
        self.assertEqual(statuses[bob_application], "borrowed")
        self.assertEqual(statuses[carol_application], "rejected")
        self.assertEqual(resource_status, "in_use")
        with self.db() as db:
            carol_notice = db.execute(
                "SELECT n.message FROM notifications n JOIN users u ON u.id=n.user_id "
                "WHERE u.username='carol' AND n.message LIKE '%其他申请%'"
            ).fetchone()
        self.assertIsNotNone(carol_notice)

        self.client.post("/logout")
        self.login(username="bob")
        self.client.post(f"/applications/{bob_application}/request-return")
        self.client.post("/logout")
        self.login()
        self.client.post(f"/applications/{bob_application}/confirm-return")
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT status FROM applications WHERE id=?", (bob_application,)).fetchone()[0],
                "returned",
            )
            self.assertEqual(
                db.execute("SELECT credit_score FROM users WHERE username='bob'").fetchone()[0], 102,
            )
            self.assertEqual(
                db.execute("SELECT delta FROM credit_events WHERE user_id=(SELECT id FROM users WHERE username='bob')").fetchone()[0], 2,
            )
            self.assertEqual(
                db.execute("SELECT status FROM resources WHERE id=?", (resource_id,)).fetchone()[0],
                "available",
            )

    def test_repeatable_skill_keeps_queue_and_reopens_after_confirmation(self):
        self.register()
        self.login()
        self.publish_resource(
            name="视频剪辑互助",
            category="技能服务",
            condition_level="不适用",
            transfer_mode="free_help",
            description="一起完成短视频",
            keywords="剪辑,视频",
        )
        resource_id = self.resource_id()

        self.switch_user("bob", "S002")
        self.client.post(f"/resources/{resource_id}/apply", data={"note": "需要剪辑指导"})
        bob_application = self.application_id("bob")
        self.switch_user("carol", "S003")
        self.client.post(f"/resources/{resource_id}/apply", data={"note": "想学习转场"})
        carol_application = self.application_id("carol")

        self.client.post("/logout")
        self.login()
        self.client.post(f"/applications/{bob_application}/approve")
        self.client.post(f"/applications/{bob_application}/request-completion")
        self.client.post("/logout")
        self.login(username="bob")
        self.client.post(f"/applications/{bob_application}/confirm-completion")

        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT status FROM applications WHERE id=?", (bob_application,)).fetchone()[0],
                "completed",
            )
            self.assertEqual(
                db.execute("SELECT status FROM applications WHERE id=?", (carol_application,)).fetchone()[0],
                "pending",
            )
            self.assertEqual(
                db.execute("SELECT status FROM resources WHERE id=?", (resource_id,)).fetchone()[0],
                "available",
            )

    def test_lost_found_similarity_creates_one_match_and_two_notifications(self):
        self.assertGreaterEqual(
            match_score("黑色校园卡", "校园卡", "校园卡,黑色", "黑色,校园卡"), 0.45
        )
        self.assertLess(
            match_score("篮球", "蓝牙耳机", "体育", "电子产品"), 0.45
        )
        self.register()
        self.login()
        self.client.post(
            "/lost-found/new/lost",
            data={
                "title": "黑色校园卡",
                "description": "卡套背面有贴纸",
                "occurred_on": date.today().isoformat(),
                "location": "图书馆",
                "keywords": "校园卡,黑色",
            },
        )
        self.switch_user("bob", "S002")
        self.client.post(
            "/lost-found/new/found",
            data={
                "title": "捡到校园卡",
                "description": "黑色卡套",
                "occurred_on": date.today().isoformat(),
                "location": "图书馆二楼",
                "keywords": "黑色,校园卡",
            },
        )
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 2)

    def test_resolved_lost_item_is_searchable_but_not_matched_and_contact_is_private(self):
        self.register()
        self.login()
        with self.db() as db:
            db.execute("UPDATE users SET contact='13800000000' WHERE username='alice'")
            db.commit()
        self.client.post(
            "/lost-found/new/lost",
            data={
                "title": "银色保温杯",
                "description": "杯盖有划痕",
                "occurred_on": date.today().isoformat(),
                "location": "教学楼",
                "keywords": "保温杯,银色",
            },
        )
        with self.db() as db:
            item_id = db.execute("SELECT id FROM lost_found").fetchone()[0]
        self.client.post(f"/lost-found/{item_id}/resolve")
        self.client.post("/logout")

        response = self.client.get(f"/lost-found/{item_id}")
        self.assertNotIn("13800000000", response.get_data(as_text=True))
        self.assertIn("银色保温杯", self.client.get("/lost-found?status=resolved").get_data(as_text=True))

        self.switch_user("bob", "S002")
        self.assertIn("13800000000", self.client.get(f"/lost-found/{item_id}").get_data(as_text=True))
        self.client.post(
            "/lost-found/new/found",
            data={
                "title": "银色保温杯",
                "description": "教学楼捡到",
                "occurred_on": date.today().isoformat(),
                "location": "教学楼",
                "keywords": "保温杯,银色",
            },
        )
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)

    def test_admin_stats_and_user_controls_protect_the_last_admin(self):
        self.register()
        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.commit()
        self.login()
        self.publish_resource()
        self.client.post("/logout")
        self.register(username="bob", student_no="S002")
        with self.db() as db:
            bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]

        self.login()
        stats_response = self.client.get("/api/admin/stats")
        self.assertEqual(stats_response.status_code, 200)
        stats = stats_response.get_json()
        self.assertEqual(stats["summary"]["users"], 2)
        self.assertEqual(stats["summary"]["resources"], 1)

        self.assertEqual(
            self.client.post(f"/admin/users/{bob_id}/active").status_code, 302
        )
        with self.db() as db:
            self.assertEqual(db.execute("SELECT is_active FROM users WHERE id=?", (bob_id,)).fetchone()[0], 0)

        with self.db() as db:
            alice_id = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
        response = self.client.post(
            f"/admin/users/{alice_id}/role", data={"role": "student"}
        )
        self.assertEqual(response.status_code, 409)
        with self.db() as db:
            self.assertEqual(db.execute("SELECT role FROM users WHERE id=?", (alice_id,)).fetchone()[0], "owner")

    def test_admin_cannot_manage_staff_or_change_system_settings(self):
        self.register()
        self.register(username="mod", student_no="S002")
        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.execute("UPDATE users SET role='admin' WHERE username='mod'")
            db.commit()
            admin_id = db.execute("SELECT id FROM users WHERE username='mod'").fetchone()[0]
        self.client.post("/logout")
        self.client.post("/login", data={"username": "mod", "password": "password1"})
        self.assertEqual(self.client.post(f"/admin/users/1/active").status_code, 403)
        self.assertEqual(self.client.post("/admin/backups").status_code, 403)
        self.assertEqual(self.client.post(f"/admin/users/{admin_id}/role", data={"role": "student"}).status_code, 403)

    def test_admin_modules_and_resource_bulk_withdraw(self):
        self.register()
        with self.db() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='alice'")
            db.commit()
        self.login()
        self.publish_resource(name="待管理资源")
        resource_id = self.resource_id("待管理资源")
        for route in ("/admin", "/admin/users", "/admin/users/1", "/admin/resources", "/admin/content", "/admin/credit", "/admin/settings", "/admin/audit"):
            self.assertEqual(self.client.get(route).status_code, 200)
        page = self.client.get("/admin/resources?q=待管理&status=available").get_data(as_text=True)
        self.assertIn("待管理资源", page)
        self.assertEqual(self.client.post("/admin/resources/bulk-withdraw", data={"resource_ids": str(resource_id)}).status_code, 302)
        with self.db() as db:
            self.assertEqual(db.execute("SELECT status FROM resources WHERE id=?", (resource_id,)).fetchone()[0], "withdrawn")
            item_id = db.execute(
                "INSERT INTO lost_found(user_id,kind,title,description,occurred_on,location,keywords) VALUES(1,'lost','待审核失物','描述','2026-01-01','图书馆','卡片')"
            ).lastrowid
            db.commit()
        self.assertEqual(self.client.post(f"/admin/lost-found/{item_id}/withdraw").status_code, 302)
        with self.db() as db:
            self.assertEqual(db.execute("SELECT status FROM lost_found WHERE id=?", (item_id,)).fetchone()[0], "withdrawn")

    def test_student_cannot_call_admin_write_routes(self):
        self.register()
        self.login()
        with self.db() as db:
            user_id = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
        self.assertEqual(
            self.client.post(f"/admin/users/{user_id}/active").status_code, 403
        )

    def test_demo_initializer_is_idempotent_and_creates_all_demo_areas(self):
        runner = self.app.test_cli_runner()
        first = runner.invoke(args=["init-demo"])
        self.assertEqual(first.exit_code, 0, first.output)
        with self.db() as db:
            first_counts = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "users", "resources", "applications", "lost_found", "notifications",
                    "posts", "tags", "comments",
                )
            )
        self.assertTrue(
            all(actual >= minimum for actual, minimum in zip(first_counts, (3, 3, 1, 2, 1, 5, 5, 1)))
        )

        second = runner.invoke(args=["init-demo"])
        self.assertEqual(second.exit_code, 0, second.output)
        with self.db() as db:
            second_counts = tuple(
                db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "users", "resources", "applications", "lost_found", "notifications",
                    "posts", "tags", "comments",
                )
            )
        self.assertEqual(first_counts, second_counts)

    def test_admin_force_withdraw_preserves_active_flow_history(self):
        self.register()
        with self.db() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='alice'")
            db.commit()
        self.login()
        self.publish_resource()
        resource_id = self.resource_id()
        self.switch_user("bob", "S002")
        self.client.post(
            f"/resources/{resource_id}/apply",
            data={
                "note": "借用",
                "expected_return_date": (date.today() + timedelta(days=3)).isoformat(),
            },
        )
        application_id = self.application_id("bob")
        self.client.post("/logout")
        self.login()
        self.client.post(f"/applications/{application_id}/approve")

        response = self.client.post(f"/resources/{resource_id}/withdraw")
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT status FROM resources WHERE id=?", (resource_id,)).fetchone()[0],
                "withdrawn",
            )
            self.assertEqual(
                db.execute("SELECT status FROM applications WHERE id=?", (application_id,)).fetchone()[0],
                "withdrawn",
            )

    def test_admin_password_reset_forces_profile_change_before_other_pages(self):
        self.register()
        with self.db() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='alice'")
            db.commit()
        self.login()
        self.client.post("/logout")
        self.register(username="bob", student_no="S002")
        with self.db() as db:
            bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]
        self.login()
        self.client.post(
            f"/admin/users/{bob_id}/reset-password", data={"password": "temporary1"}
        )
        self.client.post("/logout")
        self.login(username="bob", password="temporary1")
        response = self.client.get("/resources")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/profile"))

    def test_edit_removes_stale_lost_found_match_and_withdrawn_item_cannot_restore(self):
        self.register()
        self.login()
        common = {
            "description": "测试信息",
            "occurred_on": date.today().isoformat(),
            "location": "图书馆",
            "keywords": "校园卡,蓝色",
        }
        self.client.post("/lost-found/new/lost", data={"title": "蓝色校园卡", **common})
        self.switch_user("bob", "S002")
        self.client.post("/lost-found/new/found", data={"title": "捡到校园卡", **common})
        with self.db() as db:
            found_id = db.execute("SELECT id FROM lost_found WHERE kind='found'").fetchone()[0]
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)
        self.client.post(
            f"/lost-found/{found_id}/edit",
            data={
                "title": "白色篮球",
                "description": "操场捡到",
                "occurred_on": date.today().isoformat(),
                "location": "操场",
                "keywords": "篮球,白色",
            },
        )
        with self.db() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 0)
            db.execute("UPDATE lost_found SET status='withdrawn' WHERE id=?", (found_id,))
            db.commit()
        self.assertEqual(self.client.post(f"/lost-found/{found_id}/restore").status_code, 409)

    def test_overdue_badge_and_admin_global_application_view(self):
        self.register()
        self.login()
        self.publish_resource()
        resource_id = self.resource_id()
        self.switch_user("bob", "S002")
        self.client.post(
            f"/resources/{resource_id}/apply",
            data={"expected_return_date": (date.today() + timedelta(days=2)).isoformat()},
        )
        application_id = self.application_id("bob")
        self.client.post("/logout")
        self.login()
        self.client.post(f"/applications/{application_id}/approve")
        with self.db() as db:
            db.execute(
                "UPDATE applications SET expected_return_date=? WHERE id=?",
                ((date.today() - timedelta(days=1)).isoformat(), application_id),
            )
            db.commit()
        self.client.post("/logout")
        self.login(username="bob")
        self.assertIn("已逾期", self.client.get("/applications").get_data(as_text=True))

        self.client.post("/logout")
        self.register(username="carol", student_no="S003")
        with self.db() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='carol'")
            db.commit()
        self.login(username="carol")
        page = self.client.get("/applications").get_data(as_text=True)
        self.assertIn("Python 入门教材", page)
        self.assertIn("Bob", page)

    def test_concurrent_approvals_leave_exactly_one_active_borrower(self):
        self.register()
        self.login()
        self.publish_resource()
        resource_id = self.resource_id()
        due = (date.today() + timedelta(days=3)).isoformat()
        self.switch_user("bob", "S002")
        self.client.post(f"/resources/{resource_id}/apply", data={"expected_return_date": due})
        bob_application = self.application_id("bob")
        self.switch_user("carol", "S003")
        self.client.post(f"/resources/{resource_id}/apply", data={"expected_return_date": due})
        carol_application = self.application_id("carol")

        clients = [self.app.test_client(), self.app.test_client()]
        for client in clients:
            client.post("/login", data={"username": "alice", "password": "password1"})
        barrier = threading.Barrier(2)
        results = []

        def approve(client, application_id):
            barrier.wait()
            results.append(client.post(f"/applications/{application_id}/approve").status_code)

        threads = [
            threading.Thread(target=approve, args=(clients[0], bob_application)),
            threading.Thread(target=approve, args=(clients[1], carol_application)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), [302, 409])
        with self.db() as db:
            active = db.execute(
                "SELECT COUNT(*) FROM applications WHERE resource_id=? AND status='borrowed'",
                (resource_id,),
            ).fetchone()[0]
        self.assertEqual(active, 1)

    def test_create_admin_command_is_safe_and_idempotent(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=["create-owner"],
            input="rootadmin\nstrongpass1\nstrongpass1\n平台管理员\nADMIN002\n教师\n管理组\n13800000000\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        with self.db() as db:
            admin = db.execute(
                "SELECT username,role,is_active FROM users WHERE username='rootadmin'"
            ).fetchone()
        self.assertEqual((admin["role"], admin["is_active"]), ("owner", 1))

        second = runner.invoke(args=["create-owner"], input="")
        self.assertEqual(second.exit_code, 0, second.output)
        self.assertIn("已有有效管理员", second.output)
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM users WHERE role='owner'").fetchone()[0], 1
            )

    def test_community_schema_initializes_all_tables(self):
        expected = {
            "posts",
            "tags",
            "post_tags",
            "comments",
            "content_reactions",
            "user_follows",
            "tag_follows",
            "reports",
            "moderation_rules",
            "account_restrictions",
            "audit_logs",
            "behavior_events",
            "backup_records",
        }
        with self.db() as db:
            actual = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertTrue(expected <= actual, expected - actual)

    def test_post_publish_normalizes_tags_and_enforces_ownership(self):
        self.register()
        self.login()
        response = self.publish_post()
        self.assertEqual(response.status_code, 302)

        with self.db() as db:
            post = db.execute("SELECT * FROM posts").fetchone()
            tags = {
                row[0]
                for row in db.execute(
                    "SELECT t.name FROM tags t JOIN post_tags pt ON pt.tag_id=t.id "
                    "WHERE pt.post_id=?",
                    (post["id"],),
                ).fetchall()
            }
        self.assertEqual(post["status"], "published")
        self.assertEqual(tags, {"python", "学习"})
        self.assertIn("Python 学习小组招募", self.client.get("/community").get_data(as_text=True))

        self.switch_user("bob", "S002")
        self.assertEqual(
            self.client.post(
                f"/community/{post['id']}/edit",
                data={"title": "篡改", "section": "campus", "body": "无权限", "tags": "测试"},
            ).status_code,
            403,
        )

    def test_following_feed_includes_followed_author_posts(self):
        self.register()
        self.login()
        response = self.publish_post()
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            alice_id = db.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0]
            post_id = db.execute("SELECT id FROM posts").fetchone()[0]

        self.switch_user("bob", "S002")
        self.assertEqual(
            self.client.post(f"/community/users/{alice_id}/follow").status_code, 302
        )
        following = self.client.get("/community/following").get_data(as_text=True)
        self.assertIn("Python 学习小组招募", following)


    def test_users_and_posts_receive_public_uids(self):
        self.register()
        self.login()
        self.publish_post()
        with self.db() as db:
            user_uid = db.execute("SELECT uid FROM users WHERE username='alice'").fetchone()[0]
            post_uid = db.execute("SELECT uid FROM posts").fetchone()[0]
        self.assertRegex(user_uid, r"^U-[0-9a-f]{32}$")
        self.assertRegex(post_uid, r"^P-[0-9a-f]{32}$")

    def test_shared_comments_cover_posts_resources_and_lost_found(self):
        self.register()
        self.login()
        self.publish_post()
        self.publish_resource()
        common = {
            "description": "在一号教学楼附近遗失",
            "occurred_on": date.today().isoformat(),
            "location": "一号教学楼",
            "keywords": "校园卡,蓝色",
        }
        self.client.post("/lost-found/new/lost", data={"title": "蓝色校园卡", **common})
        with self.db() as db:
            post_id = db.execute("SELECT id FROM posts").fetchone()[0]
            resource_id = db.execute("SELECT id FROM resources").fetchone()[0]
            lost_id = db.execute("SELECT id FROM lost_found").fetchone()[0]

        self.switch_user("bob", "S002")
        for target_type, target_id in (
            ("post", post_id),
            ("resource", resource_id),
            ("lost_found", lost_id),
        ):
            response = self.client.post(
                f"/comments/{target_type}/{target_id}", data={"body": "这个信息很有帮助"}
            )
            self.assertEqual(response.status_code, 302)

        self.assertIn(
            "这个信息很有帮助",
            self.client.get(f"/community/{post_id}").get_data(as_text=True),
        )
        self.assertIn(
            "这个信息很有帮助",
            self.client.get(f"/resources/{resource_id}").get_data(as_text=True),
        )
        self.assertIn(
            "这个信息很有帮助",
            self.client.get(f"/lost-found/{lost_id}").get_data(as_text=True),
        )

    def test_reply_depth_reactions_and_comment_notifications(self):
        self.register()
        self.login()
        self.publish_post()
        with self.db() as db:
            post_id = db.execute("SELECT id FROM posts").fetchone()[0]

        self.switch_user("bob", "S002")
        response = self.client.post(
            f"/comments/post/{post_id}", data={"body": "请问几点开始？"}
        )
        self.assertEqual(response.status_code, 302)
        with self.db() as db:
            comment_id = db.execute("SELECT id FROM comments").fetchone()[0]
            alice_notices = db.execute(
                "SELECT COUNT(*) FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.username='alice'"
            ).fetchone()[0]
        self.assertEqual(alice_notices, 1)

        self.client.post("/logout")
        self.login()
        self.assertEqual(
            self.client.post(
                f"/comments/{comment_id}/reply", data={"body": "晚上七点，@bob"}
            ).status_code,
            302,
        )
        with self.db() as db:
            reply_id = db.execute(
                "SELECT id FROM comments WHERE parent_id=?", (comment_id,)
            ).fetchone()[0]
            bob_notices = db.execute(
                "SELECT COUNT(*) FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.username='bob'"
            ).fetchone()[0]
        self.assertGreaterEqual(bob_notices, 1)

        self.client.post("/logout")
        self.login(username="bob")
        self.assertEqual(
            self.client.post(
                f"/comments/{reply_id}/reply", data={"body": "不能继续嵌套"}
            ).status_code,
            400,
        )
        before = bob_notices
        self.assertEqual(
            self.client.post(f"/reactions/post/{post_id}/like").status_code, 302
        )
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM content_reactions").fetchone()[0], 1
            )
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.username='bob'"
                ).fetchone()[0],
                before,
            )
        self.client.post(f"/reactions/post/{post_id}/like")
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM content_reactions").fetchone()[0], 0
            )

    def test_home_uses_three_compact_lists_and_guidance_pages(self):
        self.register()
        self.login()
        self.publish_post(title="如何选择 Python 教材")
        self.publish_resource(name="数据结构教材")
        self.client.post(
            "/lost-found/new/lost",
            data={
                "title": "黑色雨伞",
                "description": "食堂门口遗失",
                "occurred_on": date.today().isoformat(),
                "location": "一食堂",
                "keywords": "雨伞,黑色",
            },
        )

        text = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("让校园里的每份资源，再多发挥一次价值", text)
        for heading, item in (
            ("推荐帖子", "如何选择 Python 教材"),
            ("最新资源", "数据结构教材"),
            ("失物招领", "黑色雨伞"),
        ):
            self.assertIn(heading, text)
            self.assertIn(item, text)

        resource_id = self.resource_id("数据结构教材")
        detail = self.client.get(f"/resources/{resource_id}").get_data(as_text=True)
        self.assertIn("面包屑导航", detail)
        self.assertIn("资源大厅", detail)
        for path, title in (
            ("/rules", "社区规则"),
            ("/help", "帮助中心"),
            ("/questioning-guide", "如何提出好问题"),
        ):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn(title, page.get_data(as_text=True))

    def test_recommendations_use_behavior_tags_and_dedupe_daily_views(self):
        self.register()
        self.login()
        self.publish_post(title="Python 基础资料", tags="python,编程")
        self.publish_post(title="Python 练习伙伴", tags="python,练习")
        self.publish_post(title="校园歌手比赛", section="campus", tags="音乐,校园")
        with self.db() as db:
            seed_id = db.execute(
                "SELECT id FROM posts WHERE title='Python 基础资料'"
            ).fetchone()[0]

        self.switch_user("bob", "S002")
        self.client.get(f"/community/{seed_id}")
        self.client.get(f"/community/{seed_id}")
        self.client.post(f"/reactions/post/{seed_id}/like")

        home = self.client.get("/").get_data(as_text=True)
        self.assertLess(home.index("Python 练习伙伴"), home.index("校园歌手比赛"))
        with self.db() as db:
            views = db.execute(
                "SELECT COUNT(*) FROM behavior_events WHERE event_type='view_post' AND target_id=?",
                (seed_id,),
            ).fetchone()[0]
            likes = db.execute(
                "SELECT COUNT(*) FROM behavior_events WHERE event_type='like' AND target_id=?",
                (seed_id,),
            ).fetchone()[0]
            view_count = db.execute("SELECT view_count FROM posts WHERE id=?", (seed_id,)).fetchone()[0]
        self.assertEqual((views, likes, view_count), (1, 1, 1))

    def test_text_moderation_rejects_or_queues_posts(self):
        self.register()
        self.login()
        with self.db() as db:
            db.execute(
                "INSERT INTO moderation_rules(pattern,severity,note) VALUES('诈骗','reject','明显欺诈')"
            )
            db.execute(
                "INSERT INTO moderation_rules(pattern,severity,note) VALUES('兼职','review','疑似广告')"
            )
            db.commit()

        rejected = self.publish_post(body="这是诈骗信息")
        self.assertEqual(rejected.status_code, 400)
        queued = self.publish_post(title="校园兼职交流", body="分享兼职经验")
        self.assertEqual(queued.status_code, 302)
        with self.db() as db:
            rows = db.execute("SELECT title,status FROM posts ORDER BY id").fetchall()
        self.assertEqual([tuple(row) for row in rows], [("校园兼职交流", "pending")])

    def test_report_withdrawal_audit_and_mute_form_a_governance_loop(self):
        self.register()
        self.login()
        self.publish_post()
        with self.db() as db:
            post_id = db.execute("SELECT id FROM posts").fetchone()[0]

        self.switch_user("bob", "S002")
        self.assertEqual(
            self.client.post(
                f"/reports/post/{post_id}", data={"reason": "疑似广告刷屏"}
            ).status_code,
            302,
        )
        with self.db() as db:
            report_id = db.execute("SELECT id FROM reports").fetchone()[0]
            bob_id = db.execute("SELECT id FROM users WHERE username='bob'").fetchone()[0]

        self.client.post("/logout")
        self.register(username="carol", student_no="S003")
        with self.db() as db:
            db.execute("UPDATE users SET role='admin' WHERE username='carol'")
            db.commit()
        self.login(username="carol")
        self.assertEqual(
            self.client.post(
                f"/admin/reports/{report_id}/withdraw", data={"resolution": "确认违规"}
            ).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                f"/admin/users/{bob_id}/restrict",
                data={"kind": "mute", "hours": "24", "reason": "连续刷屏"},
            ).status_code,
            302,
        )
        with self.db() as db:
            self.assertEqual(
                db.execute("SELECT status FROM posts WHERE id=?", (post_id,)).fetchone()[0],
                "withdrawn",
            )
            self.assertEqual(
                db.execute("SELECT status FROM reports WHERE id=?", (report_id,)).fetchone()[0],
                "resolved",
            )
            self.assertGreaterEqual(db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0], 2)

        self.client.post("/logout")
        self.login(username="bob")
        self.assertEqual(self.publish_post(title="禁言后发帖").status_code, 403)

    def test_backup_cli_archives_database_uploads_and_guards_restore(self):
        upload = Path(self.app.config["UPLOAD_FOLDER"]) / "proof.txt"
        upload.write_text("backup proof", encoding="utf-8")
        runner = self.app.test_cli_runner()

        created = runner.invoke(args=["create-backup"])
        self.assertEqual(created.exit_code, 0, created.output)
        archives = list((Path(self.app.config["DATA_DIR"]) / "backups").glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as archive:
            self.assertIn("app.db", archive.namelist())
            self.assertIn("uploads/proof.txt", archive.namelist())

        guarded = runner.invoke(args=["restore-backup", archives[0].name])
        self.assertNotEqual(guarded.exit_code, 0)
        self.assertIn("--confirm", guarded.output)

    def test_backup_retention_keeps_seven_daily_and_four_weekly(self):
        runner = self.app.test_cli_runner()
        for _ in range(8):
            result = runner.invoke(args=["create-backup", "--kind", "daily"])
            self.assertEqual(result.exit_code, 0, result.output)
        for _ in range(5):
            result = runner.invoke(args=["create-backup", "--kind", "weekly"])
            self.assertEqual(result.exit_code, 0, result.output)
        backup_dir = Path(self.app.config["DATA_DIR"]) / "backups"
        self.assertEqual(len(list(backup_dir.glob("daily-*.zip"))), 7)
        self.assertEqual(len(list(backup_dir.glob("weekly-*.zip"))), 4)

    def test_admin_can_create_and_download_backup_but_student_cannot(self):
        self.register()
        self.login()
        self.assertEqual(self.client.post("/admin/backups").status_code, 403)
        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.commit()
        self.client.post("/logout")
        self.login()
        self.assertEqual(self.client.post("/admin/backups").status_code, 302)
        with self.db() as db:
            filename = db.execute(
                "SELECT filename FROM backup_records ORDER BY id DESC"
            ).fetchone()[0]
        response = self.client.get(f"/admin/backups/{filename}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Disposition"].split(";")[0], "attachment")
        response.close()

    def test_confirmed_restore_replaces_database_with_snapshot(self):
        self.register()
        runner = self.app.test_cli_runner()
        created = runner.invoke(args=["create-backup"])
        self.assertEqual(created.exit_code, 0, created.output)
        archive = next((Path(self.app.config["DATA_DIR"]) / "backups").glob("manual-*.zip"))
        with self.db() as db:
            db.execute(
                "INSERT INTO users(username,password_hash,name,student_no,grade,class_name) "
                "VALUES('later','hash','Later','S999','2024级','测试班')"
            )
            db.commit()

        restored = runner.invoke(args=["restore-backup", archive.name, "--confirm"])
        self.assertEqual(restored.exit_code, 0, restored.output)
        with self.db() as db:
            self.assertIsNone(
                db.execute("SELECT id FROM users WHERE username='later'").fetchone()
            )

    def test_only_admin_can_add_moderation_rules(self):
        self.register()
        self.login()
        data = {"pattern": "代写", "severity": "review", "note": "疑似违规服务"}
        self.assertEqual(self.client.post("/admin/moderation-rules", data=data).status_code, 403)
        with self.db() as db:
            db.execute("UPDATE users SET role='owner' WHERE username='alice'")
            db.commit()
        self.client.post("/logout")
        self.login()
        self.assertEqual(self.client.post("/admin/moderation-rules", data=data).status_code, 302)
        with self.db() as db:
            rule = db.execute(
                "SELECT severity,note FROM moderation_rules WHERE pattern='代写'"
            ).fetchone()
            logged = db.execute(
                "SELECT 1 FROM audit_logs WHERE action='moderation_rule_add'"
            ).fetchone()
        self.assertEqual(tuple(rule), ("review", "疑似违规服务"))
        self.assertIsNotNone(logged)


if __name__ == "__main__":
    unittest.main()
