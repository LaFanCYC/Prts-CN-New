"""Seed test data via HTTP requests against the running Flask app.

Usage:
    python scripts/seed_test_data.py --users 80 --base-url http://127.0.0.1:5000

Requires: requests (pip install requests)
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PASSWORD = "Test1234"
REQUEST_TIMEOUT = 10
MAX_POSTS = 600
MAX_RETRIES = 1

SECTIONS = {
    "study": "学习问答",
    "resource": "资源交流",
    "campus": "校园生活",
    "lost_found": "失物招领",
    "feedback": "建议反馈",
}

GRADES = ["2024级", "2025级", "2026级"]
CLASSES = [str(i) for i in range(1, 9)]

# ---------------------------------------------------------------------------
# Chinese name pool (100 names)
# ---------------------------------------------------------------------------

NAMES = [
    "张伟", "王芳", "李娜", "刘洋", "陈静", "杨敏", "赵磊", "黄丽", "周强", "吴婷",
    "徐明", "孙洁", "胡波", "朱慧", "高翔", "林雨", "何涛", "郭雪", "马超", "罗琳",
    "梁宇", "宋佳", "郑辉", "谢娟", "韩勇", "唐艳", "冯志", "董琳", "程浩", "曹萌",
    "袁海", "邓梅", "许峰", "傅蓉", "沈刚", "曾岚", "彭博", "吕晴", "苏哲", "卢瑶",
    "蒋锐", "蔡颖", "贾华", "丁健", "魏青", "薛晨", "叶阳", "阎露", "余亮", "潘菲",
    "杜婷", "戴峰", "夏雪", "钟杰", "汪莉", "田磊", "任舒", "姜晨", "范逸", "方慧",
    "石鹏", "姚悦", "谭军", "廖文", "邹浩", "熊莉", "金义", "陆洁", "郝龙", "孔怡",
    "白宇", "崔菁", "康峰", "毛悦", "邱鹏", "秦雯", "江涛", "史岚", "顾斌", "侯薇",
    "邵杰", "孟颖", "龙武", "万晴", "段飞", "雷虹", "钱浩", "汤婷", "尹磊", "黎瑞",
    "易康", "常菲", "武哲", "乔婉", "贺云", "赖峰", "龚霞", "文旭", "兰梅", "辛伟",
]

# ---------------------------------------------------------------------------
# Post templates (30: 6 sections x 5)
# ---------------------------------------------------------------------------

POST_TEMPLATES = [
    # ---- study ----
    {
        "title": "求一份高二数学期末复习笔记",
        "body": "马上期末了，数学一直是我的弱项。有没有整理得比较全的复习笔记分享一下？最好是带例题解析的那种，函数和解析几何部分尤其需要。",
        "section": "study",
        "tags": ["数学", "复习笔记", "高二"],
    },
    {
        "title": "如何高效背诵英语单词？分享一下我的方法",
        "body": "最近试了艾宾浩斯遗忘曲线背单词，每天早晚各花15分钟，坚持了一个月效果很明显。配合百词斩APP刷题，大家还有别的技巧吗？",
        "section": "study",
        "tags": ["英语", "背单词", "学习方法"],
    },
    {
        "title": "推荐几本好用的物理竞赛辅导书",
        "body": "准备参加物理竞赛，现在手头只有一本程稼夫的力学。想问问学长学姐有没有其他推荐，最好是电磁学和热学方面的入门书。",
        "section": "study",
        "tags": ["物理竞赛", "辅导书", "推荐"],
    },
    {
        "title": "化学方程式配平有什么诀窍吗",
        "body": "每次看到复杂的氧化还原反应方程式就头疼，氧化数法老是配不平。有没有大佬分享一下配平的经验和技巧？感激不尽。",
        "section": "study",
        "tags": ["化学", "配平", "求助"],
    },
    {
        "title": "分享一个超好用的语文作文素材库",
        "body": "整理了一个作文素材库，按主题分类（励志、思辨、创新、家国情怀等），每个主题配3-5个典故和名言。需要的同学留言我发链接。",
        "section": "study",
        "tags": ["语文", "作文素材", "分享"],
    },

    # ---- resource ----
    {
        "title": "出一套九成新的《高中必刷题》数学必修一",
        "body": "上学期买的，只做了前两章，大部分是空白。书况良好无折痕，原价45现价20出，有意者私聊。",
        "section": "resource",
        "tags": ["二手", "教辅", "数学"],
    },
    {
        "title": "求借一台便携式电子辞典",
        "body": "最近准备托福，需要一台电子辞典查词用。借一个月左右，保证完好归还，可以付押金。有闲置的同学请联系我。",
        "section": "resource",
        "tags": ["借", "电子辞典", "英语"],
    },
    {
        "title": "免费赠送高中历史全套笔记",
        "body": "高三毕业了，笔记用不上了。手写整理的，字迹工整，按课本章节编排。需要的学弟学妹直接拿走，先到先得。",
        "section": "resource",
        "tags": ["赠送", "历史笔记", "高三"],
    },
    {
        "title": "有没有人会修耳机？左耳没声音了",
        "body": "Sony WH-1000XM3左耳突然没声音了，可能是线断了。有没有懂维修的同学帮忙看看？可以请喝奶茶答谢。",
        "section": "resource",
        "tags": ["维修", "耳机", "求助"],
    },
    {
        "title": "用一本《三体》交换一本《活着》",
        "body": "刚看完三体全集，想换一本余华的活着看看。书况基本全新，有书签夹在里面。只换不卖，有感兴趣的吗？",
        "section": "resource",
        "tags": ["交换", "小说", "课外书"],
    },

    # ---- campus ----
    {
        "title": "食堂二楼新开的麻辣烫怎么样？",
        "body": "听说食堂二楼新开了一家麻辣烫窗口，有去过的同学说说体验吗？价格合理吗？排队要多久？",
        "section": "campus",
        "tags": ["食堂", "麻辣烫", "测评"],
    },
    {
        "title": "操场晚上跑步组队，有一起的吗",
        "body": "想每天晚上9点半去操场跑5圈，一个人坚持不下来，找两个跑友互相监督。配速5分半左右，不要求速度，坚持就行。",
        "section": "campus",
        "tags": ["跑步", "组队", "运动"],
    },
    {
        "title": "周六下午篮球场有人约吗",
        "body": "这个周六下午3点篮球场有空场，已经约了4个人，还差2个打3v3。水平不限，来就玩。",
        "section": "campus",
        "tags": ["篮球", "约球", "周末"],
    },
    {
        "title": "图书馆四楼的空调好像坏了",
        "body": "今天下午去图书馆四楼自习，热得不行。空调出风口有风但不制冷。有工作人员看到麻烦报修一下。",
        "section": "campus",
        "tags": ["图书馆", "报修", "空调"],
    },
    {
        "title": "分享一张昨天拍的校园晚霞",
        "body": "昨天傍晚从教学楼天台拍的，夕阳透过云层洒在操场上，颜色绝美。可惜手机拍不出十分之一的震撼，大家有机会一定要去看看。",
        "section": "campus",
        "tags": ["摄影", "晚霞", "校园风景"],
    },

    # ---- lost_found ----
    {
        "title": "捡到一个黑色水杯，请失主认领",
        "body": "在操场看台第三排捡到一个黑色保温杯，品牌是膳魔师，杯身有点划痕。请失主联系我描述具体特征认领。",
        "section": "lost_found",
        "tags": ["失物招领", "水杯", "操场"],
    },
    {
        "title": "U盘丢了，里面有重要文件",
        "body": "上周五在机房上课时忘拔了，是一个银色金士顿32G U盘，上面贴了我的名字缩写。里面的作业文件对我很重要，捡到的同学必有重谢。",
        "section": "lost_found",
        "tags": ["丢失", "U盘", "机房"],
    },
    {
        "title": "在食堂捡到一张校园卡",
        "body": "食堂一楼靠窗位置捡到的，卡号末尾是3721。已经交到教务处失物招领箱了，失主可以去那里取。",
        "section": "lost_found",
        "tags": ["失物招领", "校园卡", "食堂"],
    },
    {
        "title": "钥匙串落在篮球场了",
        "body": "昨天下午打篮球的时候挂在篮架上的，一串有三把钥匙和一个小挂件。挂件是一个小黄人，很好认。有看到的同学麻烦联系我。",
        "section": "lost_found",
        "tags": ["丢失", "钥匙", "篮球场"],
    },
    {
        "title": "在校门口捡到一个钱包",
        "body": "黑色皮质钱包，里面有一些现金和一张照片。请失主联系我说明钱包内物品特征，核实后归还。",
        "section": "lost_found",
        "tags": ["失物招领", "钱包", "校门口"],
    },

    # ---- feedback ----
    {
        "title": "建议学校增加自习室的开放时间",
        "body": "目前自习室晚上10点就关了，高三复习经常需要更长时间。建议延长到11点半，或者至少保留一间通宵自习室。",
        "section": "feedback",
        "tags": ["建议", "自习室", "开放时间"],
    },
    {
        "title": "校园WiFi经常断连，能否优化一下",
        "body": "教学楼三楼和四楼的WiFi信号特别差，经常连不上或者突然断开。上课用平板记笔记的时候很受影响，希望网络中心能检查一下。",
        "section": "feedback",
        "tags": ["网络", "WiFi", "建议"],
    },
    {
        "title": "希望食堂增加更多素菜选择",
        "body": "食堂现在的菜品种类偏少，尤其是素菜基本就那几样。建议每周轮换菜单，增加一些清淡菜式，照顾口味不同的同学。",
        "section": "feedback",
        "tags": ["食堂", "菜品", "建议"],
    },
    {
        "title": "社团活动场地申请流程太繁琐了",
        "body": "现在申请社团活动场地需要跑三个办公室盖章，整个流程走下来至少三天。建议简化为一站式线上审批，提高效率。",
        "section": "feedback",
        "tags": ["社团", "场地申请", "流程优化"],
    },
    {
        "title": "自行车棚建议加装监控摄像头",
        "body": "最近有同学反映自行车被偷或者被挪位置，车棚没有监控很难追溯。建议学校在车棚区域安装监控，保障财产安全。",
        "section": "feedback",
        "tags": ["安全", "监控", "自行车棚"],
    },
]

# ---------------------------------------------------------------------------
# Comment templates (30)
# ---------------------------------------------------------------------------

COMMENT_TEMPLATES = [
    "帮顶！",
    "同求，我也需要。",
    "写得好详细，感谢分享！",
    "请问还有吗？我想要。",
    "楼主好人，一生平安。",
    "已私聊，加个联系方式？",
    "这个确实不错，收藏了。",
    "表示赞同，深有同感。",
    "我也遇到过同样的问题。",
    "求指教，完全看不懂。",
    "大佬牛啊，膜拜。",
    "建议加精，写得很好。",
    "能再详细一点吗？不太明白。",
    "价格能再优惠一点吗？",
    "已经解决了，谢谢大家。",
    "今天刚遇到，太及时了。",
    "帮你转发一下。",
    "楼主在哪个班？可以当面说。",
    "有没有大佬解释一下原理？",
    "笑死我了哈哈哈哈。",
    "这个确实是个问题，支持。",
    "我有个更好的方法，私信聊。",
    "不用谢，应该的。",
    "说得太对了，给你点赞。",
    "下次组队叫上我！",
    "已经找到了，谢谢楼主。",
    "可惜我来晚了。",
    "期待后续更新。",
    "礼貌问价。",
    "同学校友路过。",
]

# ---------------------------------------------------------------------------
# Resource / Lost-Found templates
# ---------------------------------------------------------------------------

RESOURCE_TEMPLATES = [
    {"name": "《高等数学》第七版上下册", "category": "教材书籍", "condition_level": "九成新", "transfer_mode": "borrow", "description": "去年买的，只翻了几页。适合想提前学习高数的同学借阅。可以借一个月。"},
    {"name": "STM32开发板（正点原子）", "category": "电子设备", "condition_level": "七成新", "transfer_mode": "exchange", "description": "学完了不需要了，想换一本Python编程书。板子功能完好，配LCD屏和下载器。"},
    {"name": "羽毛球拍一副（尤尼克斯）", "category": "文体用品", "condition_level": "九成新", "transfer_mode": "borrow", "description": "买来没用几次，手感很好。周末打球可以借，平时不用的时候闲置着。"},
    {"name": "高一数学全套手写笔记", "category": "学习资料", "condition_level": "明显使用痕迹", "transfer_mode": "gift", "description": "高三毕业了，笔记很详细，每个知识点都有例题。免费送给需要的学弟学妹。"},
    {"name": "Python编程辅导", "category": "技能服务", "condition_level": "不适用", "transfer_mode": "free_help", "description": "我学Python两年多了，可以免费辅导入门，帮你迈过前几个坑。每周日下午2小时。"},
    {"name": "《三体》三部曲全集", "category": "教材书籍", "condition_level": "九成新", "transfer_mode": "exchange", "description": "看完了想换《银河帝国》系列，或者其它科幻小说也行。书况很好没有折痕。"},
    {"name": "机械键盘（红轴）", "category": "电子设备", "condition_level": "七成新", "transfer_mode": "borrow", "description": "写代码用的红轴键盘，打字手感很好。最近换了新键盘，这个可以短期借给需要的同学。"},
    {"name": "高中化学实验总结", "category": "学习资料", "condition_level": "九成新", "transfer_mode": "gift", "description": "按教材章节整理了所有实验的操作步骤、现象和注意事项。考前复习神器。"},
    {"name": "篮球（斯伯丁）", "category": "文体用品", "condition_level": "明显使用痕迹", "transfer_mode": "borrow", "description": "经常用的篮球，气很足手感好。平时放在体育馆储物柜，打球的时候可以借。"},
    {"name": "Photoshop基础教学", "category": "技能服务", "condition_level": "不适用", "transfer_mode": "skill_exchange", "description": "我可以教PS基础（抠图、调色、合成），想换一个教我视频剪辑的同学。"},
    {"name": "英语四六级词汇书", "category": "教材书籍", "condition_level": "全新", "transfer_mode": "gift", "description": "买重了，全新未拆封。谁需要直接拿走。"},
    {"name": "二手自行车（26寸）", "category": "其他", "condition_level": "明显使用痕迹", "transfer_mode": "exchange", "description": "毕业了带不走，换一个蓝牙音箱或者移动电源。车况良好，刚换的新胎。"},
    {"name": "Kindle电子书阅读器", "category": "电子设备", "condition_level": "九成新", "transfer_mode": "borrow", "description": "买了平板以后Kindle基本不用了，可以长期借出去。不伤眼，看小说和PDF都很方便。"},
    {"name": "高中生物思维导图", "category": "学习资料", "condition_level": "全新", "transfer_mode": "gift", "description": "自己做了全套生物必修和选修的思维导图，打印出来厚厚一沓。送给需要的同学。"},
    {"name": "吉他入门教学", "category": "技能服务", "condition_level": "不适用", "transfer_mode": "free_help", "description": "弹吉他三年了，可以免费教入门和弦和简单弹唱。有自己的吉他可以带过来一起练。"},
]

LOST_TEMPLATES = [
    {"title": "丢失一副黑色蓝牙耳机", "description": "昨天下午在操场跑步时掉的，耳机仓是黑色的，品牌是漫步者。有看到或捡到的同学请联系我。"},
    {"title": "校服外套落在体育馆了", "description": "前天体育课结束忘了拿，蓝色校服外套，内侧口袋里有一个学生证。体育馆二楼更衣室附近。"},
    {"title": "数学练习册不见了", "description": "周五下午最后一节课放在抽屉里忘拿了，是一本蓝色的《高中数学必刷题》选修2-1。1101教室。"},
    {"title": "眼镜丢了，黑色半框", "description": "在教学楼到食堂的路上丢失，黑色半框近视眼镜，度数比较高。没有眼镜上课很困难，请捡到的同学务必联系我。"},
    {"title": "手表掉在实验室了", "description": "下午做物理实验时摘下来放在实验台上，走的时候忘了拿。一块卡西欧的电子手表，表带是黑色的。化学实验室三楼。"},
]

FOUND_TEMPLATES = [
    {"title": "捡到一本笔记本", "description": "在校门口花坛边捡到的，硬壳横线本，封面写着化学。已经放在传达室，失主可以去取。"},
    {"title": "教学楼捡到一个充电宝", "description": "教学楼一楼走廊捡到的白色小米充电宝，电量还满着。我在2105教室，失主可以来找我拿。"},
    {"title": "捡到一把雨伞", "description": "下雨天在图书馆门口捡到的，深蓝色长柄伞。放在图书馆前台了，请失主去认领。"},
    {"title": "食堂捡到一副耳机", "description": "食堂二楼靠窗座位捡到的，白色的有线耳机，插头是L型的。已经放在食堂失物招领处。"},
    {"title": "捡到一个文具盒", "description": "在1103教室午休时发现桌上有个透明文具盒，里面有几支笔和一把尺子。我在后排，失主可以来拿。"},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_csrf(sess, base_url):
    """Get CSRF token. Tries / first (logged-in users), falls back to /register."""
    for path in ("/", "/register"):
        resp = sess.get(base_url + path, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        if "csrf_token" in resp.text:
            return _extract_csrf(resp.text)
    raise RuntimeError("CSRF token not found in any page")


def _extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not match:
        raise RuntimeError("CSRF token not found in HTML response")
    return match.group(1)

def _powerlaw(rate: float) -> int:
    """Draw from exponential distribution, max 20."""
    return min(int(random.expovariate(rate)), 20)

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class Stats:
    users: int = 0
    registered: int = 0
    skipped: int = 0
    logged_in: int = 0
    posts: int = 0
    resources: int = 0
    lost_found: int = 0
    comments: int = 0
    reactions: int = 0

class SeedDataRunner:
    def __init__(self, base_url: str, num_users: int, seed: int = 42) -> None:
        self.base_url = base_url.rstrip("/")
        self.num_users = num_users
        self.stats = Stats()
        self.credentials: list[dict[str, str]] = []
        self.sessions: dict[int, requests.Session] = {}
        self.post_ids: list[int] = []
        random.seed(seed)

    # ---- Phase 1: Register ----

    def _generate_users(self) -> list[dict[str, str]]:
        users: list[dict[str, str]] = []
        used_names: set[str] = set()
        available = list(NAMES)
        random.shuffle(available)
        for i in range(self.num_users):
            name = available[i % len(available)]
            username = f"test_{i + 1:03d}"
            if username in used_names:
                username = f"test_u{i + 1:03d}"
            used_names.add(username)
            student_no = f"20{24 + (i % 3)}01{i % 8 + 1:02d}{i % 10}"
            users.append({
                "username": username,
                "name": name,
                "student_no": student_no,
                "grade": GRADES[i % 3],
                "class_name": CLASSES[i % 8],
            })
        random.shuffle(users)
        return users

    def register(self) -> None:
        print("[1/4] 注册用户...")
        users = self._generate_users()
        for idx, user in enumerate(users):
            try:
                sess = requests.Session()
                csrf = _get_csrf(sess, self.base_url)
            except Exception:
                print(f"  [WARN] Cannot reach server, aborting.")
                sys.exit(1)

            resp = sess.post(
                f"{self.base_url}/register",
                data={
                    "csrf_token": csrf,
                    "username": user["username"],
                    "name": user["name"],
                    "student_no": user["student_no"],
                    "grade": user["grade"],
                    "class_name": user["class_name"],
                    "password": PASSWORD,
                    "password_confirm": PASSWORD,
                },
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (302, 200):
                user["password"] = PASSWORD
                self.credentials.append(user)
                self.stats.registered += 1
            elif resp.status_code == 400 and "已存在" in resp.text:
                user["password"] = PASSWORD
                self.credentials.append(user)
                self.stats.skipped += 1
            else:
                print(f"  [WARN] Register {user['username']}: HTTP {resp.status_code}")

            if (idx + 1) % 10 == 0:
                print(f"  ... {idx + 1}/{self.num_users}")
        self.stats.users = len(self.credentials)
        print(f"  {self.stats.registered}/{self.num_users} 完成 (跳过 {self.stats.skipped})")

    # ---- Phase 2: Login ----

    def login_all(self) -> None:
        print("[2/4] 登录...")
        for idx, cred in enumerate(self.credentials):
            sess = requests.Session()
            csrf = _get_csrf(sess, self.base_url)
            resp = sess.post(
                f"{self.base_url}/login",
                data={
                    "csrf_token": csrf,
                    "username": cred["username"],
                    "password": PASSWORD,
                },
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (302, 200):
                self.stats.logged_in += 1
                self.sessions[idx] = sess
            else:
                ok = False
                for _ in range(MAX_RETRIES):
                    time.sleep(0.5)
                    sess2 = requests.Session()
                    csrf2 = _get_csrf(sess2, self.base_url)
                    resp2 = sess2.post(
                        f"{self.base_url}/login",
                        data={
                            "csrf_token": csrf2,
                            "username": cred["username"],
                            "password": PASSWORD,
                        },
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp2.status_code in (302, 200):
                        self.stats.logged_in += 1
                        self.sessions[idx] = sess2
                        ok = True
                        break
                if not ok:
                    print(f"  [WARN] Login failed for {cred['username']}")
        print(f"  {self.stats.logged_in}/{self.stats.users} 完成")

    # ---- Phase 3: Create posts ----

    def create_posts(self) -> None:
        print("[3/4] 发布内容...")
        session_ids = list(self.sessions.keys())
        random.shuffle(session_ids)
        section_keys = list(SECTIONS)

        # Random posts per user
        for sid in session_ids:
            n = random.randint(0, 10)
            for _ in range(n):
                if self.stats.posts >= MAX_POSTS:
                    break
                sess = self.sessions[sid]
                template = random.choice(POST_TEMPLATES)
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    resp = sess.post(
                        f"{self.base_url}/community/new",
                        data={
                            "csrf_token": csrf,
                            "title": template["title"],
                            "body": template["body"],
                            "section": template["section"],
                            "tags": ",".join(template["tags"]),
                        },
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp.status_code in (302, 200):
                        loc = resp.headers.get("Location", "")
                        m = re.search(r"/community/(\d+)", loc)
                        if m:
                            self.post_ids.append(int(m.group(1)))
                            self.stats.posts += 1
                except Exception:
                    continue
            if self.stats.posts >= MAX_POSTS:
                break

        # Fill remaining to balance sections
        while self.stats.posts < MAX_POSTS:
            for sec in section_keys:
                if self.stats.posts >= MAX_POSTS:
                    break
                matching = [t for t in POST_TEMPLATES if t["section"] == sec]
                if not matching:
                    continue
                sid = random.choice(session_ids)
                sess = self.sessions[sid]
                template = random.choice(matching)
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    resp = sess.post(
                        f"{self.base_url}/community/new",
                        data={
                            "csrf_token": csrf,
                            "title": template["title"],
                            "body": template["body"],
                            "section": template["section"],
                            "tags": ",".join(template["tags"]),
                        },
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp.status_code in (302, 200):
                        loc = resp.headers.get("Location", "")
                        m = re.search(r"/community/(\d+)", loc)
                        if m:
                            self.post_ids.append(int(m.group(1)))
                            self.stats.posts += 1
                except Exception:
                    continue

        # ---- Resources ----
        for tmpl in RESOURCE_TEMPLATES:
            sid = random.choice(session_ids)
            sess = self.sessions[sid]
            try:
                csrf = _get_csrf(sess, self.base_url)
                resp = sess.post(
                    f"{self.base_url}/resources/new",
                    data={
                        "csrf_token": csrf,
                        "name": tmpl["name"],
                        "category": tmpl["category"],
                        "condition_level": tmpl["condition_level"],
                        "transfer_mode": tmpl.get("transfer_mode", "borrow"),
                        "description": tmpl["description"],
                        "keywords": tmpl["category"],
                    },
                    allow_redirects=False,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code in (302, 200):
                    self.stats.resources += 1
            except Exception:
                continue

        # ---- Lost items ----
        for tmpl in LOST_TEMPLATES:
            sid = random.choice(session_ids)
            sess = self.sessions[sid]
            try:
                csrf = _get_csrf(sess, self.base_url)
                resp = sess.post(
                    f"{self.base_url}/lost-found/new/lost",
                    data={
                        "csrf_token": csrf,
                        "title": tmpl["title"],
                        "description": tmpl["description"],
                        "occurred_on": (date.today() - timedelta(days=random.randint(1, 30))).isoformat(),
                        "location": random.choice(["操场", "教学楼", "食堂", "图书馆", "体育馆", "宿舍"]),
                        "keywords": ",".join(tmpl["title"][:20].split()),
                    },
                    allow_redirects=False,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code in (302, 200):
                    self.stats.lost_found += 1
            except Exception:
                continue

        # ---- Found items ----
        for tmpl in FOUND_TEMPLATES:
            sid = random.choice(session_ids)
            sess = self.sessions[sid]
            try:
                csrf = _get_csrf(sess, self.base_url)
                resp = sess.post(
                    f"{self.base_url}/lost-found/new/found",
                    data={
                        "csrf_token": csrf,
                        "title": tmpl["title"],
                        "description": tmpl["description"],
                        "occurred_on": (date.today() - timedelta(days=random.randint(1, 30))).isoformat(),
                        "location": random.choice(["操场", "教学楼", "食堂", "图书馆", "体育馆", "宿舍"]),
                        "keywords": ",".join(tmpl["title"][:20].split()),
                    },
                    allow_redirects=False,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code in (302, 200):
                    self.stats.lost_found += 1
            except Exception:
                continue

        print(f"  社区 {self.stats.posts} | 资源 {self.stats.resources} | 失物 {self.stats.lost_found}")

    # ---- Phase 4: Interactions ----

    def add_interactions(self) -> None:
        print("[4/4] 互动...")
        if not self.post_ids or len(self.sessions) < 2:
            print("  跳过（帖子或用户不足）")
            return
        session_ids = list(self.sessions.keys())

        # Power-law heat: few hot posts, most quiet
        post_heats = [(pid, _powerlaw(1 / 3)) for pid in self.post_ids]
        post_heats.sort(key=lambda x: -x[1])

        for pid, heat in post_heats:
            n_comments = 0 if heat == 0 else max(1, _powerlaw(1 / (heat + 1)))
            n_likes = max(0, _powerlaw(1 / (heat + 2)))
            n_favs = 1 if heat > 10 and random.random() < 0.3 else 0
            n_reposts = 1 if heat > 15 and random.random() < 0.15 else 0

            for _ in range(n_comments):
                commenter_sid = random.choice(session_ids)
                sess = self.sessions[commenter_sid]
                body = random.choice(COMMENT_TEMPLATES)
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    resp = sess.post(
                        f"{self.base_url}/comments/post/{pid}",
                        data={"csrf_token": csrf, "body": body},
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp.status_code in (302, 200):
                        self.stats.comments += 1
                except Exception:
                    continue

            for _ in range(n_likes):
                liker_sid = random.choice(session_ids)
                sess = self.sessions[liker_sid]
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    resp = sess.post(
                        f"{self.base_url}/reactions/post/{pid}/like",
                        data={"csrf_token": csrf},
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    if resp.status_code in (302, 200):
                        self.stats.reactions += 1
                except Exception:
                    continue

            for _ in range(n_favs):
                fav_sid = random.choice(session_ids)
                sess = self.sessions[fav_sid]
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    sess.post(
                        f"{self.base_url}/reactions/post/{pid}/favorite",
                        data={"csrf_token": csrf},
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    self.stats.reactions += 1
                except Exception:
                    continue

            for _ in range(n_reposts):
                rp_sid = random.choice(session_ids)
                sess = self.sessions[rp_sid]
                try:
                    csrf = _get_csrf(sess, self.base_url)
                    sess.post(
                        f"{self.base_url}/community/{pid}/repost",
                        data={"csrf_token": csrf, "comment": "好帖，转了！"},
                        allow_redirects=False,
                        timeout=REQUEST_TIMEOUT,
                    )
                    self.stats.reactions += 1
                except Exception:
                    continue

        print(f"  评论 {self.stats.comments} | 互动 {self.stats.reactions}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed test data for Prts-CN-New.")
    parser.add_argument("--users", type=int, default=80, help="Number of test users (default 80)")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Flask server URL")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    print("Prts-CN-New Seed Data Tool")
    print(f"  Server: {args.base_url}")
    print(f"  Users:  {args.users}")
    print(f"  Seed:   {args.seed}")
    print()

    # Quick connectivity check
    try:
        requests.get(f"{args.base_url}/", timeout=5)
    except requests.ConnectionError:
        print("[ERROR] Cannot reach the server. Is `python app.py` running?")
        sys.exit(1)

    runner = SeedDataRunner(args.base_url, args.users, args.seed)
    runner.register()
    if runner.stats.users == 0:
        print("[ERROR] No users registered. Aborting.")
        sys.exit(1)
    runner.login_all()
    if runner.stats.logged_in == 0:
        print("[ERROR] No users logged in. Aborting.")
        sys.exit(1)
    runner.create_posts()
    runner.add_interactions()

    print(f"\n完成。{args.base_url}")

if __name__ == "__main__":
    main()

