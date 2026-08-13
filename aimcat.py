from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from statistics import mean
from typing import Any


PREP_START_DATE = "2026-08-12"
CAT_DATE = "2026-11-29"
FINAL_SCHEDULED_END = "2026-11-18"


def preferred_attempt_date(start_date: str, end_date: str) -> str:
    """Prefer the second window day; use the first convenient weekend otherwise."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    second = min(end, start + timedelta(days=1))
    if second.weekday() >= 5:
        return second.isoformat()
    weekend = next(
        (start + timedelta(days=offset) for offset in range((end - start).days + 1)
         if (start + timedelta(days=offset)).weekday() >= 5),
        None,
    )
    return (weekend or second).isoformat()


def status_for(row: sqlite3.Row | dict[str, Any], today: str) -> str:
    if row["historical"] and not row["converted_to_additional"]:
        return "PAST"
    if row["skipped"]:
        return "MISSED"
    if row["actual_attempt_date"]:
        return "COMPLETED" if row["analysis_completed"] else "ANALYSIS_DUE"
    planned = row["planned_attempt_date"]
    if today > row["end_date"] and not row["converted_to_additional"]:
        return "MISSED"
    if row["start_date"] <= today <= row["end_date"]:
        return "PLANNED" if planned and today <= planned else "AVAILABLE"
    return "UPCOMING" if today < row["start_date"] else "PLANNED"


def rolling_aimcat_trend(mocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted((mock for mock in mocks if mock.get("aimcat_schedule_id")), key=lambda item: item["date"])
    result: list[dict[str, Any]] = []
    keys = ("overall_percentile", "varc_percentile", "dilr_percentile", "qa_percentile")
    for index, mock in enumerate(ordered):
        window = ordered[max(0, index - 2):index + 1]
        item = dict(mock)
        for key in keys:
            values = [float(row[key] or 0) for row in window if float(row[key] or 0) > 0]
            item[f"rolling_{key}"] = round(mean(values), 1) if values else 0
        result.append(item)
    return result


def diagnosis_for(payload: dict[str, Any], recent_aimcats: list[dict[str, Any]]) -> dict[str, Any]:
    sections = {
        "VARC": float(payload.get("varc_percentile", 0) or 0),
        "DILR": float(payload.get("dilr_percentile", 0) or 0),
        "QA": float(payload.get("qa_percentile", 0) or 0),
    }
    strongest = max(sections, key=sections.get)
    limiting = min(sections, key=sections.get)
    issues: list[str] = []
    class_c = int(payload.get("class_c", 0) or 0)
    class_d = int(payload.get("class_d", 0) or 0)
    class_e = int(payload.get("class_e", 0) or 0)
    class_f = int(payload.get("class_f", 0) or 0)
    if class_c:
        issues.append(f"{class_c} conceptual errors (C): repair concepts before adding speed")
    if class_d:
        issues.append(f"{class_d} calculation/reading errors (D): add verification habits")
    if class_e:
        issues.append(f"{class_e} time/selection losses (E): change attempt decisions")
    if class_f:
        issues.append(f"{class_f} easy unattempted questions (F): improve scan and selection")
    if int(payload.get("poor_dilr_selections", 0) or 0):
        issues.append(f"{payload['poor_dilr_selections']} poor DILR set-selection decisions")
    if int(payload.get("time_waste_questions", 0) or 0):
        issues.append(f"{payload['time_waste_questions']} time-waste questions")
    if int(payload.get("easy_missed", 0) or 0):
        issues.append(f"{payload['easy_missed']} easy questions missed")
    if int(payload.get("guessing_errors", 0) or 0):
        issues.append(f"{payload['guessing_errors']} guessing errors")
    topics = str(payload.get("topics_involved") or payload.get("weak_topics") or "").strip()
    if topics:
        issues.append(f"Topic repair: {topics}")
    if not issues:
        issues.append("Use A–G review to identify conceptual, careless and selection losses")

    recent = (recent_aimcats + [payload])[-3:]
    persistent_sections = []
    for section, key in (("VARC", "varc_percentile"), ("DILR", "dilr_percentile"), ("QA", "qa_percentile")):
        values = [float(row.get(key, 0) or 0) for row in recent if float(row.get(key, 0) or 0) > 0]
        if len(values) >= 3 and mean(values) < 75:
            persistent_sections.append(section)
    limiting_weight = 40 if limiting in persistent_sections else 25
    attempted = sum(int(payload.get(f"{section}_attempts", 0) or 0) for section in ("varc", "dilr", "qa"))
    correct = sum(int(payload.get(f"{section}_correct", 0) or 0) for section in ("varc", "dilr", "qa"))
    overall_accuracy = round(correct * 100 / attempted, 1) if attempted else 0
    selection_loss = class_e + class_f + int(payload.get("poor_dilr_selections", 0) or 0) + int(payload.get("time_waste_questions", 0) or 0)
    return {
        "strongest": {"section": strongest, "percentile": sections[strongest]},
        "limiting": {"section": limiting, "percentile": sections[limiting]},
        "issues": issues,
        "persistent_sections": persistent_sections,
        "allocation": {"planned_curriculum": 100 - limiting_weight, "mock_repair": limiting_weight},
        "accuracy": overall_accuracy,
        "selection_quality": "Needs repair" if selection_loss >= 3 else "Watch" if selection_loss else "Stable",
        "prescription": [
            f"{limiting}: add one targeted weak-area block daily until the next AIMCAT",
            f"{strongest}: maintain normal practice volume",
            "Reduce D + E + F through re-solving and explicit selection review",
            "Do not add another full mock before the next scheduled AIMCAT",
        ],
    }


def encode_diagnosis(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def decode_diagnosis(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
