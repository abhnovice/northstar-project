import sqlite3
import unittest
import os

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

from fastapi import HTTPException

import aimcat
import main


class AimcatPlannerTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def schedule(self, test_ref):
        return self.con.execute(
            "SELECT * FROM aimcat_schedules WHERE test_ref=?", (test_ref,)
        ).fetchone()

    def test_all_windows_seeded_and_prep_baseline_excludes_history(self):
        rows = self.con.execute("SELECT * FROM aimcat_schedules ORDER BY start_date").fetchall()
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(row["historical"] for row in rows), 8)
        first = self.schedule("AIMCAT2714")
        self.assertEqual((first["start_date"], first["end_date"]), ("2026-08-15", "2026-08-19"))
        self.assertEqual(first["preferred_attempt_date"], "2026-08-16")
        self.assertEqual(first["planned_attempt_date"], "2026-08-16")
        past = self.schedule("AIMCAT2716")
        self.assertEqual(aimcat.status_for(past, "2026-08-12"), "PAST")
        self.assertIsNone(past["planned_attempt_date"])

    def test_only_planned_aimcat_date_generates_full_mock_lifecycle(self):
        planned = main.plan_rows(self.con, "2026-08-16")
        ordinary = main.plan_rows(self.con, "2026-08-17")
        self.assertEqual([row["duration"] for row in planned], [120, 180, 60])
        self.assertEqual([row["kind"] for row in planned], ["mock", "analysis", "revision"])
        self.assertTrue(all(row["aimcat_schedule_id"] for row in planned))
        self.assertNotIn("mock", {row["kind"] for row in ordinary})
        self.assertTrue(main.should_mock("2026-08-23", self.con))
        self.assertFalse(main.should_mock("2026-08-21", self.con))

    def test_pre_mock_runway_and_final_consolidation(self):
        runway = main.plan_rows(self.con, "2026-08-14")
        self.assertIn("familiarisation", runway[0]["title"])
        self.assertTrue(all("Pre-mock taper" in row.get("adaptive_reason", "") for row in runway))
        consolidation = main.plan_rows(self.con, "2026-11-20")
        self.assertTrue(all("CAT consolidation" in row["title"] for row in consolidation))
        self.assertNotIn("mock", {row["kind"] for row in consolidation})

    def test_attempt_date_override_stays_inside_window_and_preserves_lifecycle(self):
        schedule = self.schedule("AIMCAT2714")
        before = self.con.execute(
            "SELECT id FROM tasks WHERE aimcat_schedule_id=? AND archived=0 ORDER BY id",
            (schedule["id"],),
        ).fetchall()
        assignment_before = self.con.execute(
            """SELECT id,task_id,resource_id,manual_override FROM task_resource_assignments
               WHERE task_id IN (SELECT id FROM tasks WHERE aimcat_schedule_id=? AND archived=0) ORDER BY id""",
            (schedule["id"],),
        ).fetchall()
        main.set_aimcat_attempt_date(self.con, schedule["id"], "2026-08-17")
        moved = self.con.execute(
            "SELECT id,date,rescheduled FROM tasks WHERE aimcat_schedule_id=? AND archived=0 ORDER BY id",
            (schedule["id"],),
        ).fetchall()
        assignment_after = self.con.execute(
            """SELECT id,task_id,resource_id,manual_override FROM task_resource_assignments
               WHERE task_id IN (SELECT id FROM tasks WHERE aimcat_schedule_id=? AND archived=0) ORDER BY id""",
            (schedule["id"],),
        ).fetchall()
        self.assertEqual([row["id"] for row in before], [row["id"] for row in moved])
        self.assertTrue(all(row["date"] == "2026-08-17" and row["rescheduled"] for row in moved))
        self.assertEqual([tuple(row) for row in assignment_before], [tuple(row) for row in assignment_after])
        old_day = self.con.execute(
            "SELECT kind FROM tasks WHERE date='2026-08-16' AND archived=0 AND manual=0"
        ).fetchall()
        self.assertNotIn("mock", {row["kind"] for row in old_day})
        checkpoint_collision = self.con.execute(
            "SELECT COUNT(*) FROM time_foundation_schedule WHERE planned_date='2026-08-17' AND status='PLANNED'"
        ).fetchone()[0]
        self.assertEqual(checkpoint_collision, 0)
        relocated = self.con.execute(
            """SELECT schedule.*,task.date AS task_date,task.time_foundation_test_id
               FROM time_foundation_schedule schedule
               LEFT JOIN tasks task ON task.id=schedule.task_id
               WHERE schedule.planned_date='2026-08-16' AND schedule.status='PLANNED'"""
        ).fetchone()
        self.assertIsNotNone(relocated)
        self.assertEqual(relocated["task_date"], "2026-08-16")
        self.assertEqual(relocated["time_foundation_test_id"], relocated["test_id"])
        with self.assertRaises(HTTPException):
            main.set_aimcat_attempt_date(self.con, schedule["id"], "2026-08-20")

    def test_result_creates_diagnosis_and_analysis_due_state(self):
        schedule = self.schedule("AIMCAT2714")
        payload = {
            "date": "2026-08-16", "overall_score": 54, "overall_percentile": 82.4,
            "varc_score": 31, "varc_percentile": 91, "varc_attempts": 18,
            "varc_correct": 14, "varc_incorrect": 4, "dilr_score": 15,
            "dilr_percentile": 64, "dilr_attempts": 10, "dilr_correct": 6,
            "dilr_incorrect": 4, "qa_score": 22, "qa_percentile": 78,
            "qa_attempts": 15, "qa_correct": 10, "qa_incorrect": 5,
            "easy_missed": 2, "def_errors": 5, "time_waste_questions": 2,
            "poor_dilr_selections": 1, "guessing_errors": 1,
            "class_a": 25, "class_b": 2, "class_c": 3, "class_d": 2,
            "class_e": 2, "class_f": 1, "class_g": 10,
            "topics_involved": "Percentages, Arrangements", "weak_topics": "Percentages",
        }
        diagnosis = main.record_aimcat_result(self.con, schedule["id"], payload)
        updated = self.schedule("AIMCAT2714")
        result = self.con.execute("SELECT * FROM mocks WHERE id=?", (updated["mock_id"],)).fetchone()
        mock_task = self.con.execute(
            "SELECT * FROM tasks WHERE aimcat_schedule_id=? AND kind='mock' AND archived=0",
            (schedule["id"],),
        ).fetchone()
        self.assertEqual(updated["status"], "ANALYSIS_DUE")
        self.assertEqual(result["name"], "AIMCAT2714")
        self.assertEqual(result["poor_dilr_selections"], 1)
        self.assertEqual(result["class_c"], 3)
        self.assertEqual(diagnosis["strongest"]["section"], "VARC")
        self.assertEqual(diagnosis["limiting"]["section"], "DILR")
        self.assertEqual(diagnosis["allocation"]["mock_repair"], 25)
        self.assertEqual(diagnosis["accuracy"], 69.8)
        self.assertEqual(diagnosis["selection_quality"], "Needs repair")
        self.assertTrue(any("conceptual" in issue for issue in diagnosis["issues"]))
        self.assertTrue(mock_task["completed"])
        main.prioritize_analysis_carryover(self.con, "2026-08-17")
        next_day = self.con.execute(
            "SELECT * FROM tasks WHERE date='2026-08-17' AND archived=0 AND manual=0 ORDER BY start_time"
        ).fetchall()
        self.assertEqual(sum(row["duration"] for row in next_day), 360)
        self.assertEqual({row["subject"] for row in next_day}, {"Analysis", "DILR", "VARC"})
        self.assertEqual(next_day[0]["title"], "Analyse AIMCAT2714")

    def test_past_aimcat_can_be_manually_activated_without_backlog(self):
        past = self.schedule("AIMCAT2716")
        with self.assertRaises(HTTPException):
            main.set_aimcat_attempt_date(self.con, past["id"], "2026-09-05")
        main.set_aimcat_attempt_date(self.con, past["id"], "2026-09-05", convert_past=True)
        converted = self.schedule("AIMCAT2716")
        self.assertTrue(converted["converted_to_additional"])
        self.assertEqual(converted["planned_attempt_date"], "2026-09-05")
        self.assertEqual(aimcat.status_for(converted, "2026-08-12"), "PLANNED")


if __name__ == "__main__":
    unittest.main()
