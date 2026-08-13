from __future__ import annotations

import sqlite3
import json
import csv
import io
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from aimcat import (
    decode_diagnosis,
    diagnosis_for,
    encode_diagnosis,
    preferred_attempt_date,
    rolling_aimcat_trend,
    status_for,
)
from adaptive import (
    coverage_report,
    dilr_performance,
    mastery_score,
    mastery_status,
    normalize_varc_error,
    progression_for,
    resource_effectiveness,
    varc_analysis,
)
from seeds.resource_catalog import STUDY_RESOURCES, USER_RESOURCE_ACCESS
from seeds.aimcat_schedule import AIMCAT_WINDOWS
from seeds.time_foundation_tests import seed_time_foundation_tests
from seeds.topic_resource_mappings import build_topic_mappings

ROOT = Path(__file__).parent
DATA = ROOT / "data"
DB_PATH = DATA / "command-center.db"
MIGRATIONS = ROOT / "migrations"
APP_TIMEZONE = "Asia/Kolkata"
CAT_DATE = "2026-11-29"
PREP_START_DATE = "2026-08-12"
EXAM_DATE = date.fromisoformat(CAT_DATE)

app = FastAPI(title="Northstar MBA Prep OS", version="1.0.0")
UI_DIR = ROOT / "static" / "ui"


@contextmanager
def connection():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def phase_for(day: str) -> str:
    if day <= "2026-08-31": return "Foundation"
    if day <= "2026-09-27": return "Core syllabus + sectionals"
    if day <= "2026-10-25": return "Test strategy"
    if day <= "2026-11-15": return "Mock-heavy / peak building"
    if day <= "2026-11-28": return "Consolidation + taper"
    return "CAT 2026"


def current_app_date() -> date:
    return datetime.now(ZoneInfo(APP_TIMEZONE)).date()


def should_mock(day: str, con: sqlite3.Connection | None = None) -> bool:
    """Scheduled AIMCATs are the only automatically generated full mocks."""
    if con is None:
        return False
    return bool(con.execute(
        """SELECT 1 FROM aimcat_schedules
           WHERE planned_attempt_date=? AND historical=0 AND skipped=0""",
        (day,),
    ).fetchone())


def seed_aimcat_data(con: sqlite3.Connection):
    for test_ref, start_date, end_date in AIMCAT_WINDOWS:
        historical = int(end_date < PREP_START_DATE)
        preferred = preferred_attempt_date(start_date, end_date)
        planned = None if historical else preferred
        con.execute(
            """
            INSERT OR IGNORE INTO aimcat_schedules(
                provider,series,test_ref,start_date,end_date,preferred_attempt_date,
                planned_attempt_date,status,historical
            ) VALUES('TIME','AIMCAT',?,?,?,?,?,?,?)
            """,
            (test_ref, start_date, end_date, preferred, planned, "PAST" if historical else "UPCOMING", historical),
        )
    con.execute(
        "INSERT INTO settings(key,value) VALUES('timePortalUrl','https://www.time4education.com/') ON CONFLICT(key) DO NOTHING"
    )


def seed_time_foundation_data(con: sqlite3.Connection):
    seed_time_foundation_tests(con)
    defaults = {
        "timeFoundationAdvanceAccuracy": "85",
        "timeFoundationContinueAccuracy": "70",
        "timeFoundationConfidence": "4",
        "timeOmetAutoSchedule": "off",
    }
    con.executemany(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING",
        defaults.items(),
    )


TIME_TOPIC_NAMES = {
    "TIME_SPEED_DISTANCE": "Time, speed and distance",
    "TIME_WORK": "Time and work",
    "QUADRATIC_EQUATIONS": "Quadratic equations",
    "INEQUALITIES": "Inequalities",
    "PROGRESSIONS": "Progressions",
    "PERMUTATION_COMBINATION": "Permutations / combinations",
    "PROBABILITY_STATISTICS": "Probability",
}

TIME_GROUP_AREAS = {
    "ARITHMETIC": "Arithmetic",
    "ALGEBRA": "Algebra",
    "NUMBER_SYSTEMS": "Number Systems",
    "GEOMETRY_MENSURATION": "Geometry",
    "MODERN_MATH": "Modern Mathematics",
}

TIME_DILR_CATEGORIES = {
    "Tables": ("TABLES",),
    "Charts": ("LINE_GRAPHS", "BAR_STACK_GRAPHS", "PIE_CHARTS"),
    "Games and tournaments": ("GAMES_TOURNAMENTS",),
    "Routes / networks": ("NETWORKS",),
    "Caselets": ("CASELETS",),
    "Distribution": ("DISTRIBUTION_SELECTION_COMPARISON",),
    "Selection": ("DISTRIBUTION_SELECTION_COMPARISON",),
    "Mixed DI-LR": ("REASONING_BASED_DI",),
}


def time_foundation_enabled(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT enabled FROM user_resource_access WHERE resource_provider='TIME'"
    ).fetchone()
    return bool(row and row["enabled"])


def choose_time_foundation_test(con: sqlite3.Connection, subject: str, topic: str):
    """Choose one relevant CAT-core checkpoint without inventory-completion pressure."""
    if not time_foundation_enabled(con):
        return None
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    allow_optional = settings.get("timeOmetAutoSchedule", "off") == "on"
    subjects = ("QA",) if subject == "Quant" else ("DI", "LR") if subject == "DILR" else ()
    if not subjects:
        return None
    placeholders = ",".join("?" for _ in subjects)
    candidates = con.execute(
        f"""
        SELECT test.*,
               (SELECT attempt.accuracy FROM time_foundation_attempts attempt
                WHERE attempt.test_id=test.id ORDER BY attempt.attempted_on DESC,attempt.id DESC LIMIT 1) AS last_accuracy,
               (SELECT attempt.confidence FROM time_foundation_attempts attempt
                WHERE attempt.test_id=test.id ORDER BY attempt.attempted_on DESC,attempt.id DESC LIMIT 1) AS last_confidence,
               (SELECT COUNT(*) FROM time_foundation_attempts attempt WHERE attempt.test_id=test.id) AS attempt_count
        FROM time_foundation_tests test
        WHERE test.active=1 AND test.subject IN ({placeholders})
          AND (?=1 OR test.cat_core=1)
        """,
        (*subjects, int(allow_optional)),
    ).fetchall()
    if not candidates:
        return None
    advance_accuracy = float(settings.get("timeFoundationAdvanceAccuracy", "85"))
    confidence_gate = int(settings.get("timeFoundationConfidence", "4"))
    remaining = [
        row for row in candidates
        if row["last_accuracy"] is None
        or float(row["last_accuracy"]) < advance_accuracy
        or int(row["last_confidence"] or 0) < confidence_gate
    ]
    if remaining:
        candidates = remaining
    topic_row = con.execute(
        "SELECT area FROM topics WHERE subject=? AND LOWER(name)=LOWER(?) LIMIT 1",
        (subject, topic),
    ).fetchone()
    wanted_area = topic_row["area"] if topic_row else None
    wanted_categories = TIME_DILR_CATEGORIES.get(topic, ())
    recent_categories = {
        row["category"]
        for row in con.execute(
            """
            SELECT test.category FROM tasks task
            JOIN time_foundation_tests test ON test.id=task.time_foundation_test_id
            WHERE task.archived=0 AND task.time_foundation_test_id IS NOT NULL
            ORDER BY task.date DESC,task.id DESC LIMIT 2
            """
        ).fetchall()
    }
    category_order = {
        "REASONING_BASED_DI": 0, "DISTRIBUTION_SELECTION_COMPARISON": 1,
        "GAMES_TOURNAMENTS": 2, "CASELETS": 3, "NETWORKS": 4,
        "TABLES": 5, "LINE_GRAPHS": 6, "BAR_STACK_GRAPHS": 7, "PIE_CHARTS": 8,
    }

    def score(row):
        exact_name = TIME_TOPIC_NAMES.get(row["canonical_topic"])
        exact = int(bool(exact_name and exact_name.lower() == topic.lower()))
        group_area = TIME_GROUP_AREAS.get(row["canonical_topic_group"])
        group = int(bool(wanted_area and group_area == wanted_area))
        category = int(row["category"] in wanted_categories)
        unattempted = int(not row["attempt_count"])
        needs_retest = int(row["last_accuracy"] is not None and float(row["last_accuracy"]) < 70)
        fresh_category = int(row["category"] not in recent_categories)
        priority = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}[row["cat_priority"]]
        rotation = -category_order.get(row["category"], 50)
        return (exact, category, group, needs_retest, unattempted, fresh_category, priority, rotation, -row["id"])

    return max(candidates, key=score)


