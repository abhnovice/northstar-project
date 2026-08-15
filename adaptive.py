from __future__ import annotations

import sqlite3
from collections import Counter
from statistics import median
from typing import Any


PROGRESSION_LEVELS = ("FOUNDATION", "INTERMEDIATE", "CAT_LEVEL", "TIMED", "MIXED")

VARC_ERROR_PATTERNS = (
    "EXTREME_OPTION",
    "SCOPE_SHIFT",
    "UNSUPPORTED_INFERENCE",
    "AUTHOR_VIEW_VS_EXAMPLE",
    "CAUSE_EFFECT_REVERSAL",
    "PARTIALLY_CORRECT",
    "MISSED_QUALIFIER",
    "MISREAD_QUESTION",
    "TIME_PRESSURE",
    "CLOSE_CALL",
    "OTHER",
)


def progression_for(attempted: int, accuracy: float, confidence: int) -> str:
    """Return the highest justified level; low accuracy/confidence always pulls work back."""
    if attempted < 10 or accuracy < 60 or confidence <= 1:
        return "FOUNDATION"
    if attempted < 15 or accuracy < 70 or confidence <= 2:
        return "INTERMEDIATE"
    if attempted < 30 or accuracy < 80 or confidence <= 3:
        return "CAT_LEVEL"
    if attempted < 60 or accuracy < 85 or confidence <= 4:
        return "TIMED"
    return "MIXED"


def mastery_status(attempted: int, progression: str) -> str:
    if attempted <= 0:
        return "Not Started"
    if progression == "FOUNDATION":
        return "Learning"
    if progression in ("INTERMEDIATE", "CAT_LEVEL"):
        return "Practising"
    return "Strong"


def mastery_score(accuracy: float, confidence: int, progression: str) -> float:
    level_index = PROGRESSION_LEVELS.index(progression)
    return round(min(100, accuracy * 0.55 + confidence * 7 + level_index * 5), 1)


