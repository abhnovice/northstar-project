import os
import sqlite3
import unittest

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

import main


class CalendarEarlyCompletionTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")
        self.topic_id = self.con.execute(
            "SELECT id FROM topics WHERE subject='Quant' ORDER BY id LIMIT 1"
        ).fetchone()[0]

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def task(self, day, title, duration=60, **values):
        fields = {
            "date": day,
            "start_time": values.pop("start_time", "18:00"),
            "duration": duration,
            "subject": values.pop("subject", "Quant"),
            "topic": values.pop("topic", "Percentages"),
            "title": title,
            "detail": "Test task",
            "resource": "Test resource",
            "priority": values.pop("priority", "High"),
            "kind": values.pop("kind", "practice"),
            "topic_id": values.pop("topic_id", self.topic_id),
            "difficulty": values.pop("difficulty", "FOUNDATION"),
        }
        fields.update(values)
        cursor = self.con.execute(
            f"INSERT INTO tasks({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
            tuple(fields.values()),
        )
        return cursor.lastrowid

    def test_completion_preserves_original_date_and_reuses_slot(self):
        early = self.task("2098-08-24", "Cubes", 60, topic="Cubes")
        candidate = self.task("2098-08-15", "Percentages", 75)
        mock = self.task("2098-08-15", "Protected AIMCAT", 60, kind="mock", priority="Critical")
        pinned = self.task("2098-08-15", "Pinned lesson", 60, pinned=1)

        result = main.complete_scheduled_topic_early(
            self.con, early, "2098-08-15", "TASK", "AUTO"
        )

        completed = self.con.execute("SELECT * FROM tasks WHERE id=?", (early,)).fetchone()
        moved = self.con.execute("SELECT * FROM tasks WHERE id=?", (candidate,)).fetchone()
        audit = self.con.execute(
            "SELECT * FROM task_early_completion_history WHERE completed_task_id=?", (early,)
        ).fetchone()
        self.assertEqual(completed["date"], "2098-08-15")
        self.assertEqual(completed["original_planned_date"], "2098-08-24")
        self.assertEqual(completed["actual_completion_date"], "2098-08-15")
        self.assertTrue(completed["completed_early"])
        self.assertEqual(moved["date"], "2098-08-24")
        self.assertEqual(moved["reallocated_from_date"], "2098-08-15")
        self.assertEqual(result["replacement_task_id"], candidate)
        self.assertEqual(audit["replacement_task_id"], candidate)
        self.assertEqual(self.con.execute("SELECT date FROM tasks WHERE id=?", (mock,)).fetchone()[0], "2098-08-15")
        self.assertEqual(self.con.execute("SELECT date FROM tasks WHERE id=?", (pinned,)).fetchone()[0], "2098-08-15")

    def test_large_duration_mismatch_is_rejected(self):
        early = self.task("2098-08-24", "Short future task", 60)
        long_task = self.task("2098-08-15", "Long current task", 135)
        with self.assertRaisesRegex(Exception, "duration mismatch"):
            main.complete_scheduled_topic_early(
                self.con, early, "2098-08-15", "TASK", "SPECIFIC", long_task
            )

    def test_topic_completion_keeps_advanced_and_revision_work(self):
        early = self.task("2098-08-24", "Cubes Foundation", 60, topic="Cubes")
        other_foundation = self.task("2098-08-28", "Cubes Intermediate", 60, topic="Cubes", difficulty="INTERMEDIATE")
        advanced = self.task("2098-09-10", "Cubes CAT mixed", 60, topic="Cubes", difficulty="CAT_LEVEL")
        revision = self.task("2098-09-11", "Cubes revision", 60, topic="Cubes", kind="revision")

        main.complete_scheduled_topic_early(
            self.con, early, "2098-08-15", "TOPIC", "NONE"
        )

        self.assertTrue(self.con.execute("SELECT completed FROM tasks WHERE id=?", (other_foundation,)).fetchone()[0])
        self.assertFalse(self.con.execute("SELECT completed FROM tasks WHERE id=?", (advanced,)).fetchone()[0])
        self.assertFalse(self.con.execute("SELECT completed FROM tasks WHERE id=?", (revision,)).fetchone()[0])
        topic = self.con.execute("SELECT * FROM topics WHERE id=?", (self.topic_id,)).fetchone()
        self.assertEqual(topic["progression_level"], "CAT_LEVEL")
        self.assertGreaterEqual(topic["mastery_score"], 70)


if __name__ == "__main__":
    unittest.main()