def attach_time_foundation_checkpoint(con: sqlite3.Connection, day: str, planned: list[dict[str, Any]], days_to_mock: int | None):
    """Use Foundation tests as occasional August checkpoints after normal learning/practice."""
    parsed = date.fromisoformat(day)
    if not (PREP_START_DATE < day <= "2026-08-31") or parsed.weekday() != 2:
        return
    if days_to_mock is not None and days_to_mock <= 3:
        return
    checkpoint_subject = "Quant" if (parsed.day // 7) % 2 == 0 else "DILR"
    block = next((item for item in planned if item["subject"] == checkpoint_subject), None)
    if not block or block.get("kind") != "practice":
        return
    selected = choose_time_foundation_test(con, checkpoint_subject, block["topic"])
    if not selected:
        return
    block["time_foundation_test_id"] = selected["id"]
    reason = f"Exact T.I.M.E. checkpoint · {selected['test_reference']} · {selected['cat_priority']} CAT priority"
    block["adaptive_reason"] = f"{block.get('adaptive_reason')} · {reason}" if block.get("adaptive_reason") else reason


def aimcat_on(con: sqlite3.Connection, day: str):
    return con.execute(
        """SELECT * FROM aimcat_schedules
           WHERE planned_attempt_date=? AND skipped=0
             AND (historical=0 OR converted_to_additional=1)
           ORDER BY id LIMIT 1""",
        (day,),
    ).fetchone()


def next_aimcat(con: sqlite3.Connection, day: str):
    return con.execute(
        """SELECT * FROM aimcat_schedules
           WHERE skipped=0 AND actual_attempt_date IS NULL
             AND (historical=0 OR converted_to_additional=1)
             AND COALESCE(planned_attempt_date,end_date)>=?
           ORDER BY COALESCE(planned_attempt_date,end_date),id LIMIT 1""",
        (day,),
    ).fetchone()


def shifted_times(start: str, durations: list[int]) -> list[str]:
    hour, minute = map(int, start.split(":"))
    cursor = hour * 60 + minute
    result = []
    for duration in durations:
        result.append(f"{cursor // 60 % 24:02d}:{cursor % 60:02d}")
        cursor += duration
    return result


def topic_priority(topic: sqlite3.Row, today: str) -> float:
    mastery = (5 - topic["confidence"]) * 8
    accuracy = max(0, 80 - topic["accuracy"]) * .45
    due = 24 if topic["next_revision"] and topic["next_revision"] <= today else 0
    unfinished = 12 if topic["status"] == "Not Started" else 8 if topic["status"] == "Learning" else 0
    recency = 12
    if topic["last_practised"]:
        recency = min(12, (date.fromisoformat(today) - date.fromisoformat(topic["last_practised"])).days)
    pressure = topic["adaptive_pressure"] if "adaptive_pressure" in topic.keys() else 0
    return topic["importance"] * 7 + mastery + accuracy + due + unfinished + recency + pressure


def topics_with_signals(con: sqlite3.Connection, subject: str):
    return con.execute(
        """
        SELECT t.*,COALESCE((
            SELECT SUM(signal.weight) FROM adaptive_signals signal
            WHERE signal.topic_id=t.id AND signal.resolved_at IS NULL
        ),0) AS adaptive_pressure
        FROM topics t WHERE t.subject=?
        """,
        (subject,),
    ).fetchall()


def choose_dilr_topic(con: sqlite3.Connection, day: str):
    topic_rows = topics_with_signals(con, "DILR")
    if not topic_rows:
        return None
    offset = max(0, (date.fromisoformat(day) - date.fromisoformat(PREP_START_DATE)).days)
    # Alternate a weak/signal-driven category with a normal rotation to avoid single-category overload.
    if offset % 2:
        measured = [row for row in topic_rows if row["attempted"] or row["adaptive_pressure"]]
        if measured:
            return max(measured, key=lambda row: topic_priority(row, day))
    return topic_rows[offset % len(topic_rows)]


def plan_rows(con: sqlite3.Connection, day: str) -> list[dict[str, Any]]:
    start = row_map(con.execute("SELECT key,value FROM settings").fetchall()).get("studyStart", "18:00")
    scheduled = aimcat_on(con, day)
    if scheduled:
        times = shifted_times(start, [120, 180, 60])
        lifecycle = [
            task(day, times[0], 120, "Mock", scheduled["test_ref"], scheduled["test_ref"], "Take the scheduled T.I.M.E. AIMCAT under CAT conditions. Selection is a scored skill.", "T.I.M.E. AIMCAT portal", 1, 0, "Critical", "mock"),
            task(day, times[1], 180, "Analysis", scheduled["test_ref"], f"Analyse {scheduled['test_ref']}", "Classify A–G; isolate D/E/F losses, easy misses, time waste and section strategy.", "T.I.M.E. solutions + error log", 0, 0, "Critical", "analysis"),
            task(day, times[2], 60, "Revision", scheduled["test_ref"], f"Re-solve {scheduled['test_ref']} errors", "Retry important errors without solutions and write only transferable lessons.", "Error log + T.I.M.E. solutions", 0, 80, "High", "revision"),
        ]
        for item in lifecycle:
            item["aimcat_schedule_id"] = scheduled["id"]
            item["adaptive_reason"] = f"Priority A scheduled AIMCAT · official window {scheduled['start_date']} to {scheduled['end_date']}"
        return lifecycle
    topics = topics_with_signals(con, "Quant")
    topics = [topic for topic in topics if topic["status"] != "Strong" or (topic["next_revision"] and topic["next_revision"] <= day)]
    topics.sort(key=lambda item: topic_priority(item, day), reverse=True)
    quant = topics[0] if topics else {"name": "Percentages", "source": "IMS module + CAT PYQs"}
    durations = [135, 105, 90, 30]
    upcoming = next_aimcat(con, day)
    days_to_mock = None
    if upcoming and upcoming["planned_attempt_date"]:
        days_to_mock = (date.fromisoformat(upcoming["planned_attempt_date"]) - date.fromisoformat(day)).days
    if days_to_mock is not None and 1 <= days_to_mock <= 3:
        durations = [105, 75, 75, 105]
    times = shifted_times(start, durations)
    sets = 2 if day < "2026-09-01" else 3
    timed = " Work under a time cap." if day >= "2026-09-28" else " Protect comprehension before speed."
    dilr = choose_dilr_topic(con, day)
    quant_revision = bool(quant["next_revision"] and quant["next_revision"] <= day) if "next_revision" in quant.keys() else False
    quant_title = f"Spaced revision · {quant['name']}" if quant_revision else f"{quant['name']}: learn → solve → test"
    quant_detail = "Retrieve the method without notes, solve a compact mixed set, then verify only the misses." if quant_revision else "Use the current mastery level; log reusable errors and let accuracy control the next step."
    planned = [
        task(day, times[0], durations[0], "Quant", quant["name"], quant_title, quant_detail, quant["source"], 35, 80, "High", "practice"),
        task(day, times[1], durations[1], "DILR", dilr["name"] if dilr else "Mixed DI-LR", f"{sets} DILR sets: {dilr['name'] if dilr else 'mixed selection'}", "One weak-area exposure plus normal rotation. Record representation, solve result and CAT selectability.", "Enabled DILR bank", sets, 70, "High", "practice"),
        task(day, times[2], durations[2], "VARC", "RC + VA", "2 RC passages + 5 VA questions", "Review every wrong option; tag recurring patterns." + timed, "Enabled VARC bank + editorials", 7, 75, "High", "practice"),
        task(day, times[3], durations[3], "Revision", "Error log", "Close the loop", "Update physical diaries, schedule revisions, and preview tomorrow.", "Error log + physical diaries", 0, 0, "Medium", "revision"),
    ]

    # The opening runway builds familiarity without inventing a separate diagnostic.
    if day == "2026-08-12":
        planned[0].update(topic="Percentages", title="Percentages + ratio basics · diagnostic runway", detail="Build basic arithmetic familiarity; stop before fatigue. AIMCAT2714 is the diagnostic.", target_count=24)
    elif day == "2026-08-13":
        planned[0].update(topic="Averages", title="Averages + profit/loss · diagnostic runway", detail="Continue foundation coverage while keeping enough energy for the first AIMCAT.", target_count=24)
    elif day == "2026-08-14":
        planned[0].update(topic="Percentages", title="Light foundation + CAT format familiarisation", detail="Review formulas and question format; do not try to finish the syllabus before AIMCAT2714.", target_count=15)

    if days_to_mock is not None and 1 <= days_to_mock <= 3:
        planned[0].update(title=f"Formula recall + weak-area warm-up · {upcoming['test_ref']}", detail="Revise recent work; avoid cramming an entire new topic before the AIMCAT.", target_count=min(planned[0]["target_count"], 20))
        planned[1].update(title="DILR selection rehearsal · easy/moderate set", detail="Practise opening scan and set choice, then solve one controlled set.", target_count=1)
        planned[2].update(title="Light VARC strategy rehearsal", detail="Maintain comprehension and option review without a heavy new drill.", target_count=5)
        planned[3].update(title=f"Pre-{upcoming['test_ref']} readiness", detail="Review recent errors, formula book, DILR selection rules and VARC attempt strategy.", priority="High")
        for item in planned:
            item["adaptive_reason"] = f"Pre-mock taper · {upcoming['test_ref']} in {days_to_mock} day{'s' if days_to_mock != 1 else ''}"

    if day == "2026-08-12":
        planned[0].update(topic="Percentages", title="Percentages + ratio basics · diagnostic runway", detail="Build basic arithmetic familiarity; stop before fatigue. AIMCAT2714 is the diagnostic.", target_count=24)
    elif day == "2026-08-13":
        planned[0].update(topic="Averages", title="Averages + profit/loss · diagnostic runway", detail="Continue foundation coverage while keeping enough energy for the first AIMCAT.", target_count=24)
    elif day == "2026-08-14":
        planned[0].update(topic="Percentages", title="Light foundation + CAT format familiarisation", detail="Review formulas and question format; do not try to finish the syllabus before AIMCAT2714.", target_count=15)

    last_diagnosis = con.execute(
        """SELECT schedule.diagnosis_json,schedule.test_ref,schedule.actual_attempt_date
           FROM aimcat_schedules schedule
           WHERE schedule.actual_attempt_date IS NOT NULL
             AND schedule.actual_attempt_date<? AND schedule.diagnosis_json!=''
           ORDER BY schedule.actual_attempt_date DESC LIMIT 1""",
        (day,),
    ).fetchone()
    diagnosis = decode_diagnosis(last_diagnosis["diagnosis_json"]) if last_diagnosis else None
    if diagnosis and not (days_to_mock is not None and days_to_mock <= 1):
        subject = {"QA": "Quant", "DILR": "DILR", "VARC": "VARC"}[diagnosis["limiting"]["section"]]
        block = next(item for item in planned if item["subject"] == subject)
        block["title"] = f"{last_diagnosis['test_ref']} repair · {block['title']}"
        block["detail"] = f"Mock-derived repair: {diagnosis['issues'][0]}. {block['detail']}"
        block["target_count"] += 10 if subject == "Quant" else 1 if subject == "DILR" else 3
        block["adaptive_reason"] = f"{diagnosis['allocation']['mock_repair']}% repair allocation after {last_diagnosis['test_ref']}"
        month = day[5:7]
        weekday = date.fromisoformat(day).weekday()
        persistent = diagnosis["limiting"]["section"] in diagnosis["persistent_sections"]
        sectional_day = (
            (month == "09" and persistent and weekday == 3)
            or (month == "10" and (persistent or diagnosis["limiting"]["percentile"] < 80) and weekday in (1, 3))
            or (month == "11" and persistent and weekday == 3)
        )
        if sectional_day and not (days_to_mock is not None and days_to_mock <= 3):
            block.update(
                kind="sectional", title=f"T.I.M.E. Turbo {diagnosis['limiting']['section']} sectional",
                detail=f"Evidence-backed sectional after {last_diagnosis['test_ref']}; analyse selection and pacing before using another.",
                resource="T.I.M.E. Turbo advanced sectionals", target_count=1,
                adaptive_reason=f"Selective sectional for repeated {diagnosis['limiting']['section']} weakness",
            )

    if "2026-11-19" <= day < CAT_DATE:
        planned[0].update(title="CAT consolidation · mixed QA + formula book", detail="Use PYQs and the formula book; no broad new syllabus expansion.")
        planned[1].update(title="CAT consolidation · selected DILR", detail="Prioritise set selection and one or two high-quality sets.", target_count=min(2, planned[1]["target_count"]))
        planned[2].update(title="CAT consolidation · VARC strategy", detail="Maintain normal comprehension rhythm and stable attempt strategy.")
        planned[3].update(title="CAT consolidation · errors, routine and sleep", detail="Review error logs, test strategy and sleep consistency. No automatic full mocks.")
        for item in planned:
            item["adaptive_reason"] = "Final 11-day CAT consolidation · full mocks suppressed"
    attach_time_foundation_checkpoint(con, day, planned, days_to_mock)
    return planned


def task(day, start, duration, subject, topic, title, detail, resource, target, accuracy, priority, kind):
    return dict(date=day, start_time=start, duration=duration, subject=subject, topic=topic, title=title, detail=detail, resource=resource, target_count=target, accuracy_target=accuracy, priority=priority, completed=0, completion=0, actual_duration=0, manual=0, kind=kind)


def row_map(rows: list[sqlite3.Row]) -> dict[str, str]:
    return {row["key"]: row["value"] for row in rows}


def init_db():
    DATA.mkdir(exist_ok=True)
    with connection() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS profile (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS topics (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, area TEXT, name TEXT, status TEXT DEFAULT 'Not Started', confidence INTEGER DEFAULT 1, accuracy REAL DEFAULT 0, attempted INTEGER DEFAULT 0, correct INTEGER DEFAULT 0, avg_time REAL DEFAULT 0, last_practised TEXT, next_revision TEXT, importance INTEGER DEFAULT 3, source TEXT DEFAULT 'IMS module');
        CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, start_time TEXT, duration INTEGER, subject TEXT, topic TEXT, title TEXT, detail TEXT, resource TEXT, target_count INTEGER DEFAULT 0, accuracy_target REAL DEFAULT 0, priority TEXT, completed INTEGER DEFAULT 0, completion INTEGER DEFAULT 0, actual_duration INTEGER DEFAULT 0, manual INTEGER DEFAULT 0, kind TEXT DEFAULT 'practice');
        CREATE TABLE IF NOT EXISTS deadlines (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, date TEXT, time TEXT DEFAULT '', category TEXT, official INTEGER DEFAULT 0, status TEXT DEFAULT 'Pending', note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS mocks (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, provider TEXT, name TEXT, overall_score REAL, overall_percentile REAL, varc_score REAL, varc_percentile REAL, dilr_score REAL, dilr_percentile REAL, qa_score REAL, qa_percentile REAL, varc_attempts INTEGER DEFAULT 0, dilr_attempts INTEGER DEFAULT 0, qa_attempts INTEGER DEFAULT 0, varc_correct INTEGER DEFAULT 0, dilr_correct INTEGER DEFAULT 0, qa_correct INTEGER DEFAULT 0, easy_missed INTEGER DEFAULT 0, def_errors INTEGER DEFAULT 0, weak_topics TEXT DEFAULT '', strategy_next TEXT DEFAULT '', notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS errors (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, subject TEXT, topic TEXT, source TEXT, question_ref TEXT, error_type TEXT, incorrect_approach TEXT, correct_insight TEXT, rule_next TEXT, revision_status TEXT DEFAULT 'Due', repeated INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS resources (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT, type TEXT, tags TEXT, note TEXT, recommended INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS stories (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, tags TEXT, situation TEXT DEFAULT '', problem TEXT DEFAULT '', role TEXT DEFAULT '', actions TEXT DEFAULT '', stakeholders TEXT DEFAULT '', leadership TEXT DEFAULT '', impact TEXT DEFAULT '', challenges TEXT DEFAULT '', outcome TEXT DEFAULT '', learning TEXT DEFAULT '', usefulness TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS day_reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT UNIQUE, actual_hours REAL, energy INTEGER, focus INTEGER, went_well TEXT, difficult TEXT, tomorrow TEXT);
        CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(date);
        """)
        run_migrations(con)
        if con.execute("SELECT COUNT(*) FROM profile").fetchone()[0]:
            migrate_schedule(con)
            seed_study_resource_data(con)
            seed_aimcat_data(con)
            seed_time_foundation_data(con)
            initialize_phase3(con)
            initialize_plan_days(con)
            reconcile_aimcat_plans(con)
            initialize_time_foundation_assignments(con)
            backfill_task_resources(con)
            return
        profile = {"name":"Anusha","class10":"92.2%","class12":"94%","ugCgpa":"7.69","undergraduate":"Information Science / Engineering","schoolBackground":"PCMC","category":"General","gender":"Female","employer":"IBM","employmentStart":"2024-07-01","catTarget":"98–99+","catFloor":"95","gmatTarget":"675+"}
        con.executemany("INSERT INTO profile VALUES(?,?)", profile.items())
        settings = {"studyStart":"18:00","dailyMinutes":"360","theme":"light","revisionIntervals":"1,3,7,14,30","accuracyThreshold":"70","gmatRetakeRule":"Verify current official GMAC waiting interval before booking","notifications":"on","scheduleVersion":"2"}
        con.executemany("INSERT INTO settings VALUES(?,?)", settings.items())
        curricula = {
          "Quant":{"Arithmetic":["Percentages","Ratio and proportion","Averages","Profit and loss","Simple and compound interest","Mixtures and alligation","Time and work","Pipes and cisterns","Time, speed and distance","Relative speed"],"Algebra":["Linear equations","Quadratic equations","Inequalities","Algebraic identities","Logarithms","Functions","Progressions"],"Number Systems":["Divisibility","Factors and multiples","Remainders","Units digits / cyclicity","HCF / LCM","Number properties"],"Geometry":["Lines and angles","Triangles","Circles","Quadrilaterals / polygons","Coordinate geometry basics","Mensuration"],"Modern Mathematics":["Permutations / combinations","Probability","Set theory"]},
          "DILR":{"Structures":["Arrangements","Distribution","Scheduling","Selection","Games and tournaments","Routes / networks","Tables","Charts","Caselets","Venn / set-based","Mixed DI-LR"]},
          "VARC":{"Practice":["Reading Comprehension","Para Summary","Odd Sentence","Para Completion","Para Ordering"]}}
        for subject, areas in curricula.items():
            for area, names in areas.items():
                for name in names:
                    importance = 5 if subject == "Quant" and area in ("Arithmetic", "Algebra") else 3
                    source = "IMS module + CAT PYQs" if subject == "Quant" else "IMS practice"
                    con.execute("INSERT INTO topics(subject,area,name,importance,source) VALUES(?,?,?,?,?)", (subject,area,name,importance,source))
        con.execute("UPDATE topics SET status='Learning',confidence=2 WHERE name IN ('Percentages','Ratio and proportion')")
        deadlines = [
          ("CAT registration closes","2026-09-15","17:00 IST","CAT",1,"Complete registration early; urgent until done."),("CAT admit card available","2026-11-04","","CAT",1,"Download from the official CAT portal."),("CAT 2026 exam","2026-11-29","","CAT",1,"Primary exam."),("ISB Round 1","2026-09-20","","ISB",1,"Skip / not recommended for the current plan."),("ISB Round 2","2026-12-06","","ISB",1,"Primary application target."),("ISB Round 3","2027-01-17","","ISB",1,"Backup; prefer over a rushed R2 application."),("Achievement inventory complete","2026-08-31","","ISB",0,"Capture 8–10 strong stories."),("GMAT Official Diagnostic","2026-09-06","","GMAT",0,"Official Practice Exam 1."),("ISB recommender identified","2026-09-30","","ISB",0,"Confirm fit and availability."),("Why MBA / Why ISB core draft","2026-10-31","","ISB",0,"Career story and goals."),("First GMAT attempt window","2026-10-27","","GMAT",0,"Target October 24–31; editable."),("ISB R2 application 80–90% complete","2026-11-15","","ISB",0,"Reduce application load during CAT peak."),("Final ISB R2 work","2026-12-05","","ISB",0,"Final review November 30–December 5.")]
        con.executemany("INSERT INTO deadlines(title,date,time,category,official,note) VALUES(?,?,?,?,?,?)", deadlines)
        resources = [("IMS SimCAT Plus 2026","https://www.imsindia.com/course/cat/","Test series","Mock,Sectional,DILR,VARC,Practice","Primary paid series. Start here; do not buy everything.",1),("Official CAT website","https://iimcat.ac.in/","Official","CAT,Deadline","Registration, admit card and official notices.",1),("Official CAT PYQs","https://iimcat.ac.in/","Question bank","CAT,PYQ,Practice","Use previous-year papers alongside IMS.",1),("GMAT Official Starter Kit","https://www.mba.com/exam-prep/gmat-official-starter-kit","Official","GMAT,Diagnostic","Free official diagnostic and practice.",1),("T.I.M.E. AIMCAT","https://www.time4education.com/","Test series","Mock,CAT","Selective secondary source from October.",0),("Career Launcher CAT","https://www.careerlauncher.com/cat-mba/","Test series","Mock,CAT","Use open/free CDC mocks selectively.",0),("Cracku CAT","https://cracku.in/cat","Practice","Quant,DILR,Mock","Optional source if more challenge is needed.",0)]
        con.executemany("INSERT INTO resources(name,url,type,tags,note,recommended) VALUES(?,?,?,?,?,?)", resources)
        con.execute("INSERT INTO stories(title,tags,situation,usefulness) VALUES(?,?,?,?)", ("IBM impact story — add details","Leadership,Technical impact,Business impact","Capture a project where your work changed an outcome.","Potential leadership / impact essay evidence"))
        seed_study_resource_data(con)
        seed_aimcat_data(con)
        seed_time_foundation_data(con)
        for offset in range(7):
            day = (date(2026,8,12)+timedelta(days=offset)).isoformat()
            for row in plan_rows(con, day): insert_task(con, row)
        insert_task(con, task("2026-08-12","19:30",20,"Admin","Setup","Complete CAT registration checklist","Confirm documents and complete registration early.","Official CAT website",1,0,"Critical","deadline"))
        seed_study_resource_data(con)
        seed_aimcat_data(con)
        seed_time_foundation_data(con)
        initialize_phase3(con)
        initialize_plan_days(con)
        reconcile_aimcat_plans(con)
        initialize_time_foundation_assignments(con)
        backfill_task_resources(con)


def insert_task(con: sqlite3.Connection, row: dict[str, Any]) -> int:
    keys = list(row)
    cursor = con.execute(f"INSERT INTO tasks({','.join(keys)}) VALUES({','.join('?' for _ in keys)})", tuple(row[k] for k in keys))
    task_id = int(cursor.lastrowid)
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_resource_assignments'").fetchone():
        task_row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        topic_row = resolve_task_topic(con, task_row)
        if topic_row:
            con.execute(
                "UPDATE tasks SET topic_id=?,difficulty=?,adaptive_reason=? WHERE id=?",
                (
                    topic_row["id"], topic_row["progression_level"],
                    row.get("adaptive_reason") or adaptive_reason_for(con, topic_row), task_id,
                ),
            )
        assign_task_resources(con, task_id)
    return task_id


def migrate_schedule(con: sqlite3.Connection):
    """One-time migration of seeded automatic tasks to the 6 PM–midnight window."""
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    if settings.get("scheduleVersion") == "2":
        return
    con.execute("INSERT INTO settings(key,value) VALUES('studyStart','18:00') ON CONFLICT(key) DO UPDATE SET value='18:00'")
    con.execute("INSERT INTO settings(key,value) VALUES('scheduleVersion','2') ON CONFLICT(key) DO UPDATE SET value='2'")
    con.execute("""
        UPDATE tasks
        SET start_time = CASE
            WHEN kind = 'mock' THEN '18:00'
            WHEN kind = 'analysis' THEN '20:00'
            WHEN kind = 'revision' AND EXISTS (
                SELECT 1 FROM tasks mock_task
                WHERE mock_task.date = tasks.date AND mock_task.kind = 'mock'
            ) THEN '23:00'
            WHEN subject = 'Quant' THEN '18:00'
            WHEN subject = 'DILR' THEN '20:15'
            WHEN subject = 'VARC' THEN '22:00'
            WHEN kind = 'revision' THEN '23:30'
            WHEN title = 'Complete CAT registration checklist' THEN '17:30'
            WHEN title = 'Activate primary practice system' THEN '17:50'
            ELSE start_time
        END
        WHERE manual = 0
    """)


def run_migrations(con: sqlite3.Connection):
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    applied = {row[0] for row in con.execute("SELECT version FROM schema_migrations")}
    for migration in sorted(MIGRATIONS.glob("*.sql")):
        if migration.stem in applied:
            continue
        con.executescript(migration.read_text(encoding="utf-8"))
        con.execute("INSERT INTO schema_migrations(version) VALUES(?)", (migration.stem,))


def initialize_plan_days(con: sqlite3.Connection):
    """Populate generated-day markers on first setup without changing later moves."""
    if con.execute("SELECT COUNT(*) FROM plan_days").fetchone()[0]:
        return
    con.execute("INSERT OR IGNORE INTO plan_days(date) SELECT DISTINCT date FROM tasks WHERE manual=0 AND archived=0")


def reconcile_aimcat_plans(con: sqlite3.Connection):
    """Replace untouched generated plans in place while archiving, never deleting, old rows."""
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    if settings.get("aimcatPlannerVersion") == "3":
        return
    planner_kinds = ("practice", "sectional", "mock", "analysis", "revision")
    days = [row["date"] for row in con.execute(
        "SELECT date FROM plan_days WHERE date>=? AND date<? ORDER BY date",
        (PREP_START_DATE, CAT_DATE),
    ).fetchall()]
    for day in days:
        existing = con.execute(
            """SELECT * FROM tasks
               WHERE date=? AND manual=0 AND archived=0 AND kind IN (?,?,?,?,?)
               ORDER BY start_time,id""",
            (day, *planner_kinds),
        ).fetchall()
        if not existing:
            continue
        task_ids = [int(item["id"]) for item in existing]
        placeholders = ",".join("?" for _ in task_ids)
        touched = any(item["completed"] or item["completion"] or item["actual_duration"] or item["rescheduled"] for item in existing)
        touched = touched or bool(con.execute(
            f"SELECT 1 FROM task_results WHERE task_id IN ({placeholders}) LIMIT 1", task_ids
        ).fetchone())
        touched = touched or bool(con.execute(
            f"SELECT 1 FROM task_resource_assignments WHERE task_id IN ({placeholders}) AND manual_override=1 LIMIT 1", task_ids
        ).fetchone())
        desired = plan_rows(con, day)
        if touched:
            if day in ("2026-08-12", "2026-08-13", "2026-08-14") and len(existing) == len(desired):
                for current, replacement in zip(existing, desired):
                    topic_row = resolve_task_topic(con, replacement)
                    con.execute(
                        """UPDATE tasks SET subject=?,topic=?,title=?,detail=?,resource=?,target_count=?,
                           accuracy_target=?,priority=?,topic_id=?,difficulty=?,adaptive_reason=? WHERE id=?""",
                        (
                            replacement["subject"], replacement["topic"], replacement["title"],
                            replacement["detail"], replacement["resource"], replacement["target_count"],
                            replacement["accuracy_target"], replacement["priority"],
                            topic_row["id"] if topic_row else current["topic_id"],
                            topic_row["progression_level"] if topic_row else current["difficulty"],
                            replacement.get("adaptive_reason", current["adaptive_reason"]), current["id"],
                        ),
                    )
                    con.execute("DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0", (current["id"],))
                    assign_task_resources(con, int(current["id"]))
            continue
        current_signature = [(item["kind"], item["title"], item["duration"], item["aimcat_schedule_id"]) for item in existing]
        desired_signature = [(item["kind"], item["title"], item["duration"], item.get("aimcat_schedule_id")) for item in desired]
        if current_signature == desired_signature:
            continue
        con.execute(
            f"UPDATE tasks SET archived=1 WHERE id IN ({placeholders})", task_ids
        )
        for item in desired:
            insert_task(con, item)
    con.execute(
        "INSERT INTO settings(key,value) VALUES('aimcatPlannerVersion','3') ON CONFLICT(key) DO UPDATE SET value='3'"
    )


def initialize_time_foundation_assignments(con: sqlite3.Connection):
    """Attach checkpoints to eligible untouched August plans without replacing any task data."""
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    if settings.get("timeFoundationPlannerVersion") == "2":
        return
    days = con.execute(
        """SELECT DISTINCT date FROM tasks
           WHERE date>? AND date<='2026-08-31' AND manual=0 AND archived=0 ORDER BY date""",
        (PREP_START_DATE,),
    ).fetchall()
    for item in days:
        desired = plan_rows(con, item["date"])
        for planned in desired:
            test_id = planned.get("time_foundation_test_id")
            if not test_id:
                continue
            existing = con.execute(
                """
                SELECT task.id FROM tasks task
                WHERE task.date=? AND task.subject=? AND task.kind='practice'
                  AND task.manual=0 AND task.archived=0 AND task.completed=0
                  AND task.rescheduled=0 AND task.time_foundation_test_id IS NULL
                  AND NOT EXISTS (SELECT 1 FROM task_results result WHERE result.task_id=task.id)
                  AND NOT EXISTS (
                    SELECT 1 FROM task_resource_assignments assignment
                    WHERE assignment.task_id=task.id AND assignment.manual_override=1
                  )
                ORDER BY task.start_time LIMIT 1
                """,
                (item["date"], planned["subject"]),
            ).fetchone()
            if existing:
                con.execute(
                    "UPDATE tasks SET time_foundation_test_id=?,adaptive_reason=? WHERE id=?",
                    (test_id, planned.get("adaptive_reason", ""), existing["id"]),
                )
    checkpoint_tasks = con.execute(
        """SELECT task.id FROM tasks task WHERE task.time_foundation_test_id IS NOT NULL
           AND task.manual=0 AND task.completed=0 AND task.archived=0 AND task.rescheduled=0
           AND NOT EXISTS (
             SELECT 1 FROM task_resource_assignments assignment
             WHERE assignment.task_id=task.id AND assignment.manual_override=1
           )"""
    ).fetchall()
    for task in checkpoint_tasks:
        con.execute(
            "DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0",
            (task["id"],),
        )
        assign_task_resources(con, int(task["id"]))
    con.execute(
        "INSERT INTO settings(key,value) VALUES('timeFoundationPlannerVersion','2') ON CONFLICT(key) DO UPDATE SET value='2'"
    )


def seed_study_resource_data(con: sqlite3.Connection):
    columns = [
        "id", "provider", "title", "description", "subject", "topic_slug", "type", "url",
        "platform_path", "free", "requires_subscription", "estimated_minutes",
        "recommended_question_count", "difficulty", "active", "last_verified_at",
    ]
    placeholders = ",".join("?" for _ in columns)
    for item in STUDY_RESOURCES:
        con.execute(
            f"INSERT OR IGNORE INTO study_resources({','.join(columns)}) VALUES({placeholders})",
            tuple(item[column] for column in columns),
        )
    con.executemany(
        "INSERT OR IGNORE INTO user_resource_access(resource_provider,enabled,subscription_name,notes) VALUES(?,?,?,?)",
        USER_RESOURCE_ACCESS,
    )
    mappings = build_topic_mappings(con.execute("SELECT id,subject,name FROM topics").fetchall())
    con.executemany(
        "INSERT OR IGNORE INTO topic_resource_maps(topic_id,resource_id,purpose,priority,phase) VALUES(?,?,?,?,?)",
        mappings,
    )


def initialize_phase3(con: sqlite3.Connection):
    """Populate new derived references without replacing any user-entered values."""
    for task_row in con.execute("SELECT * FROM tasks WHERE topic_id IS NULL AND archived=0 ORDER BY id").fetchall():
        topic_row = resolve_task_topic(con, task_row)
        if topic_row:
            con.execute(
                "UPDATE tasks SET topic_id=?,difficulty=?,adaptive_reason=? WHERE id=?",
                (
                    topic_row["id"], topic_row["progression_level"],
                    "Backfilled topic link; existing task content preserved", task_row["id"],
                ),
            )
    con.execute(
        """
        UPDATE task_resource_assignments
        SET difficulty=COALESCE((SELECT difficulty FROM tasks WHERE tasks.id=task_id),'FOUNDATION')
        WHERE difficulty='FOUNDATION'
        """
    )
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    if settings.get("adaptiveAssignmentVersion") != "3":
        task_ids = [
            row["id"]
            for row in con.execute("SELECT id FROM tasks WHERE manual=0 AND rescheduled=0 AND completed=0 AND archived=0 ORDER BY id").fetchall()
        ]
        for task_id in task_ids:
            con.execute(
                "DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0",
                (task_id,),
            )
            assign_task_resources(con, int(task_id))
        con.execute(
            "INSERT INTO settings(key,value) VALUES('adaptiveAssignmentVersion','3') ON CONFLICT(key) DO UPDATE SET value='3'"
        )


def resolve_task_topic(con: sqlite3.Connection, task_row: sqlite3.Row | dict[str, Any]):
    """Resolve broad generated blocks to one catalog topic without changing planner priority."""
    subject = "Quant" if task_row["subject"] in ("Quant", "QA") else task_row["subject"]
    exact = con.execute(
        "SELECT * FROM topics WHERE subject=? AND name=?",
        (subject, task_row["topic"]),
    ).fetchone()
    if exact:
        return exact
    if subject == "VARC":
        return con.execute("SELECT * FROM topics WHERE subject='VARC' AND name='Reading Comprehension'").fetchone()
    if subject == "DILR":
        topic_rows = con.execute("SELECT * FROM topics WHERE subject='DILR' ORDER BY id").fetchall()
        if topic_rows:
            offset = max(0, (date.fromisoformat(task_row["date"]) - date.fromisoformat(PREP_START_DATE)).days)
            return topic_rows[offset % len(topic_rows)]
    return None


def adaptive_reason_for(con: sqlite3.Connection, topic_row: sqlite3.Row | dict[str, Any]) -> str:
    level = topic_row["progression_level"]
    if not topic_row["attempted"]:
        return f"First measured exposure: start at {level.replace('_', ' ').title()}"
    signals = con.execute(
        "SELECT reason FROM adaptive_signals WHERE topic_id=? AND resolved_at IS NULL ORDER BY weight DESC LIMIT 1",
        (topic_row["id"],),
    ).fetchone()
    if signals:
        return f"{signals['reason']} Current level: {level.replace('_', ' ').title()}."
    return f"{topic_row['accuracy']}% accuracy and confidence {topic_row['confidence']}/5 justify {level.replace('_', ' ').title()} work"


def resource_candidates(
    con: sqlite3.Connection,
    task_row: sqlite3.Row | dict[str, Any],
    stage: str,
) -> list[sqlite3.Row]:
    if task_row["kind"] == "sectional" and stage == "PRACTICE":
        return con.execute(
            """SELECT sr.*,1 AS priority,'ALL' AS phase FROM study_resources sr
               JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
               WHERE sr.id='time-turbo-sectionals' AND sr.active=1"""
        ).fetchall()
    if task_row["kind"] == "mock" and task_row["aimcat_schedule_id"] and stage == "PYQ":
        return con.execute(
            """
            SELECT sr.*,1 AS priority,'ALL' AS phase
            FROM study_resources sr
            JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
            WHERE sr.id='time-aimcat-portal' AND sr.active=1
            """
        ).fetchall()
    topic_row = resolve_task_topic(con, task_row)
    if topic_row:
        candidates = con.execute(
            """
            SELECT sr.*, trm.priority, trm.phase,
                   CASE
                     WHEN ? IN ('CAT_LEVEL','TIMED','MIXED') AND sr.difficulty='CAT_LEVEL' THEN 0
                     WHEN ? IN ('FOUNDATION','INTERMEDIATE') AND sr.difficulty='FOUNDATION' THEN 0
                     WHEN sr.difficulty IS NULL THEN 1
                     ELSE 2
                   END AS difficulty_rank
            FROM topic_resource_maps trm
            JOIN study_resources sr ON sr.id=trm.resource_id AND sr.active=1
            JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
            WHERE trm.topic_id=? AND trm.purpose=? AND trm.phase IN ('ALL', ?)
            ORDER BY difficulty_rank,trm.priority,sr.free DESC,sr.title
            """,
            (task_row["difficulty"], task_row["difficulty"], topic_row["id"], stage, phase_for(task_row["date"])),
        ).fetchall()
        if candidates:
            return candidates

    # A mock can still use a full previous-year paper when no paid test series is enabled.
    if task_row["kind"] == "mock" and stage == "PYQ":
        return con.execute(
            """
            SELECT sr.*, 100 AS priority, 'ALL' AS phase
            FROM study_resources sr
            JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
            WHERE sr.id='2iim-cat-pyq' AND sr.active=1
            """
        ).fetchall()
    return []


def stage_plan(task_row: sqlite3.Row | dict[str, Any]) -> list[tuple[str, int, int]]:
    duration = int(task_row["duration"] or 0)
    checkpoint = bool(
        "time_foundation_test_id" in task_row.keys() and task_row["time_foundation_test_id"]
    )
    # Reserve time inside the existing block; a checkpoint never stacks extra nightly load.
    if checkpoint:
        duration = max(30, duration - 45)
    level = task_row["difficulty"] if "difficulty" in task_row.keys() else "FOUNDATION"
    if task_row["kind"] == "mock":
        return [("PYQ", duration, 1)]
    if task_row["kind"] == "sectional":
        return [("PRACTICE", duration, 1)]
    if task_row["kind"] != "practice":
        return []
    if task_row["subject"] in ("Quant", "QA"):
        if level == "FOUNDATION":
            return [("LEARN", min(55, duration), 0), ("PRACTICE", max(30, duration - 55), 12)]
        if level == "INTERMEDIATE":
            return [("LEARN", min(30, duration), 0), ("PRACTICE", max(45, duration - 30), 18)]
        if level == "CAT_LEVEL":
            return [("PRACTICE", min(80, duration), 20), ("PYQ", max(25, duration - 80), 6)]
        if level == "TIMED":
            return [("PRACTICE", min(75, duration), 25), ("PYQ", max(30, duration - 75), 8)]
        return [("PRACTICE", min(90, duration), 30), ("PYQ", max(30, duration - 90), 10)]
    if task_row["subject"] == "DILR":
        if level in ("FOUNDATION", "INTERMEDIATE"):
            target = min(1, int(task_row["target_count"] or 2)) if checkpoint else int(task_row["target_count"] or 2)
            return [("LEARN", min(20, duration), 0), ("PRACTICE", max(30, duration - 20), target)]
        return [("PRACTICE", min(60, duration), 2), ("PYQ", max(30, duration - 60), 1)]
    if task_row["subject"] == "VARC":
        if level in ("FOUNDATION", "INTERMEDIATE"):
            return [("PRACTICE", duration, 7)]
        return [("PRACTICE", min(60, duration), 5), ("PYQ", max(15, duration - 60), 2)]
    return []


def assign_task_resources(con: sqlite3.Connection, task_id: int):
    task_row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task_row:
        return
    for stage_order, (stage, minutes, target_count) in enumerate(stage_plan(task_row), start=1):
        if con.execute(
            "SELECT 1 FROM task_resource_assignments WHERE task_id=? AND stage=?",
            (task_id, stage),
        ).fetchone():
            continue
        candidates = resource_candidates(con, task_row, stage)
        if not candidates:
            continue
        resource = candidates[0]
        con.execute(
            """
            INSERT INTO task_resource_assignments(
                task_id,resource_id,stage,stage_order,estimated_minutes,target_count,
                accuracy_target,selected_reason
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                task_id, resource["id"], stage, stage_order, minutes, target_count,
                float(task_row["accuracy_target"] or 0),
                f"{task_row['adaptive_reason']} Selected enabled {stage.lower()} material at {task_row['difficulty'].replace('_', ' ').title()} level.",
            ),
        )
        con.execute(
            "UPDATE task_resource_assignments SET difficulty=? WHERE task_id=? AND stage=?",
            (task_row["difficulty"], task_id, stage),
        )


def backfill_task_resources(con: sqlite3.Connection):
    """Idempotently attach material to existing tasks; no task or result data is replaced."""
    for task_row in con.execute("SELECT id FROM tasks WHERE archived=0 ORDER BY id").fetchall():
        assign_task_resources(con, int(task_row["id"]))


def refresh_disabled_assignments(con: sqlite3.Connection):
    con.execute(
        """
        DELETE FROM task_resource_assignments
        WHERE manual_override=0 AND resource_id IN (
            SELECT sr.id FROM study_resources sr
            JOIN user_resource_access ura ON ura.resource_provider=sr.provider
            WHERE ura.enabled=0
        )
        """
    )
    backfill_task_resources(con)


def revision_intervals(con: sqlite3.Connection) -> list[int]:
    raw = row_map(con.execute("SELECT key,value FROM settings").fetchall()).get("revisionIntervals", "1,3,7,14,30")
    try:
        values = [int(value.strip()) for value in raw.split(",") if int(value.strip()) > 0]
    except ValueError:
        values = [1, 3, 7, 14, 30]
    return values or [1, 3, 7, 14, 30]


def schedule_revision(
    con: sqlite3.Connection,
    topic_row: sqlite3.Row,
    task_row: sqlite3.Row,
    accuracy: float,
    confidence: int,
):
    intervals = revision_intervals(con)
    threshold = float(row_map(con.execute("SELECT key,value FROM settings").fetchall()).get("accuracyThreshold", "70"))
    current_step = int(topic_row["revision_step"] or 0)
    if accuracy < threshold or confidence <= 2:
        interval_index = 0
    else:
        interval_index = min(current_step, len(intervals) - 1)
    due_date = (date.fromisoformat(task_row["date"]) + timedelta(days=intervals[interval_index])).isoformat()
    con.execute(
        "UPDATE revision_schedule SET status='SUPERSEDED' WHERE topic_id=? AND status='PENDING'",
        (topic_row["id"],),
    )
    con.execute(
        "INSERT INTO revision_schedule(topic_id,due_date,interval_index,source_task_id) VALUES(?,?,?,?)",
        (topic_row["id"], due_date, interval_index, task_row["id"]),
    )
    con.execute(
        "UPDATE topics SET next_revision=?,revision_step=? WHERE id=?",
        (due_date, min(interval_index + 1, len(intervals) - 1), topic_row["id"]),
    )


def refresh_future_topic_assignments(con: sqlite3.Connection, topic_id: int, after_date: str):
    topic_row = con.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    if not topic_row:
        return
    future_tasks = con.execute(
        "SELECT id FROM tasks WHERE topic_id=? AND date>? AND manual=0 AND rescheduled=0 AND completed=0 AND archived=0 ORDER BY date",
        (topic_id, after_date),
    ).fetchall()
    for item in future_tasks:
        con.execute(
            "UPDATE tasks SET difficulty=?,adaptive_reason=? WHERE id=?",
            (topic_row["progression_level"], adaptive_reason_for(con, topic_row), item["id"]),
        )
        con.execute(
            "DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0",
            (item["id"],),
        )
        assign_task_resources(con, int(item["id"]))

    if topic_row["accuracy"] < 70 or topic_row["confidence"] <= 2:
        repair_task = con.execute(
            """
            SELECT * FROM tasks
            WHERE date>? AND subject='Quant' AND kind='practice' AND manual=0 AND rescheduled=0 AND completed=0 AND archived=0
              AND NOT EXISTS (
                SELECT 1 FROM task_resource_assignments assignment
                WHERE assignment.task_id=tasks.id AND assignment.manual_override=1
              )
            ORDER BY date,start_time LIMIT 1
            """,
            (after_date,),
        ).fetchone()
        if repair_task and repair_task["topic_id"] != topic_id:
            con.execute(
                """
                UPDATE tasks SET topic_id=?,topic=?,title=?,difficulty=?,
                    adaptive_reason=?,detail=? WHERE id=?
                """,
                (
                    topic_id, topic_row["name"], f"{topic_row['name']}: repair → practise → verify",
                    topic_row["progression_level"],
                    f"Low performance requires concept repair: {topic_row['accuracy']}% accuracy, confidence {topic_row['confidence']}/5",
                    "Repair the specific gap, then complete a smaller graded practice set. Do not jump to hard PYQs yet.",
                    repair_task["id"],
                ),
            )
            con.execute("DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0", (repair_task["id"],))
            assign_task_resources(con, int(repair_task["id"]))


def recompute_topic_from_events(
    con: sqlite3.Connection,
    topic_id: int,
    event_date: str,
    source_task_id: int | None,
    result_accuracy: float,
    result_confidence: int,
    outcome: str | None = None,
):
    """Apply the shared mastery/revision pipeline to any measured study event."""
    aggregate = con.execute(
        """
        SELECT SUM(attempted) attempted,SUM(correct) correct,SUM(time_spent) time_spent,
               ROUND(AVG(confidence),0) confidence
        FROM topic_performance_events WHERE topic_id=?
        """,
        (topic_id,),
    ).fetchone()
    attempted = int(aggregate["attempted"] or 0)
    correct = int(aggregate["correct"] or 0)
    accuracy = round(correct * 100 / attempted, 1) if attempted else 0
    confidence = max(1, min(5, int(aggregate["confidence"] or result_confidence)))
    progression = progression_for(attempted, accuracy, confidence)
    levels = ("FOUNDATION", "INTERMEDIATE", "CAT_LEVEL", "TIMED", "MIXED")
    if outcome == "ADVANCE" and levels.index(progression) < levels.index("CAT_LEVEL"):
        progression = "CAT_LEVEL"
    elif outcome == "REPAIR":
        progression = "FOUNDATION"
    con.execute(
        """
        UPDATE topics SET status=?,confidence=?,accuracy=?,attempted=?,correct=?,avg_time=?,
            last_practised=?,progression_level=?,mastery_score=? WHERE id=?
        """,
        (
            mastery_status(attempted, progression), confidence, accuracy, attempted, correct,
            round(float(aggregate["time_spent"] or 0) / attempted, 2) if attempted else 0,
            event_date, progression, mastery_score(accuracy, confidence, progression), topic_id,
        ),
    )
    if outcome in (None, "ADVANCE"):
        con.execute(
            "UPDATE adaptive_signals SET resolved_at=CURRENT_TIMESTAMP WHERE topic_id=? AND resolved_at IS NULL",
            (topic_id,),
        )
    updated_topic = con.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
    con.execute(
        """
        UPDATE revision_schedule SET status='COMPLETE',completed_at=CURRENT_TIMESTAMP
        WHERE topic_id=? AND status='PENDING' AND due_date<=?
        """,
        (topic_id, event_date),
    )
    schedule_revision(
        con, updated_topic, {"date": event_date, "id": source_task_id},
        result_accuracy, result_confidence,
    )
    refresh_future_topic_assignments(con, topic_id, event_date)


def apply_task_result_to_topic(con: sqlite3.Connection, task_id: int, result: dict[str, Any]):
    task_row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task_row or not task_row["topic_id"]:
        return
    topic_id = int(task_row["topic_id"])
    metadata = {
        key: result.get(key)
        for key in ("dilr_sets_solved", "dilr_representation", "dilr_selectability", "varc_error_pattern")
        if result.get(key) not in (None, "")
    }
    con.execute(
        """
        INSERT INTO topic_performance_events(
            topic_id,source_type,source_id,occurred_on,attempted,correct,accuracy,
            time_spent,confidence,difficulty,metadata
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(topic_id,source_type,source_id) DO UPDATE SET
            occurred_on=excluded.occurred_on,attempted=excluded.attempted,correct=excluded.correct,
            accuracy=excluded.accuracy,time_spent=excluded.time_spent,confidence=excluded.confidence,
            difficulty=excluded.difficulty,metadata=excluded.metadata,updated_at=CURRENT_TIMESTAMP
        """,
        (
            topic_id, "TASK", task_id, task_row["date"], result["attempted"], result["correct"],
            result["accuracy"], result["time_spent"], result["confidence"], task_row["difficulty"],
            json.dumps(metadata, sort_keys=True),
        ),
    )
    recompute_topic_from_events(
        con, topic_id, task_row["date"], task_id,
        result["accuracy"], result["confidence"],
    )


def match_topic(con: sqlite3.Connection, subject: str, topic_name: str):
    normalized_subject = "Quant" if subject in ("QA", "Quant", "Mock") else subject
    exact = con.execute(
        "SELECT * FROM topics WHERE subject=? AND LOWER(name)=LOWER(?)",
        (normalized_subject, topic_name.strip()),
    ).fetchone()
    if exact:
        return exact
    return con.execute(
        "SELECT * FROM topics WHERE subject=? AND (LOWER(name) LIKE LOWER(?) OR LOWER(?) LIKE '%'||LOWER(name)||'%') ORDER BY importance DESC LIMIT 1",
        (normalized_subject, f"%{topic_name.strip()}%", topic_name.strip()),
    ).fetchone()


def add_adaptive_signal(con: sqlite3.Connection, topic_row: sqlite3.Row, source_type: str, source_id: int, weight: float, reason: str):
    con.execute(
        """
        INSERT INTO adaptive_signals(topic_id,source_type,source_id,weight,reason)
        VALUES(?,?,?,?,?)
        ON CONFLICT(topic_id,source_type,source_id) DO UPDATE SET
            weight=excluded.weight,reason=excluded.reason,resolved_at=NULL
        """,
        (topic_row["id"], source_type, source_id, weight, reason),
    )


def retarget_future_task_from_signal(con: sqlite3.Connection, topic_row: sqlite3.Row, after_date: str, reason: str):
    task_subject = "Quant" if topic_row["subject"] == "Quant" else topic_row["subject"]
    future = con.execute(
        """
        SELECT * FROM tasks
        WHERE date>? AND subject=? AND kind='practice' AND manual=0 AND rescheduled=0 AND completed=0 AND archived=0
          AND adaptive_reason NOT LIKE 'Mock/error signal:%'
          AND NOT EXISTS (
            SELECT 1 FROM task_resource_assignments assignment
            WHERE assignment.task_id=tasks.id AND assignment.manual_override=1
          )
        ORDER BY date,start_time LIMIT 1
        """,
        (after_date, task_subject),
    ).fetchone()
    if not future:
        return
    con.execute(
        """
        UPDATE tasks SET topic_id=?,topic=?,difficulty=?,adaptive_reason=?,title=? WHERE id=?
        """,
        (
            topic_row["id"], topic_row["name"], topic_row["progression_level"],
            f"Mock/error signal: {reason}",
            f"{topic_row['name']}: targeted repair and verification", future["id"],
        ),
    )
    con.execute("DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0", (future["id"],))
    assign_task_resources(con, int(future["id"]))


def import_time_foundation_csv(con: sqlite3.Connection, content: str) -> dict[str, int]:
    cleaned = content.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(cleaned[:4096], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(cleaned), dialect=dialect)
    if not reader.fieldnames:
        raise HTTPException(400, "Paste a CSV with Test Reference, Description and Subject columns")
    header_map = {name.strip().lower(): name for name in reader.fieldnames if name}
    required = ("test reference", "description", "subject")
    missing = [name.title() for name in required if name not in header_map]
    if missing:
        raise HTTPException(400, f"Missing required columns: {', '.join(missing)}")
    created = updated = 0
    subject_aliases = {
        "QUANT": "QA", "QUANTITATIVE ABILITY": "QA", "QA": "QA",
        "DATA INTERPRETATION": "DI", "DI": "DI",
        "LOGICAL REASONING": "LR", "LR": "LR", "VARC": "VARC",
    }

    def optional(row, name):
        source = header_map.get(name)
        value = row.get(source, "") if source else ""
        return str(value).strip() or None

    for number, row in enumerate(reader, start=2):
        reference = str(row.get(header_map["test reference"], "")).strip()
        title = str(row.get(header_map["description"], "")).strip()
        raw_subject = str(row.get(header_map["subject"], "")).strip().upper()
        if not reference and not title and not raw_subject:
            continue
        subject = subject_aliases.get(raw_subject)
        if not reference or not title or not subject:
            raise HTTPException(400, f"Row {number} needs a valid Test Reference, Description and Subject")
        existing = con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference=?", (reference,)
        ).fetchone()
        priority = (optional(row, "cat priority") or (existing["cat_priority"] if existing else None) or
                    ("LOW" if "OMET" in title.upper() or "DATA SUFFICIENCY" in title.upper() else "MEDIUM")).upper()
        if priority not in ("HIGH", "MEDIUM", "LOW"):
            raise HTTPException(400, f"Row {number} has invalid CAT Priority")
        category = optional(row, "category") or (existing["category"] if existing else None)
        group = optional(row, "canonical topic group") or (existing["canonical_topic_group"] if existing else None)
        topic = optional(row, "canonical topic") or (existing["canonical_topic"] if existing else None)
        level = optional(row, "level") or (existing["level"] if existing else "FOUNDATION")
        cat_core = int(priority != "LOW")
        con.execute(
            """
            INSERT INTO time_foundation_tests(
                test_reference,provider_title,subject,level,category,
                canonical_topic_group,canonical_topic,cat_priority,cat_core,imported
            ) VALUES(?,?,?,?,?,?,?,?,?,1)
            ON CONFLICT(test_reference) DO UPDATE SET
                provider_title=excluded.provider_title,subject=excluded.subject,
                level=excluded.level,category=excluded.category,
                canonical_topic_group=excluded.canonical_topic_group,
                canonical_topic=excluded.canonical_topic,cat_priority=excluded.cat_priority,
                cat_core=excluded.cat_core,active=1,imported=1,updated_at=CURRENT_TIMESTAMP
            """,
            (reference, title, subject, level, category, group, topic, priority, cat_core),
        )
        if existing:
            updated += 1
        else:
            created += 1
    if created + updated == 0:
        raise HTTPException(400, "The CSV did not contain any test rows")
    return {"created": created, "updated": updated}


def add_custom_study_material(con: sqlite3.Connection, payload: dict[str, Any]) -> str:
    """Create one reusable USER resource from Replace Material or Settings."""
    assignment_id = int(payload.get("assignment_id", 0))
    assignment = None
    topic_id = 0
    if assignment_id:
        assignment = con.execute(
            """
            SELECT assignment.*,task.subject AS task_subject,task.topic AS task_topic,
                   task.topic_id,task.difficulty,task.date,task.kind,task.aimcat_schedule_id
            FROM task_resource_assignments assignment
            JOIN tasks task ON task.id=assignment.task_id
            WHERE assignment.id=? AND task.archived=0
            """,
            (assignment_id,),
        ).fetchone()
        if not assignment:
            raise HTTPException(404, "Task material assignment not found")
        topic_id = int(assignment["topic_id"] or 0)
        stage = assignment["stage"]
        source_subject = assignment["task_subject"]
        default_difficulty = assignment["difficulty"] or "FOUNDATION"
    else:
        topic_id = int(payload.get("topic_id", 0))
        topic_row = con.execute("SELECT * FROM topics WHERE id=?", (topic_id,)).fetchone()
        if not topic_row:
            raise HTTPException(404, "Study topic not found")
        stage = str(payload.get("stage", "")).strip().upper()
        if stage not in ("LEARN", "PRACTICE", "PYQ"):
            raise HTTPException(400, "Choose Learn, Practice or PYQ")
        source_subject = topic_row["subject"]
        default_difficulty = topic_row["progression_level"] or "FOUNDATION"
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    url = str(payload.get("url", "")).strip()
    platform_path = str(payload.get("platform_path", "")).strip()
    if not title:
        raise HTTPException(400, "Material name is required")
    if len(title) > 180 or len(description) > 1000 or len(platform_path) > 500:
        raise HTTPException(400, "Custom material details are too long")
    if not url and not platform_path:
        raise HTTPException(400, "Add a URL or instructions for where to find the material")
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(400, "Material URL must begin with http:// or https://")
    resource_type = str(payload.get("type", "OTHER")).strip().upper()
    allowed_types = {"VIDEO", "ARTICLE", "COURSE", "QUESTION_BANK", "NOTES", "PDF", "OTHER"}
    if resource_type not in allowed_types:
        raise HTTPException(400, "Unknown custom material type")
    difficulty = str(payload.get("difficulty", default_difficulty)).strip().upper()
    if difficulty not in ("FOUNDATION", "INTERMEDIATE", "CAT_LEVEL", "TIMED", "MIXED"):
        raise HTTPException(400, "Unknown difficulty level")
    access = str(payload.get("access", "FREE")).strip().upper()
    if access not in ("FREE", "SUBSCRIPTION"):
        raise HTTPException(400, "Access must be Free or Subscription")
    subject = "QA" if source_subject in ("Quant", "QA") else source_subject
    resource_id = f"user-{uuid.uuid4().hex}"
    con.execute(
        """
        INSERT INTO study_resources(
            id,provider,title,description,subject,type,url,platform_path,free,
            requires_subscription,difficulty,active,last_verified_at
        ) VALUES(?,'USER',?,?,?,?,?,?,?,?,?,1,?)
        """,
        (
            resource_id, title, description, subject, resource_type, url or None,
            platform_path or None, int(access == "FREE"), int(access == "SUBSCRIPTION"),
            difficulty, current_app_date().isoformat(),
        ),
    )
    con.execute(
        """
        INSERT INTO user_resource_access(resource_provider,enabled,subscription_name,notes)
        VALUES('USER',1,'My study material','Custom resources added from Settings or Replace Material')
        ON CONFLICT(resource_provider) DO UPDATE SET enabled=1,updated_at=CURRENT_TIMESTAMP
        """
    )
    if topic_id:
        con.execute(
            """
            INSERT OR IGNORE INTO topic_resource_maps(topic_id,resource_id,purpose,priority,phase)
            VALUES(?,?,?,50,'ALL')
            """,
            (topic_id, resource_id, stage),
        )
    if assignment:
        con.execute(
            """
            UPDATE task_resource_assignments
            SET resource_id=?,manual_override=1,
                selected_reason='Custom material added and selected by user',updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            (resource_id, assignment_id),
        )
    return resource_id


def topic_for_time_test(con: sqlite3.Connection, test_row: sqlite3.Row, task_row: sqlite3.Row | None):
    if task_row and task_row["topic_id"]:
        return con.execute("SELECT * FROM topics WHERE id=?", (task_row["topic_id"],)).fetchone()
    exact_name = TIME_TOPIC_NAMES.get(test_row["canonical_topic"])
    if exact_name:
        return match_topic(con, "Quant", exact_name)
    area = TIME_GROUP_AREAS.get(test_row["canonical_topic_group"])
    if area:
        return con.execute(
            "SELECT * FROM topics WHERE subject='Quant' AND area=? ORDER BY mastery_score,accuracy,confidence,id LIMIT 1",
            (area,),
        ).fetchone()
    category_names = {
        "TABLES": "Tables", "LINE_GRAPHS": "Charts", "BAR_STACK_GRAPHS": "Charts",
        "PIE_CHARTS": "Charts", "GAMES_TOURNAMENTS": "Games and tournaments",
        "NETWORKS": "Routes / networks", "CASELETS": "Caselets",
        "REASONING_BASED_DI": "Mixed DI-LR",
        "DISTRIBUTION_SELECTION_COMPARISON": "Distribution",
    }
    name = category_names.get(test_row["category"])
    return match_topic(con, "DILR", name) if name else None


def record_time_foundation_result(con: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    test_id = int(payload.get("test_id", 0))
    task_id = int(payload.get("task_id", 0)) or None
    test_row = con.execute("SELECT * FROM time_foundation_tests WHERE id=? AND active=1", (test_id,)).fetchone()
    if not test_row:
        raise HTTPException(404, "T.I.M.E. Foundation test not found")
    task_row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone() if task_id else None
    if task_row and task_row["time_foundation_test_id"] != test_id:
        raise HTTPException(400, "This test is not assigned to that task")
    attempted = int(payload.get("attempted", 0))
    correct = int(payload.get("correct", 0))
    time_spent = int(payload.get("time_spent", 0))
    confidence = int(payload.get("confidence", 3))
    if attempted <= 0 or correct < 0 or correct > attempted:
        raise HTTPException(400, "Attempted must be positive and correct cannot exceed attempted")
    if time_spent < 0 or not 1 <= confidence <= 5:
        raise HTTPException(400, "Use a non-negative time and confidence from 1 to 5")
    attempted_on = str(payload.get("attempted_on") or (task_row["date"] if task_row else current_app_date().isoformat()))
    try:
        date.fromisoformat(attempted_on)
    except ValueError as exc:
        raise HTTPException(400, "Attempt date must be YYYY-MM-DD") from exc
    accuracy = round(correct * 100 / attempted, 1)
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    high = float(settings.get("timeFoundationAdvanceAccuracy", "85"))
    low = float(settings.get("timeFoundationContinueAccuracy", "70"))
    confidence_gate = int(settings.get("timeFoundationConfidence", "4"))
    outcome = "ADVANCE" if accuracy >= high and confidence >= confidence_gate else "CONTINUE" if accuracy >= low else "REPAIR"
    cursor = con.execute(
        """
        INSERT INTO time_foundation_attempts(
            test_id,task_id,attempted_on,attempted,correct,accuracy,time_spent,confidence,notes,outcome
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (test_id, task_id, attempted_on, attempted, correct, accuracy, time_spent,
         confidence, str(payload.get("notes", "")), outcome),
    )
    attempt_id = int(cursor.lastrowid)
    topic_row = topic_for_time_test(con, test_row, task_row)
    if topic_row:
        con.execute(
            """
            INSERT INTO topic_performance_events(
                topic_id,source_type,source_id,occurred_on,attempted,correct,accuracy,
                time_spent,confidence,difficulty,metadata
            ) VALUES(?,?,?,?,?,?,?,?,?,'FOUNDATION',?)
            """,
            (topic_row["id"], "TIME_FOUNDATION", attempt_id, attempted_on, attempted,
             correct, accuracy, time_spent, confidence,
             json.dumps({"test_reference": test_row["test_reference"], "outcome": outcome}, sort_keys=True)),
        )
        recompute_topic_from_events(
            con, int(topic_row["id"]), attempted_on, task_id, accuracy, confidence, outcome,
        )
        updated_topic = con.execute("SELECT * FROM topics WHERE id=?", (topic_row["id"],)).fetchone()
        if outcome != "ADVANCE":
            reason = (
                f"{test_row['test_reference']} needs concept repair ({accuracy:g}%)."
                if outcome == "REPAIR" else
                f"{test_row['test_reference']} needs more targeted practice ({accuracy:g}%)."
            )
            add_adaptive_signal(
                con, updated_topic, "TIME_FOUNDATION", attempt_id,
                30 if outcome == "REPAIR" else 12, reason,
            )
            retarget_future_task_from_signal(con, updated_topic, attempted_on, reason)
    for future in con.execute(
        """SELECT * FROM tasks WHERE time_foundation_test_id=? AND date>? AND completed=0
           AND manual=0 AND rescheduled=0 AND archived=0 ORDER BY date""",
        (test_id, attempted_on),
    ).fetchall():
        replacement = choose_time_foundation_test(con, future["subject"], future["topic"])
        if replacement:
            con.execute(
                "UPDATE tasks SET time_foundation_test_id=? WHERE id=?",
                (replacement["id"], future["id"]),
            )
    return {"attempt_id": attempt_id, "accuracy": accuracy, "outcome": outcome}


def connect_error_to_adaptive_signal(con: sqlite3.Connection, error_id: int, payload: dict[str, Any]):
    subject = str(payload.get("subject", ""))
    topic_name = str(payload.get("topic", ""))
    if subject == "Mock":
        topic_row = con.execute(
            "SELECT * FROM topics WHERE LOWER(name)=LOWER(?) OR LOWER(?) LIKE '%'||LOWER(name)||'%' ORDER BY importance DESC LIMIT 1",
            (topic_name, topic_name),
        ).fetchone()
    else:
        topic_row = match_topic(con, subject, topic_name)
    if topic_row:
        reason = f"Error log: {payload.get('error_type', 'reusable mistake')} in {topic_row['name']}."
        add_adaptive_signal(con, topic_row, "ERROR", error_id, 18, reason)
        retarget_future_task_from_signal(con, topic_row, str(payload.get("date") or current_app_date().isoformat()), reason)


def connect_mock_to_adaptive_signals(con: sqlite3.Connection, mock_id: int, payload: dict[str, Any]):
    for raw_topic in str(payload.get("weak_topics", "")).split(","):
        topic_name = raw_topic.strip()
        if not topic_name:
            continue
        topic_row = con.execute(
            "SELECT * FROM topics WHERE LOWER(name)=LOWER(?) OR LOWER(?) LIKE '%'||LOWER(name)||'%' ORDER BY importance DESC LIMIT 1",
            (topic_name, topic_name),
        ).fetchone()
        if topic_row:
            reason = f"Mock weakness: {topic_row['name']} was explicitly flagged."
            add_adaptive_signal(con, topic_row, "MOCK", mock_id, 28, reason)
            retarget_future_task_from_signal(con, topic_row, str(payload.get("date") or current_app_date().isoformat()), reason)
    section_map = (("Quant", "qa_percentile"), ("DILR", "dilr_percentile"), ("VARC", "varc_percentile"))
    for subject, key in section_map:
        percentile = float(payload.get(key, 0) or 0)
        if percentile <= 0 or percentile >= 75:
            continue
        weakest = con.execute(
            "SELECT * FROM topics WHERE subject=? ORDER BY mastery_score,accuracy,confidence LIMIT 1",
            (subject,),
        ).fetchone()
        if weakest:
            reason = f"Mock {subject} percentile {percentile:g} exposed a section weakness."
            add_adaptive_signal(
                con, weakest, "MOCK", mock_id, min(25, (75 - percentile) / 2 + 8),
                reason,
            )
            retarget_future_task_from_signal(con, weakest, str(payload.get("date") or current_app_date().isoformat()), reason)


def aimcat_payload(con: sqlite3.Connection, reference_day: str) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    mock_rows = rows(con, "SELECT * FROM mocks ORDER BY date,id")
    mocks_by_id = {item["id"]: item for item in mock_rows}
    schedules = []
    for raw in con.execute("SELECT * FROM aimcat_schedules ORDER BY start_date,id").fetchall():
        item = dict(raw)
        item["status"] = status_for(raw, reference_day)
        item["diagnosis"] = decode_diagnosis(item["diagnosis_json"])
        item["result"] = mocks_by_id.get(item["mock_id"])
        con.execute(
            "UPDATE aimcat_schedules SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status!=?",
            (item["status"], item["id"], item["status"]),
        )
        schedules.append(item)
    future = [item for item in schedules if item["status"] not in ("PAST", "COMPLETED", "MISSED") and (item["planned_attempt_date"] or item["end_date"]) >= reference_day]
    completed = [item for item in schedules if item["actual_attempt_date"]]
    next_item = future[0] if future else None
    last_item = completed[-1] if completed else None
    trend = rolling_aimcat_trend(mock_rows)
    return schedules, {
        "next": next_item,
        "last": last_item,
        "firstDiagnostic": "AIMCAT2714",
        "finalScheduledEnd": "2026-11-18",
        "catDate": CAT_DATE,
        "consolidationDays": 11,
        "portalUrl": row_map(con.execute("SELECT key,value FROM settings").fetchall()).get("timePortalUrl", "https://www.time4education.com/"),
    }, trend


def archive_replaceable_planner_tasks(con: sqlite3.Connection, day: str, exclude_aimcat_id: int | None = None):
    planner = con.execute(
        """SELECT * FROM tasks WHERE date=? AND archived=0 AND manual=0 AND rescheduled=0
           AND completed=0 AND kind IN ('practice','sectional','mock','analysis','revision')""",
        (day,),
    ).fetchall()
    if exclude_aimcat_id is not None:
        planner = [item for item in planner if item["aimcat_schedule_id"] != exclude_aimcat_id]
    for item in planner:
        manual_material = con.execute(
            "SELECT 1 FROM task_resource_assignments WHERE task_id=? AND manual_override=1",
            (item["id"],),
        ).fetchone()
        if manual_material:
            raise HTTPException(400, "This date contains a protected material override; move that task first")
    if planner:
        con.executemany("UPDATE tasks SET archived=1 WHERE id=?", ((item["id"],) for item in planner))


def restore_standard_plan(con: sqlite3.Connection, day: str):
    active = con.execute(
        """SELECT 1 FROM tasks WHERE date=? AND archived=0 AND manual=0
           AND kind IN ('practice','sectional','mock','analysis','revision') LIMIT 1""",
        (day,),
    ).fetchone()
    if not active:
        for item in plan_rows(con, day):
            insert_task(con, item)
    con.execute("INSERT OR IGNORE INTO plan_days(date) VALUES(?)", (day,))


def prioritize_analysis_carryover(con: sqlite3.Connection, day: str):
    """Carry unfinished AIMCAT analysis into the next day without touching user work."""
    previous = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    schedule = con.execute(
        """SELECT * FROM aimcat_schedules
           WHERE actual_attempt_date=? AND analysis_completed=0 AND skipped=0
           ORDER BY id DESC LIMIT 1""",
        (previous,),
    ).fetchone()
    if not schedule:
        return
    analysis_task = con.execute(
        """SELECT * FROM tasks WHERE aimcat_schedule_id=? AND kind='analysis'
           AND completed=0 AND archived=0 AND manual=0 AND rescheduled=0 LIMIT 1""",
        (schedule["id"],),
    ).fetchone()
    if not analysis_task or analysis_task["date"] == day:
        return
    ordinary = con.execute(
        """SELECT * FROM tasks WHERE date=? AND archived=0 AND manual=0 AND rescheduled=0
           AND completed=0 AND kind IN ('practice','revision') ORDER BY start_time,id""",
        (day,),
    ).fetchall()
    by_subject = {item["subject"]: item for item in ordinary}
    if not all(subject in by_subject for subject in ("Quant", "DILR", "VARC", "Revision")):
        return
    protected = con.execute(
        """SELECT 1 FROM task_resource_assignments WHERE manual_override=1 AND task_id IN (?,?,?,?)""",
        tuple(by_subject[subject]["id"] for subject in ("Quant", "DILR", "VARC", "Revision")),
    ).fetchone()
    if protected:
        return
    con.execute("UPDATE tasks SET archived=1 WHERE id IN (?,?)", (by_subject["Quant"]["id"], by_subject["Revision"]["id"]))
    con.execute(
        """INSERT INTO task_reschedule_history(task_id,from_date,to_date,from_start_time,to_start_time,grouped)
           VALUES(?,?,?,?,?,0)""",
        (analysis_task["id"], analysis_task["date"], day, analysis_task["start_time"], "18:00"),
    )
    con.execute(
        "UPDATE tasks SET date=?,start_time='18:00',duration=180,rescheduled=1 WHERE id=?",
        (day, analysis_task["id"]),
    )
    for subject, start_time in (("DILR", "21:00"), ("VARC", "22:30")):
        task_id = int(by_subject[subject]["id"])
        con.execute("UPDATE tasks SET start_time=?,duration=90 WHERE id=?", (start_time, task_id))
        con.execute("DELETE FROM task_resource_assignments WHERE task_id=? AND manual_override=0", (task_id,))
        assign_task_resources(con, task_id)


def set_aimcat_attempt_date(con: sqlite3.Connection, schedule_id: int, planned_date: str, *, convert_past: bool = False):
    try:
        date.fromisoformat(planned_date)
    except ValueError:
        raise HTTPException(400, "Attempt date must use YYYY-MM-DD format") from None
    schedule = con.execute("SELECT * FROM aimcat_schedules WHERE id=?", (schedule_id,)).fetchone()
    if not schedule:
        raise HTTPException(404, "AIMCAT not found")
    if schedule["actual_attempt_date"]:
        raise HTTPException(400, "A completed AIMCAT cannot be replanned")
    converted = bool(schedule["converted_to_additional"] or convert_past)
    if schedule["historical"] and not converted:
        raise HTTPException(400, "Convert this past AIMCAT to an additional mock first")
    if not converted and not (schedule["start_date"] <= planned_date <= schedule["end_date"]):
        raise HTTPException(400, "Attempt date must stay inside the official AIMCAT availability window")
    if converted and planned_date < PREP_START_DATE:
        raise HTTPException(400, "Additional mocks must be planned on or after preparation starts")
    old_date = schedule["planned_attempt_date"]
    lifecycle = con.execute(
        """SELECT * FROM tasks WHERE aimcat_schedule_id=? AND archived=0 AND completed=0
           ORDER BY start_time,id""",
        (schedule_id,),
    ).fetchall()
    archive_replaceable_planner_tasks(con, planned_date, schedule_id)
    con.execute(
        """UPDATE aimcat_schedules SET planned_attempt_date=?,manual_override=1,
           converted_to_additional=?,skipped=0,status='PLANNED',updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (planned_date, int(converted), schedule_id),
    )
    if lifecycle:
        for item in lifecycle:
            con.execute(
                """INSERT INTO task_reschedule_history(
                   task_id,from_date,to_date,from_start_time,to_start_time,grouped
                   ) VALUES(?,?,?,?,?,1)""",
                (item["id"], item["date"], planned_date, item["start_time"], item["start_time"]),
            )
            con.execute("UPDATE tasks SET date=?,rescheduled=1 WHERE id=?", (planned_date, item["id"]))
    else:
        for item in plan_rows(con, planned_date):
            insert_task(con, item)
    con.execute("INSERT OR IGNORE INTO plan_days(date) VALUES(?)", (planned_date,))
    if old_date and old_date != planned_date:
        restore_standard_plan(con, old_date)


def record_aimcat_result(con: sqlite3.Connection, schedule_id: int, payload: dict[str, Any]):
    schedule = con.execute("SELECT * FROM aimcat_schedules WHERE id=?", (schedule_id,)).fetchone()
    if not schedule:
        raise HTTPException(404, "AIMCAT not found")
    attempt_date = str(payload.get("date") or schedule["planned_attempt_date"] or "")
    converted = bool(schedule["converted_to_additional"])
    if not converted and not (schedule["start_date"] <= attempt_date <= schedule["end_date"]):
        raise HTTPException(400, "Actual attempt date must stay inside the official availability window")
    numeric = [
        "overall_score", "overall_percentile", "varc_score", "varc_percentile", "dilr_score",
        "dilr_percentile", "qa_score", "qa_percentile", "varc_attempts", "dilr_attempts",
        "qa_attempts", "varc_correct", "dilr_correct", "qa_correct", "varc_incorrect",
        "dilr_incorrect", "qa_incorrect", "easy_missed", "def_errors", "time_waste_questions",
        "poor_dilr_selections", "guessing_errors", "class_a", "class_b", "class_c", "class_d",
        "class_e", "class_f", "class_g",
    ]
    for key in numeric:
        value = float(payload.get(key, 0) or 0)
        if value < 0:
            raise HTTPException(400, f"{key.replace('_', ' ').title()} cannot be negative")
    for section in ("varc", "dilr", "qa"):
        attempted = int(payload.get(f"{section}_attempts", 0) or 0)
        correct = int(payload.get(f"{section}_correct", 0) or 0)
        incorrect = int(payload.get(f"{section}_incorrect", attempted - correct) or 0)
        if correct + incorrect > attempted:
            raise HTTPException(400, f"{section.upper()} correct + incorrect cannot exceed attempts")
        payload[f"{section}_incorrect"] = incorrect
    recent = rows(
        con,
        """SELECT mocks.* FROM mocks JOIN aimcat_schedules schedule ON schedule.mock_id=mocks.id
           WHERE schedule.id!=? ORDER BY mocks.date DESC LIMIT 2""",
        (schedule_id,),
    )
    payload = {**payload, "date": attempt_date, "provider": "TIME", "name": schedule["test_ref"], "aimcat_schedule_id": schedule_id}
    diagnosis = diagnosis_for(payload, list(reversed(recent)))
    columns = [
        "date","provider","name","overall_score","overall_percentile","varc_score","varc_percentile",
        "dilr_score","dilr_percentile","qa_score","qa_percentile","varc_attempts","dilr_attempts",
        "qa_attempts","varc_correct","dilr_correct","qa_correct","easy_missed","def_errors",
        "weak_topics","strategy_next","notes","aimcat_schedule_id","varc_incorrect","dilr_incorrect",
        "qa_incorrect","time_waste_questions","poor_dilr_selections","guessing_errors","topics_involved",
        "class_a","class_b","class_c","class_d","class_e","class_f","class_g",
    ]
    existing = con.execute("SELECT id FROM mocks WHERE aimcat_schedule_id=?", (schedule_id,)).fetchone()
    if existing:
        assignments = ",".join(f"{column}=?" for column in columns)
        con.execute(f"UPDATE mocks SET {assignments} WHERE id=?", tuple(payload.get(column, "") for column in columns) + (existing["id"],))
        mock_id = int(existing["id"])
    else:
        mock_id = insert_named(con, "mocks", payload, columns)
    con.execute(
        """UPDATE aimcat_schedules SET actual_attempt_date=?,mock_id=?,status='ANALYSIS_DUE',
           analysis_completed=0,diagnosis_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (attempt_date, mock_id, encode_diagnosis(diagnosis), schedule_id),
    )
    con.execute(
        "UPDATE tasks SET completed=1,completion=100,actual_duration=duration WHERE aimcat_schedule_id=? AND kind='mock' AND archived=0",
        (schedule_id,),
    )
    con.execute(
        """UPDATE task_resource_assignments SET completed=1,updated_at=CURRENT_TIMESTAMP
           WHERE task_id IN (SELECT id FROM tasks WHERE aimcat_schedule_id=? AND kind='mock' AND archived=0)""",
        (schedule_id,),
    )
    connect_mock_to_adaptive_signals(con, mock_id, payload)
    for section in diagnosis["persistent_sections"]:
        subject = "Quant" if section == "QA" else section
        weakest = con.execute(
            "SELECT * FROM topics WHERE subject=? ORDER BY mastery_score,accuracy,confidence LIMIT 1",
            (subject,),
        ).fetchone()
        if weakest:
            reason = f"Rolling three-AIMCAT weakness: {section} has remained below 75 percentile."
            add_adaptive_signal(con, weakest, "MOCK", mock_id, 35, reason)
            retarget_future_task_from_signal(con, weakest, attempt_date, reason)
    return diagnosis


def ensure_plan(con: sqlite3.Connection, day: str):
    if con.execute("SELECT 1 FROM plan_days WHERE date=?", (day,)).fetchone() or day > "2026-11-29": return
    for row in plan_rows(con, day): insert_task(con, row)
    con.execute("INSERT OR IGNORE INTO plan_days(date) VALUES(?)", (day,))


def rows(con: sqlite3.Connection, query: str, values=()):
    return [dict(row) for row in con.execute(query, values).fetchall()]


def time_foundation_payload(con: sqlite3.Connection) -> list[dict[str, Any]]:
    settings = row_map(con.execute("SELECT key,value FROM settings").fetchall())
    portal = settings.get("timePortalUrl", "https://www.time4education.com/")
    catalog = rows(
        con,
        """
        SELECT test.*,
               attempt.id AS last_attempt_id,attempt.attempted_on AS last_attempt,
               attempt.attempted,attempt.correct,attempt.accuracy,
               attempt.time_spent,attempt.confidence,attempt.outcome,
               CASE WHEN attempt.id IS NULL THEN 'Not attempted' ELSE 'Attempted' END AS status
        FROM time_foundation_tests test
        LEFT JOIN time_foundation_attempts attempt ON attempt.id=(
            SELECT latest.id FROM time_foundation_attempts latest
            WHERE latest.test_id=test.id ORDER BY latest.attempted_on DESC,latest.id DESC LIMIT 1
        )
        WHERE test.active=1 ORDER BY
            CASE test.cat_priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
            test.subject,test.test_reference
        """,
    )
    for item in catalog:
        item["url"] = portal
        item["advance_accuracy"] = float(settings.get("timeFoundationAdvanceAccuracy", "85"))
        item["confidence_gate"] = int(settings.get("timeFoundationConfidence", "4"))
    return catalog


def enrich_tasks_with_resources(con: sqlite3.Connection, task_rows: list[dict[str, Any]]):
    assignments = rows(
        con,
        """
        SELECT tra.id AS assignment_id,tra.task_id,tra.stage,tra.stage_order,
               tra.estimated_minutes,tra.target_count,tra.accuracy_target,
               tra.selected_reason,tra.manual_override,tra.completed AS stage_completed,
               sr.id AS resource_id,sr.provider,sr.title,sr.description,sr.subject AS resource_subject,
               sr.type AS resource_type,sr.url,sr.platform_path,sr.free,
               sr.requires_subscription,sr.difficulty
        FROM task_resource_assignments tra
        JOIN study_resources sr ON sr.id=tra.resource_id
        JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
        ORDER BY tra.task_id,tra.stage_order
        """,
    )
    results = {
        item["task_id"]: item
        for item in rows(con, "SELECT * FROM task_results ORDER BY task_id")
    }
    by_task: dict[int, list[dict[str, Any]]] = {}
    for assignment in assignments:
        by_task.setdefault(assignment["task_id"], []).append(assignment)
    tests = {item["id"]: item for item in time_foundation_payload(con)}
    for task_row in task_rows:
        task_row["resource_stages"] = by_task.get(task_row["id"], [])
        task_row["result"] = results.get(task_row["id"])
        task_row["time_foundation_test"] = tests.get(task_row.get("time_foundation_test_id"))


def task_resource_options(con: sqlite3.Connection, task_rows: list[dict[str, Any]]):
    options: dict[str, list[dict[str, Any]]] = {}
    for task_row in task_rows:
        for stage, _, _ in stage_plan(task_row):
            candidates = resource_candidates(con, task_row, stage)
            if not candidates:
                continue
            options[f"{task_row['id']}:{stage}"] = [
                {
                    "id": item["id"], "provider": item["provider"], "title": item["title"],
                    "url": item["url"], "platform_path": item["platform_path"],
                    "type": item["type"], "free": item["free"],
                    "requires_subscription": item["requires_subscription"],
                }
                for item in candidates
            ]
    return options


def minutes_from_clock(value: str) -> int:
    try:
        hour, minute = (int(part) for part in value.split(":"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Start time must use HH:MM format") from None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise HTTPException(400, "Start time must be a valid 24-hour time")
    return hour * 60 + minute


def clock_from_minutes(value: int) -> str:
    return f"{value // 60 % 24:02d}:{value % 60:02d}"


def reschedule_task(con: sqlite3.Connection, task_id: int, to_date: str, to_start_time: str):
    try:
        date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(400, "Target date must use YYYY-MM-DD format") from None
    new_start = minutes_from_clock(to_start_time)
    selected = con.execute("SELECT * FROM tasks WHERE id=? AND archived=0", (task_id,)).fetchone()
    if not selected:
        raise HTTPException(404, "Task not found")
    if selected["completed"]:
        raise HTTPException(400, "Completed tasks cannot be moved; reopen the task first")
    if selected["aimcat_schedule_id"] and selected["kind"] == "mock":
        lifecycle_ids = [row["id"] for row in con.execute(
            "SELECT id FROM tasks WHERE aimcat_schedule_id=? AND archived=0 AND completed=0 ORDER BY start_time,id",
            (selected["aimcat_schedule_id"],),
        ).fetchall()]
        set_aimcat_attempt_date(con, int(selected["aimcat_schedule_id"]), to_date)
        return {"task_ids": lifecycle_ids, "grouped": len(lifecycle_ids) > 1, "date": to_date}

    mock_day = con.execute(
        "SELECT 1 FROM tasks WHERE date=? AND kind='mock' AND manual=0 AND archived=0",
        (selected["date"],),
    ).fetchone()
    if mock_day and selected["kind"] == "mock" and not selected["manual"]:
        task_rows = con.execute(
            """
            SELECT * FROM tasks
            WHERE date=? AND kind IN ('mock','analysis','revision') AND manual=0 AND completed=0 AND archived=0
            ORDER BY start_time,id
            """,
            (selected["date"],),
        ).fetchall()
    else:
        task_rows = [selected]

    base_start = min(minutes_from_clock(row["start_time"]) for row in task_rows)
    latest_finish = max(
        minutes_from_clock(row["start_time"]) - base_start + int(row["duration"])
        for row in task_rows
    )
    if new_start + latest_finish > 24 * 60:
        raise HTTPException(400, "The moved work must finish by midnight; choose an earlier start time")
    grouped = int(len(task_rows) > 1)
    moved_ids = []
    for task_row in task_rows:
        shifted_start = clock_from_minutes(new_start + minutes_from_clock(task_row["start_time"]) - base_start)
        if len(task_rows) == 1:
            shifted_start = to_start_time
        con.execute(
            """
            INSERT INTO task_reschedule_history(
                task_id,from_date,to_date,from_start_time,to_start_time,grouped
            ) VALUES(?,?,?,?,?,?)
            """,
            (task_row["id"], task_row["date"], to_date, task_row["start_time"], shifted_start, grouped),
        )
        con.execute(
            "UPDATE tasks SET date=?,start_time=?,rescheduled=1 WHERE id=?",
            (to_date, shifted_start, task_row["id"]),
        )
        moved_ids.append(int(task_row["id"]))
    return {"task_ids": moved_ids, "grouped": bool(grouped), "date": to_date}


def get_data(day: str) -> dict[str, Any]:
    with connection() as con:
        ensure_plan(con, day)
        prioritize_analysis_carryover(con, day)
        profile = row_map(con.execute("SELECT * FROM profile").fetchall())
        settings = row_map(con.execute("SELECT * FROM settings").fetchall())
        tasks = rows(con, "SELECT * FROM tasks WHERE archived=0 ORDER BY date,start_time")
        topics = rows(con, "SELECT * FROM topics ORDER BY subject,area,id")
        deadlines = rows(con, "SELECT * FROM deadlines ORDER BY date")
        mocks = rows(con, "SELECT * FROM mocks ORDER BY date")
        errors = rows(con, "SELECT * FROM errors ORDER BY date DESC,id DESC")
        aimcats, aimcat_meta, aimcat_trend = aimcat_payload(con, current_app_date().isoformat())
        enrich_tasks_with_resources(con, tasks)
        today_tasks = [x for x in tasks if x["date"] == day]
        due = sum(bool(x["next_revision"] and x["next_revision"] <= day) for x in topics)
        overdue_admin = sum(x["date"] >= PREP_START_DATE and x["date"] < day and not x["completed"] and x["kind"] not in ("practice","revision","mock","analysis") for x in tasks)
        missed_aimcats = sum(item["status"] == "MISSED" and not item["historical"] for item in aimcats)
        health_load = overdue_admin + due + missed_aimcats * 3
        status = "Significantly behind" if health_load > 7 else "Slightly behind" if health_load > 2 else "On track"
        quant_left = sum(x["subject"] == "Quant" and x["area"] == "Arithmetic" and x["status"] == "Not Started" for x in topics)
        start = date.fromisoformat(profile["employmentStart"])
        now = date.fromisoformat(day)
        work_months = (now.year-start.year)*12 + now.month-start.month - (1 if now.day < start.day else 0)
        revisions = rows(
            con,
            """
            SELECT rs.*,t.name AS topic,t.subject,t.progression_level
            FROM revision_schedule rs JOIN topics t ON t.id=rs.topic_id
            WHERE rs.status='PENDING' ORDER BY rs.due_date
            """,
        )
        next_mock = aimcat_meta["next"]["planned_attempt_date"] if aimcat_meta["next"] else "Not scheduled"
        return {
            "profile": profile, "settings": settings, "tasks": tasks, "topics": topics,
            "deadlines": deadlines, "mocks": mocks, "aimcats": aimcats,
            "aimcatMeta": aimcat_meta, "aimcatTrend": aimcat_trend, "errors": errors,
            "resources": rows(con, "SELECT * FROM resources ORDER BY recommended DESC,id"),
            "studyResources": rows(con, "SELECT * FROM study_resources ORDER BY free DESC,provider,title"),
            "resourceAccess": rows(con, "SELECT * FROM user_resource_access ORDER BY enabled DESC,resource_provider"),
            "topicResourceMaps": rows(con, "SELECT * FROM topic_resource_maps ORDER BY topic_id,purpose,priority"),
            "timeFoundationTests": time_foundation_payload(con),
            "taskResourceOptions": task_resource_options(con, tasks), "revisionSchedule": revisions,
            "dilrPerformance": dilr_performance(con), "varcAnalysis": varc_analysis(con),
            "resourceEffectiveness": resource_effectiveness(con), "resourceCoverage": coverage_report(con),
            "adaptiveSignals": rows(con, "SELECT signal.*,topic.name AS topic,topic.subject FROM adaptive_signals signal JOIN topics topic ON topic.id=signal.topic_id WHERE signal.resolved_at IS NULL ORDER BY signal.weight DESC"),
            "stories": rows(con, "SELECT * FROM stories ORDER BY id DESC"),
            "reviews": rows(con, "SELECT * FROM day_reviews ORDER BY date DESC"),
            "meta": {
                "today": day, "phase": phase_for(day), "countdown": (EXAM_DATE-now).days,
                "workMonths": work_months, "plannedMinutes": sum(x["duration"] for x in today_tasks),
                "completedMinutes": sum((x["actual_duration"] or x["duration"]) if x["completed"] else round(x["duration"]*x["completion"]/100) for x in today_tasks),
                "behind": {"label": status, "detail": f"{quant_left} Arithmetic blocks remain unstarted; {due} revisions are due; {missed_aimcats} scheduled AIMCATs missed."},
                "nextMock": next_mock, "revisionDue": due,
            },
        }


class Action(BaseModel):
    action: str
    payload: dict[str, Any] = {}


@app.get("/", include_in_schema=False)
def home():
    if not (UI_DIR / "index.html").exists():
        return {"status":"Frontend not built","next":"Run npm run build, then reload."}
    return FileResponse(UI_DIR / "index.html")


@app.get("/api/app")
def api_data(day: str | None = Query(None, alias="date")):
    return get_data(day or current_app_date().isoformat())


@app.post("/api/app")
def api_action(body: Action):
    p, action = body.payload, body.action
    with connection() as con:
        if action == "toggleTask":
            completed = int(bool(p.get("completed")))
            con.execute("UPDATE tasks SET completed=?,completion=?,actual_duration=CASE WHEN ?=1 AND actual_duration=0 THEN duration ELSE actual_duration END WHERE id=?", (completed,100 if completed else 0,completed,p["id"]))
            con.execute("UPDATE task_resource_assignments SET completed=?,updated_at=CURRENT_TIMESTAMP WHERE task_id=?", (completed,p["id"]))
            changed = con.execute("SELECT aimcat_schedule_id,kind FROM tasks WHERE id=?", (p["id"],)).fetchone()
            if changed and changed["aimcat_schedule_id"] and changed["kind"] in ("analysis", "revision"):
                field = "analysis_completed" if changed["kind"] == "analysis" else "resolve_completed"
                con.execute(f"UPDATE aimcat_schedules SET {field}=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (completed, changed["aimcat_schedule_id"]))
                if changed["kind"] == "analysis":
                    con.execute("UPDATE aimcat_schedules SET status=? WHERE id=? AND actual_attempt_date IS NOT NULL", ("COMPLETED" if completed else "ANALYSIS_DUE", changed["aimcat_schedule_id"]))
        elif action == "addMock":
            mock_id = insert_named(con, "mocks", p, ["date","provider","name","overall_score","overall_percentile","varc_score","varc_percentile","dilr_score","dilr_percentile","qa_score","qa_percentile","varc_attempts","dilr_attempts","qa_attempts","varc_correct","dilr_correct","qa_correct","easy_missed","def_errors","weak_topics","strategy_next","notes"])
            connect_mock_to_adaptive_signals(con, mock_id, p)
        elif action == "recordAimcatResult":
            record_aimcat_result(con, int(p.get("schedule_id", 0)), p)
        elif action == "planAimcat":
            set_aimcat_attempt_date(con, int(p.get("schedule_id", 0)), str(p.get("date", "")))
        elif action == "activatePastAimcat":
            set_aimcat_attempt_date(con, int(p.get("schedule_id", 0)), str(p.get("date", "")), convert_past=True)
        elif action == "skipAimcat":
            schedule_id = int(p.get("schedule_id", 0))
            schedule = con.execute("SELECT * FROM aimcat_schedules WHERE id=?", (schedule_id,)).fetchone()
            if not schedule:
                raise HTTPException(404, "AIMCAT not found")
            if schedule["actual_attempt_date"]:
                raise HTTPException(400, "A completed AIMCAT cannot be skipped")
            con.execute("UPDATE tasks SET archived=1 WHERE aimcat_schedule_id=? AND archived=0 AND completed=0", (schedule_id,))
            con.execute("UPDATE aimcat_schedules SET skipped=1,status='MISSED',updated_at=CURRENT_TIMESTAMP WHERE id=?", (schedule_id,))
            if schedule["planned_attempt_date"]:
                restore_standard_plan(con, schedule["planned_attempt_date"])
        elif action == "markAimcatAnalysis":
            schedule_id = int(p.get("schedule_id", 0))
            schedule = con.execute("SELECT * FROM aimcat_schedules WHERE id=?", (schedule_id,)).fetchone()
            if not schedule or not schedule["actual_attempt_date"]:
                raise HTTPException(400, "Record the AIMCAT result before completing analysis")
            analysis_completed = int(bool(p.get("analysis_completed", True)))
            resolve_completed = int(bool(p.get("resolve_completed", schedule["resolve_completed"])))
            con.execute(
                "UPDATE aimcat_schedules SET analysis_completed=?,resolve_completed=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (analysis_completed, resolve_completed, "COMPLETED" if analysis_completed else "ANALYSIS_DUE", schedule_id),
            )
            con.execute(
                """UPDATE tasks SET completed=?,completion=?,actual_duration=CASE WHEN ?=1 THEN duration ELSE 0 END
                   WHERE aimcat_schedule_id=? AND kind='analysis' AND archived=0""",
                (analysis_completed, 100 if analysis_completed else 0, analysis_completed, schedule_id),
            )
        elif action == "recordTimeFoundationResult":
            record_time_foundation_result(con, p)
        elif action == "importTimeFoundationTests":
            import_time_foundation_csv(con, str(p.get("csv", "")))
        elif action == "addCustomStudyMaterial":
            add_custom_study_material(con, p)
        elif action == "addError":
            if str(p.get("subject", "")) == "VARC":
                p["error_type"] = normalize_varc_error(str(p.get("error_type", "OTHER")))
            error_id = insert_named(con,"errors",p,["date","subject","topic","source","question_ref","error_type","incorrect_approach","correct_insight","rule_next"])
            connect_error_to_adaptive_signal(con, error_id, p)
        elif action == "addResource": insert_named(con,"resources",p,["name","url","type","tags","note"])
        elif action == "addStory": insert_named(con,"stories",p,["title","tags","situation","problem","role","actions","stakeholders","leadership","impact","challenges","outcome","learning","usefulness"])
        elif action == "addTask":
            p.update(manual=1,kind="manual",completed=0,completion=0,actual_duration=0)
            insert_task(con,p)
        elif action == "updateTopic":
            con.execute("UPDATE topics SET status=?,confidence=?,accuracy=?,attempted=?,correct=?,last_practised=?,next_revision=? WHERE id=?", tuple(p.get(k) for k in ["status","confidence","accuracy","attempted","correct","last_practised","next_revision","id"]))
        elif action == "updateDeadline": con.execute("UPDATE deadlines SET title=?,date=?,status=?,note=? WHERE id=?", tuple(p.get(k) for k in ["title","date","status","note","id"]))
        elif action == "settings":
            merged = row_map(con.execute("SELECT key,value FROM settings").fetchall()) | {
                key: str(value) for key, value in p.items()
            }
            try:
                foundation_low = float(merged.get("timeFoundationContinueAccuracy", "70"))
                foundation_high = float(merged.get("timeFoundationAdvanceAccuracy", "85"))
                foundation_confidence = int(merged.get("timeFoundationConfidence", "4"))
            except ValueError as exc:
                raise HTTPException(400, "Foundation thresholds must be numeric") from exc
            if not 0 <= foundation_low < foundation_high <= 100 or not 1 <= foundation_confidence <= 5:
                raise HTTPException(400, "Use 0–100 accuracy thresholds with Continue below Advance, and confidence from 1–5")
            if merged.get("timeOmetAutoSchedule", "off") not in ("on", "off"):
                raise HTTPException(400, "OMET auto-scheduling must be on or off")
            for key,value in p.items():
                if key == "timePortalUrl" and value and not str(value).startswith(("https://", "http://")):
                    raise HTTPException(400, "T.I.M.E. portal URL must begin with http:// or https://")
                con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
                if key == "timePortalUrl" and value:
                    con.execute("UPDATE study_resources SET url=?,updated_at=CURRENT_TIMESTAMP WHERE id='time-aimcat-portal'", (str(value),))
        elif action == "setResourceAccess":
            provider = str(p.get("resource_provider", ""))
            if not con.execute("SELECT 1 FROM user_resource_access WHERE resource_provider=?", (provider,)).fetchone():
                raise HTTPException(404, "Unknown resource provider")
            con.execute(
                "UPDATE user_resource_access SET enabled=?,updated_at=CURRENT_TIMESTAMP WHERE resource_provider=?",
                (int(bool(p.get("enabled"))), provider),
            )
            refresh_disabled_assignments(con)
            if provider == "TIME":
                if p.get("enabled"):
                    con.execute("DELETE FROM settings WHERE key='timeFoundationPlannerVersion'")
                    initialize_time_foundation_assignments(con)
                else:
                    con.execute(
                        """UPDATE tasks SET time_foundation_test_id=NULL
                           WHERE manual=0 AND completed=0 AND archived=0 AND rescheduled=0
                             AND date>=?""",
                        (current_app_date().isoformat(),),
                    )
        elif action == "replaceTaskResource":
            assignment_id = int(p.get("assignment_id", 0))
            resource_id = str(p.get("resource_id", ""))
            assignment = con.execute(
                "SELECT * FROM task_resource_assignments WHERE id=?",
                (assignment_id,),
            ).fetchone()
            if not assignment:
                raise HTTPException(404, "Task material assignment not found")
            candidate = con.execute(
                """
                SELECT sr.id FROM study_resources sr
                JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
                WHERE sr.id=? AND sr.active=1
                """,
                (resource_id,),
            ).fetchone()
            task_row = con.execute("SELECT * FROM tasks WHERE id=?", (assignment["task_id"],)).fetchone()
            allowed = {item["id"] for item in resource_candidates(con, task_row, assignment["stage"])}
            if not candidate or resource_id not in allowed:
                raise HTTPException(400, "Replacement must be an enabled resource mapped to this task stage")
            con.execute(
                """
                UPDATE task_resource_assignments
                SET resource_id=?,manual_override=1,selected_reason='Selected with Replace Material',updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (resource_id, assignment_id),
            )
        elif action == "rescheduleTask":
            selected = con.execute("SELECT * FROM tasks WHERE id=? AND archived=0", (int(p.get("task_id", 0)),)).fetchone()
            if selected and selected["aimcat_schedule_id"] and selected["kind"] == "mock":
                set_aimcat_attempt_date(con, int(selected["aimcat_schedule_id"]), str(p.get("date", "")))
            else:
                reschedule_task(
                    con,
                    int(p.get("task_id", 0)),
                    str(p.get("date", "")),
                    str(p.get("start_time", "")),
                )
        elif action == "completeTaskWithResult":
            task_id = int(p.get("task_id", 0))
            attempted = int(p.get("attempted", 0))
            correct = int(p.get("correct", 0))
            time_spent = int(p.get("time_spent", 0))
            confidence = int(p.get("confidence", 3))
            notes = str(p.get("notes", ""))
            task_row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not task_row:
                raise HTTPException(404, "Task not found")
            if attempted < 0 or correct < 0 or correct > attempted:
                raise HTTPException(400, "Correct answers must be between zero and attempted answers")
            if time_spent < 0:
                raise HTTPException(400, "Time spent cannot be negative")
            if confidence < 1 or confidence > 5:
                raise HTTPException(400, "Confidence must be between 1 and 5")
            accuracy = round(correct * 100 / attempted, 1) if attempted else 0
            average_time = round(time_spent / attempted, 2) if attempted else 0
            dilr_sets_solved = int(p.get("dilr_sets_solved", 0)) if task_row["subject"] == "DILR" else 0
            if task_row["subject"] == "DILR" and (dilr_sets_solved < 0 or dilr_sets_solved > attempted):
                raise HTTPException(400, "DILR sets solved must be between zero and sets attempted")
            dilr_solved = int(dilr_sets_solved > 0) if task_row["subject"] == "DILR" else None
            dilr_representation = str(p.get("dilr_representation", "")) or None
            dilr_selectability = str(p.get("dilr_selectability", "")) or None
            varc_error_pattern = normalize_varc_error(str(p.get("varc_error_pattern", ""))) if task_row["subject"] == "VARC" and p.get("varc_error_pattern") else None
            con.execute(
                """
                INSERT INTO task_results(task_id,attempted,correct,time_spent,confidence,accuracy,average_time,notes,dilr_solved,dilr_representation,dilr_selectability,varc_error_pattern,dilr_sets_solved)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET
                    attempted=excluded.attempted,correct=excluded.correct,time_spent=excluded.time_spent,
                    confidence=excluded.confidence,accuracy=excluded.accuracy,
                    average_time=excluded.average_time,notes=excluded.notes,
                    dilr_solved=excluded.dilr_solved,dilr_representation=excluded.dilr_representation,
                    dilr_selectability=excluded.dilr_selectability,varc_error_pattern=excluded.varc_error_pattern,
                    dilr_sets_solved=excluded.dilr_sets_solved,
                    completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                """,
                (task_id, attempted, correct, time_spent, confidence, accuracy, average_time, notes,dilr_solved,dilr_representation,dilr_selectability,varc_error_pattern,dilr_sets_solved),
            )
            con.execute(
                "UPDATE tasks SET completed=1,completion=100,actual_duration=? WHERE id=?",
                (time_spent, task_id),
            )
            if task_row["aimcat_schedule_id"] and task_row["kind"] in ("analysis", "revision"):
                field = "analysis_completed" if task_row["kind"] == "analysis" else "resolve_completed"
                con.execute(f"UPDATE aimcat_schedules SET {field}=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_row["aimcat_schedule_id"],))
                if task_row["kind"] == "analysis":
                    con.execute("UPDATE aimcat_schedules SET status='COMPLETED' WHERE id=? AND actual_attempt_date IS NOT NULL", (task_row["aimcat_schedule_id"],))
            con.execute(
                "UPDATE task_resource_assignments SET completed=1,updated_at=CURRENT_TIMESTAMP WHERE task_id=?",
                (task_id,),
            )
            apply_task_result_to_topic(
                con,
                task_id,
                {
                    "attempted": attempted, "correct": correct, "time_spent": time_spent,
                    "confidence": confidence, "accuracy": accuracy,
                    "dilr_sets_solved": dilr_sets_solved, "dilr_representation": dilr_representation,
                    "dilr_selectability": dilr_selectability, "varc_error_pattern": varc_error_pattern,
                },
            )
        elif action == "closeDay":
            keys=["date","actual_hours","energy","focus","went_well","difficult","tomorrow"]
            con.execute("INSERT INTO day_reviews(date,actual_hours,energy,focus,went_well,difficult,tomorrow) VALUES(?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET actual_hours=excluded.actual_hours,energy=excluded.energy,focus=excluded.focus,went_well=excluded.went_well,difficult=excluded.difficult,tomorrow=excluded.tomorrow",tuple(p.get(k) for k in keys))
        else: raise HTTPException(400, "Unknown action")
    return {"ok": True}


def insert_named(con, table, payload, keys):
    values=[payload.get(k, 0 if k.endswith(("score","percentile","attempts","correct","missed","errors")) else "") for k in keys]
    cursor = con.execute(f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' for _ in keys)})",values)
    return int(cursor.lastrowid)


init_db()

# Mount last so /api routes retain precedence. Vite builds the React SPA here.
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="react-ui")
