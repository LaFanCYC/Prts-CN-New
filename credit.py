"""信用规则、不可变账本与按需结算。"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
MIN_SCORE, MAX_SCORE, BASE_SCORE = 0, 120, 100
DAILY_POSITIVE_LIMIT, WEEKLY_POSITIVE_LIMIT = 2, 6
APPEAL_DAYS = 30
TIERS = (
    (100, "优先", "可正常发布与申请，候选排序优先"),
    (80, "正常", "可正常发布与申请"),
    (60, "靠后", "最多 1 条待审批申请和 1 条进行中流转"),
    (0, "受限", "分数低于 60 不可新申请；低于 40 不可发布"),
)
EVENT_LABELS = {
    "on_time_return": "按时归还", "overdue_return": "逾期未归还", "borrower_termination": "借用方责任终止",
    "skill_completed": "技能服务完成", "skill_no_show": "技能服务爽约", "natural_recovery": "每日信用恢复",
    "admin_adjustment": "管理员调整", "appeal_reversal": "申诉撤销补偿",
}
BEHAVIOR_POSITIVES = {"on_time_return", "skill_completed"}


def china_now(now=None):
    if now is None:
        return datetime.now(TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=TZ)
    return now.astimezone(TZ)


def credit_tier(score):
    score = max(MIN_SCORE, min(MAX_SCORE, int(score)))
    for threshold, name, description in TIERS:
        if score >= threshold:
            return {"name": name, "description": description, "threshold": threshold}


def permission_for_score(score):
    score = int(score)
    return {
        "can_publish": score >= 40,
        "can_apply": score >= 60,
        "limited": 60 <= score < 80,
        "tier": credit_tier(score),
    }


def priority_rank(score):
    return 0 if score >= 100 else 1 if score >= 80 else 2 if score >= 60 else 3


def _stamp(now):
    return china_now(now).strftime("%Y-%m-%d %H:%M:%S")


def _week_start(day):
    return day - timedelta(days=day.weekday())


def _positive_used(db, user_id, now):
    current = china_now(now).date()
    rows = db.execute(
        "SELECT delta,created_at FROM credit_events WHERE user_id=? AND event_type IN ('on_time_return','skill_completed')",
        (user_id,),
    ).fetchall()
    daily = weekly = 0
    week_start = _week_start(current)
    for row in rows:
        event_day = datetime.fromisoformat(row["created_at"]).date()
        if event_day == current:
            daily += max(0, row["delta"])
        if week_start <= event_day <= current:
            weekly += max(0, row["delta"])
    return daily, weekly


def record_event(db, user_id, delta, event_type, reason, *, reference_type="", reference_id=None,
                 actor_id=None, event_key=None, now=None):
    """Write one immutable score event. Duplicate event keys are harmless no-ops."""
    if event_key and db.execute("SELECT 1 FROM credit_events WHERE event_key=?", (event_key,)).fetchone():
        return None
    user = db.execute("SELECT credit_score FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        raise ValueError("user not found")
    requested = int(delta)
    if requested > 0 and event_type in BEHAVIOR_POSITIVES:
        daily, weekly = _positive_used(db, user_id, now)
        requested = min(requested, max(0, DAILY_POSITIVE_LIMIT - daily), max(0, WEEKLY_POSITIVE_LIMIT - weekly))
    score = int(user["credit_score"])
    actual = max(MIN_SCORE, min(MAX_SCORE, score + requested)) - score
    cursor = db.execute(
        "INSERT INTO credit_events(user_id,delta,balance_after,event_type,reference_type,reference_id,reason,actor_id,event_key,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (user_id, actual, score + actual, event_type, reference_type, reference_id, reason, actor_id, event_key, _stamp(now)),
    )
    db.execute("UPDATE users SET credit_score=? WHERE id=?", (score + actual, user_id))
    if actual < 0:
        db.execute("UPDATE users SET credit_recovered_on=? WHERE id=?", (china_now(now).date().isoformat(), user_id))
    return {"id": cursor.lastrowid, "delta": actual, "score": score + actual, "event_type": event_type, "tier_before": credit_tier(score), "tier_after": credit_tier(score + actual)}


def settle_credit(db, user_id, now=None):
    """Apply due overdue milestones and daily recovery when this account is accessed."""
    current = china_now(now)
    today = current.date()
    outcomes = []
    overdue = db.execute(
        "SELECT id,expected_return_date FROM applications WHERE applicant_id=? AND status='borrowed' "
        "AND expected_return_date IS NOT NULL AND expected_return_date < ?",
        (user_id, today.isoformat()),
    ).fetchall()
    for item in overdue:
        days = (today - date.fromisoformat(item["expected_return_date"])).days
        for milestone, total in ((1, -5), (4, -10), (8, -20)):
            if days >= milestone:
                previous = 0 if milestone == 1 else (-5 if milestone == 4 else -10)
                outcome = record_event(
                    db, user_id, total - previous, "overdue_return", f"逾期第 {milestone} 天未归还",
                    reference_type="application", reference_id=item["id"], event_key=f"overdue:{item['id']}:{milestone}", now=current,
                )
                if outcome:
                    outcomes.append(outcome)
    user = db.execute("SELECT credit_score,credit_recovered_on FROM users WHERE id=?", (user_id,)).fetchone()
    if not overdue and user and user["credit_score"] < BASE_SCORE:
        last = date.fromisoformat(user["credit_recovered_on"]) if user["credit_recovered_on"] else today
        days = max(0, (today - last).days)
        if days:
            outcome = record_event(
                db, user_id, min(days, BASE_SCORE - user["credit_score"]), "natural_recovery", "每日信用恢复",
                event_key=f"recovery:{user_id}:{today.isoformat()}", now=current,
            )
            if outcome:
                outcomes.append(outcome)
        db.execute("UPDATE users SET credit_recovered_on=? WHERE id=?", (today.isoformat(), user_id))
    return outcomes


def score_chart(db, user_id, days=30, now=None):
    days = 90 if int(days) == 90 else 30
    end = china_now(now).date()
    start = end - timedelta(days=days - 1)
    events = db.execute(
        "SELECT delta,created_at FROM credit_events WHERE user_id=? AND date(created_at)<=? ORDER BY created_at,id",
        (user_id, end.isoformat()),
    ).fetchall()
    score = BASE_SCORE
    by_day = {}
    for event in events:
        event_day = datetime.fromisoformat(event["created_at"]).date()
        score += event["delta"]
        if event_day >= start:
            by_day[event_day] = score
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day in by_day:
            score = by_day[day]
        result.append({"date": day.isoformat(), "score": score})
    return result