def normalize_varc_error(value: str | None) -> str:
    normalized = (value or "OTHER").strip().upper().replace("/", "_").replace("-", "_").replace(" ", "_")
    aliases = {
        "EXTREME": "EXTREME_OPTION",
        "SCOPE_EXPANSION": "SCOPE_SHIFT",
        "UNSUPPORTED": "UNSUPPORTED_INFERENCE",
        "MISSED_QUALIFIER": "MISSED_QUALIFIER",
        "MISREAD": "MISREAD_QUESTION",
        "TIME": "TIME_PRESSURE",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in VARC_ERROR_PATTERNS else "OTHER"


def resource_effectiveness(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in con.execute(
            """
            WITH provider_tasks AS (
                SELECT DISTINCT tr.task_id,sr.provider,tr.accuracy,tr.confidence
                FROM task_results tr
                JOIN task_resource_assignments tra ON tra.task_id=tr.task_id
                JOIN study_resources sr ON sr.id=tra.resource_id
            )
            SELECT provider,COUNT(*) AS tasks,
                   ROUND(CAST(AVG(accuracy) AS NUMERIC),1) AS average_accuracy,
                   ROUND(CAST(AVG(confidence) AS NUMERIC),1) AS average_confidence
            FROM provider_tasks
            GROUP BY provider
            ORDER BY tasks DESC,provider
            """
        ).fetchall()
    ]


def dilr_performance(con: sqlite3.Connection) -> list[dict[str, Any]]:
    result_rows = con.execute(
        """
        SELECT t.topic_id,tr.attempted,tr.correct,tr.time_spent,tr.confidence,tr.dilr_sets_solved
        FROM task_results tr JOIN tasks t ON t.id=tr.task_id
        WHERE t.subject='DILR' AND t.topic_id IS NOT NULL AND t.archived=0
        ORDER BY tr.completed_at
        """
    ).fetchall()
    by_topic: dict[int, list[sqlite3.Row]] = {}
    for row in result_rows:
        by_topic.setdefault(row["topic_id"], []).append(row)
    output = []
    for topic in con.execute("SELECT id,name,confidence,progression_level FROM topics WHERE subject='DILR' ORDER BY id"):
        samples = by_topic.get(topic["id"], [])
        attempted = sum(max(0, int(row["attempted"] or 0)) for row in samples)
        solved = sum(int(row["dilr_sets_solved"] or 0) for row in samples)
        times = [int(row["time_spent"]) for row in samples if row["time_spent"]]
        bank = con.execute(
            """
            SELECT sr.provider,sr.title,sr.url,sr.platform_path
            FROM topic_resource_maps trm
            JOIN study_resources sr ON sr.id=trm.resource_id AND sr.active=1
            JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
            WHERE trm.topic_id=? AND trm.purpose='PRACTICE'
            ORDER BY trm.priority LIMIT 1
            """,
            (topic["id"],),
        ).fetchone()
        output.append(
            {
                "topic_id": topic["id"],
                "category": topic["name"],
                "sets_attempted": attempted,
                "solved": solved,
                "solve_rate": round(solved * 100 / attempted, 1) if attempted else 0,
                "median_time": round(float(median(times)), 1) if times else 0,
                "confidence": topic["confidence"],
                "progression_level": topic["progression_level"],
                "primary_resource": dict(bank) if bank else None,
            }
        )
    return output


def varc_analysis(con: sqlite3.Connection) -> dict[str, Any]:
    raw_patterns = [row[0] for row in con.execute(
        """
        SELECT pattern FROM (
            SELECT error_type AS pattern,date AS occurred FROM errors WHERE subject='VARC'
            UNION ALL
            SELECT tr.varc_error_pattern AS pattern,CAST(tr.completed_at AS TEXT) AS occurred
            FROM task_results tr JOIN tasks t ON t.id=tr.task_id
            WHERE t.subject='VARC' AND t.archived=0 AND tr.varc_error_pattern IS NOT NULL AND tr.varc_error_pattern!=''
        ) ORDER BY occurred DESC LIMIT 50
        """
    ).fetchall()]
    counts = Counter(normalize_varc_error(item) for item in raw_patterns)
    total = sum(counts.values())
    patterns = [
        {"pattern": name, "count": count, "percentage": round(count * 100 / total, 1) if total else 0}
        for name, count in counts.most_common()
    ]
    top = patterns[0]["pattern"] if patterns else None
    recommendations = {
        "SCOPE_SHIFT": "During RC review, compare the exact scope of the passage with every close option.",
        "UNSUPPORTED_INFERENCE": "Require a specific line or unavoidable implication before accepting an inference.",
        "EXTREME_OPTION": "Circle absolute language and verify whether the passage supports that strength.",
        "MISSED_QUALIFIER": "Underline qualifiers in both the stem and the relevant passage sentence.",
        "TIME_PRESSURE": "Use one timed RC passage, then review selection and pacing separately.",
    }
    return {
        "total_errors": total,
        "patterns": patterns,
        "most_common": top,
        "recommendation": recommendations.get(top, "Review one RC passage and explicitly classify every close-option error.") if top else "Log VARC errors to unlock pattern recommendations.",
    }


def coverage_report(con: sqlite3.Connection) -> dict[str, Any]:
    issues: list[str] = []
    topics = con.execute("SELECT id,subject,name,practice_only FROM topics WHERE subject IN ('Quant','DILR','VARC') ORDER BY subject,id").fetchall()
    for topic in topics:
        purposes = {
            row[0]
            for row in con.execute(
                """
                SELECT DISTINCT trm.purpose FROM topic_resource_maps trm
                JOIN study_resources sr ON sr.id=trm.resource_id AND sr.active=1
                JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
                WHERE trm.topic_id=?
                """,
                (topic["id"],),
            )
        }
        label = f"{topic['subject']} · {topic['name']}"
        if not topic["practice_only"] and "LEARN" not in purposes:
            issues.append(f"{label}: missing LEARN source")
        if "PRACTICE" not in purposes:
            issues.append(f"{label}: missing PRACTICE source")
        if "PYQ" not in purposes:
            issues.append(f"{label}: missing PYQ fallback")
    gmat = con.execute(
        """
        SELECT 1 FROM study_resources sr
        JOIN user_resource_access ura ON ura.resource_provider=sr.provider AND ura.enabled=1
        WHERE sr.subject='GMAT' AND sr.provider='GMAC' AND sr.type='DIAGNOSTIC' AND sr.active=1
        """
    ).fetchone()
    if not gmat:
        issues.append("GMAT: missing official GMAC diagnostic")
    return {"valid": not issues, "issues": issues, "topics_checked": len(topics), "resources_checked": con.execute("SELECT COUNT(*) FROM study_resources WHERE active=1").fetchone()[0]}
