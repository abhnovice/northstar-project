import sqlite3
import unittest
import os

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

import main


class TimeFoundationTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def test_exact_catalog_is_seeded_without_acronym_inference(self):
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM time_foundation_tests").fetchone()[0],
            63,
        )
        row = self.con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference='OBQ1001810'"
        ).fetchone()
        self.assertEqual(row["provider_title"], "Foundation - AMA and SICI - 1")
        self.assertEqual(row["canonical_topic_group"], "ARITHMETIC")
        self.assertIsNone(row["canonical_topic"])
        optional = self.con.execute(
            "SELECT COUNT(*) FROM time_foundation_tests WHERE cat_core=0"
        ).fetchone()[0]
        self.assertEqual(optional, 13)
        verbal = self.con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference='OBE1001803'"
        ).fetchone()
        self.assertEqual(verbal["provider_title"], "Foundation - RC - 1")
        self.assertEqual(verbal["subject"], "VARC")
        self.assertEqual(verbal["canonical_topic"], "READING_COMPREHENSION")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM aimcat_schedules").fetchone()[0], 20)

    def test_every_known_reference_is_scheduled_once_outside_aimcat_days(self):
        main.initialize_time_foundation_schedule(self.con)
        schedule = self.con.execute(
            "SELECT * FROM time_foundation_schedule ORDER BY planned_date,id"
        ).fetchall()
        self.assertEqual(len(schedule), 63)
        self.assertEqual(len({row["test_id"] for row in schedule}), 63)
        self.assertEqual(len({row["planned_date"] for row in schedule}), 63)
        # Existing schedule dates are durable as the real Kolkata date advances.
        self.assertGreaterEqual(schedule[0]["planned_date"], main.PREP_START_DATE)
        self.assertLessEqual(schedule[-1]["planned_date"], "2026-11-18")
        aimcat_collision = self.con.execute(
            """SELECT COUNT(*) FROM time_foundation_schedule foundation
               JOIN aimcat_schedules aimcat
                 ON aimcat.planned_attempt_date=foundation.planned_date
                AND aimcat.skipped=0
                AND (aimcat.historical=0 OR aimcat.converted_to_additional=1)"""
        ).fetchone()[0]
        self.assertEqual(aimcat_collision, 0)

    def test_future_checkpoint_attaches_when_its_day_is_opened(self):
        scheduled = self.con.execute(
            """SELECT schedule.*,test.subject FROM time_foundation_schedule schedule
               JOIN time_foundation_tests test ON test.id=schedule.test_id
               WHERE schedule.task_id IS NULL AND schedule.status='PLANNED'
               ORDER BY schedule.planned_date LIMIT 1"""
        ).fetchone()
        self.assertIsNotNone(scheduled)
        main.ensure_plan(self.con, scheduled["planned_date"])
        attached = self.con.execute(
            "SELECT * FROM time_foundation_schedule WHERE id=?", (scheduled["id"],)
        ).fetchone()
        self.assertIsNotNone(attached["task_id"])
        task = self.con.execute("SELECT * FROM tasks WHERE id=?", (attached["task_id"],)).fetchone()
        expected_subject = main.foundation_subject_block(scheduled["subject"])
        self.assertEqual(task["subject"], expected_subject)
        self.assertEqual(task["time_foundation_test_id"], scheduled["test_id"])
        self.assertLessEqual(sum(stage[1] for stage in main.stage_plan(task)) + 45, task["duration"])

    def test_portal_totals_make_missing_quant_references_explicit(self):
        inventory = {row["subject"]: row for row in main.time_foundation_inventory_payload(self.con)}
        self.assertEqual(inventory["LR"]["portal_reported_attempted"], 2)
        self.assertEqual(inventory["VARC"]["portal_reported_attempted"], 1)
        self.assertEqual(inventory["QA"]["portal_total"], 37)
        self.assertEqual(inventory["QA"]["known_references"], 20)
        self.assertEqual(inventory["QA"]["missing_references"], 17)

    def test_today_payload_contains_exact_reference_and_portal(self):
        task = self.con.execute(
            """SELECT * FROM tasks WHERE time_foundation_test_id IS NOT NULL
               AND archived=0 ORDER BY date,id LIMIT 1"""
        ).fetchone()
        self.assertIsNotNone(task)
        payload = [dict(task)]
        main.enrich_tasks_with_resources(self.con, payload)
        checkpoint = payload[0]["time_foundation_test"]
        self.assertTrue(checkpoint["test_reference"].startswith(("OBQ", "OBD", "OBL", "OBE")))
        self.assertEqual(checkpoint["url"], "https://www.time4education.com/")
        stages = main.stage_plan(task)
        self.assertLessEqual(sum(stage[1] for stage in stages) + 45, task["duration"])

    def test_foundation_result_uses_adjustable_threshold_and_updates_mastery(self):
        test = self.con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference='OBQ1001812'"
        ).fetchone()
        task = self.con.execute(
            "SELECT * FROM tasks WHERE subject='Quant' AND topic_id IS NOT NULL AND archived=0 ORDER BY date,id LIMIT 1"
        ).fetchone()
        self.con.execute(
            "UPDATE tasks SET time_foundation_test_id=? WHERE id=?", (test["id"], task["id"])
        )
        self.con.execute(
            "INSERT INTO settings(key,value) VALUES('timeFoundationAdvanceAccuracy','90') ON CONFLICT(key) DO UPDATE SET value='90'"
        )
        result = main.record_time_foundation_result(
            self.con,
            {
                "test_id": test["id"], "task_id": task["id"], "attempted_on": task["date"],
                "attempted": 20, "correct": 18, "time_spent": 30, "confidence": 4,
            },
        )
        self.assertEqual(result["outcome"], "ADVANCE")
        schedule = self.con.execute(
            "SELECT * FROM time_foundation_schedule WHERE test_id=?", (test["id"],)
        ).fetchone()
        self.assertEqual(schedule["status"], "COMPLETED")
        updated = self.con.execute("SELECT * FROM topics WHERE id=?", (task["topic_id"],)).fetchone()
        self.assertIn(updated["progression_level"], ("CAT_LEVEL", "TIMED", "MIXED"))
        revision = self.con.execute(
            "SELECT * FROM revision_schedule WHERE topic_id=? AND status='PENDING'",
            (task["topic_id"],),
        ).fetchone()
        self.assertIsNotNone(revision)

    def test_low_checkpoint_creates_repair_signal(self):
        test = self.con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference='OBQ1001806'"
        ).fetchone()
        result = main.record_time_foundation_result(
            self.con,
            {
                "test_id": test["id"], "attempted_on": "2026-08-20",
                "attempted": 10, "correct": 5, "time_spent": 25, "confidence": 2,
            },
        )
        self.assertEqual(result["outcome"], "REPAIR")
        signal = self.con.execute(
            "SELECT * FROM adaptive_signals WHERE source_type='TIME_FOUNDATION' AND source_id=?",
            (result["attempt_id"],),
        ).fetchone()
        self.assertIsNotNone(signal)
        self.assertIn("concept repair", signal["reason"])

    def test_csv_import_upserts_by_test_reference(self):
        before = self.con.execute("SELECT COUNT(*) FROM time_foundation_tests").fetchone()[0]
        first = main.import_time_foundation_csv(
            self.con,
            "Test Reference,Description,Subject\nOBQ1001999,Foundation - Future supplied title,QA\n",
        )
        second = main.import_time_foundation_csv(
            self.con,
            "Test Reference,Description,Subject\nOBQ1001999,Foundation - Corrected supplied title,QA\n",
        )
        self.assertEqual(first, {"created": 1, "updated": 0})
        self.assertEqual(second, {"created": 0, "updated": 1})
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM time_foundation_tests").fetchone()[0],
            before + 1,
        )
        imported = self.con.execute(
            """SELECT schedule.* FROM time_foundation_schedule schedule
               JOIN time_foundation_tests test ON test.id=schedule.test_id
               WHERE test.test_reference='OBQ1001999'"""
        ).fetchone()
        self.assertIsNotNone(imported)
        row = self.con.execute(
            "SELECT * FROM time_foundation_tests WHERE test_reference='OBQ1001999'"
        ).fetchone()
        self.assertEqual(row["provider_title"], "Foundation - Corrected supplied title")
        self.assertIsNone(row["canonical_topic"])

        existing = main.import_time_foundation_csv(
            self.con,
            "Test Reference,Description,Subject\nOBQ1001812,User-verified corrected portal title,QA\n",
        )
        self.assertEqual(existing, {"created": 0, "updated": 1})
        main.seed_time_foundation_data(self.con)
        preserved = self.con.execute(
            "SELECT provider_title FROM time_foundation_tests WHERE test_reference='OBQ1001812'"
        ).fetchone()
        self.assertEqual(preserved["provider_title"], "User-verified corrected portal title")

    def test_tabular_import_is_supported(self):
        result = main.import_time_foundation_csv(
            self.con,
            "Test Reference\tDescription\tSubject\nOBL1001998\tFoundation - Future LR title\tLR\n",
        )
        self.assertEqual(result, {"created": 1, "updated": 0})


if __name__ == "__main__":
    unittest.main()
