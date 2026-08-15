import sqlite3
import unittest
import os

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

import adaptive
import main


class AdaptiveLearningTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def add_task(self, topic, day, subject="Quant"):
        row = main.task(
            day, "18:00", 90, subject, topic["name"], f"Adaptive test · {topic['name']}",
            "Adaptive test details", "Test-only transaction", 20, 80, "High", "practice",
        )
        row.update(
            topic_id=topic["id"],
            difficulty=topic["progression_level"],
            adaptive_reason="Test baseline",
        )
        return main.insert_task(self.con, row)

    def test_progression_thresholds(self):
        self.assertEqual(adaptive.progression_for(8, 90, 5), "FOUNDATION")
        self.assertEqual(adaptive.progression_for(12, 66, 2), "INTERMEDIATE")
        self.assertEqual(adaptive.progression_for(20, 78, 3), "CAT_LEVEL")
        self.assertEqual(adaptive.progression_for(45, 84, 4), "TIMED")
        self.assertEqual(adaptive.progression_for(70, 90, 5), "MIXED")

    def test_accuracy_updates_mastery_and_spaced_revision(self):
        topic = self.con.execute("SELECT * FROM topics WHERE subject='Quant' AND name='Percentages'").fetchone()
        task_id = self.add_task(topic, "2026-09-01")
        future_task = self.add_task(topic, "2026-09-04")
        main.apply_task_result_to_topic(
            self.con,
            task_id,
            {"attempted": 20, "correct": 18, "accuracy": 90, "time_spent": 40, "confidence": 4},
        )
        updated = self.con.execute("SELECT * FROM topics WHERE id=?", (topic["id"],)).fetchone()
        revision = self.con.execute(
            "SELECT * FROM revision_schedule WHERE topic_id=? AND status='PENDING'",
            (topic["id"],),
        ).fetchone()
        self.assertEqual(updated["progression_level"], "CAT_LEVEL")
        self.assertEqual(updated["status"], "Practising")
        self.assertEqual(updated["accuracy"], 90)
        self.assertEqual(updated["next_revision"], "2026-09-02")
        self.assertEqual(revision["due_date"], "2026-09-02")
        future = self.con.execute("SELECT * FROM tasks WHERE id=?", (future_task,)).fetchone()
        stages = self.con.execute(
            "SELECT tra.stage,sr.difficulty FROM task_resource_assignments tra JOIN study_resources sr ON sr.id=tra.resource_id WHERE tra.task_id=? ORDER BY tra.stage_order",
            (future_task,),
        ).fetchall()
        self.assertEqual(future["difficulty"], "CAT_LEVEL")
        self.assertEqual({row["stage"] for row in stages}, {"PRACTICE", "PYQ"})
        self.assertEqual(next(row for row in stages if row["stage"] == "PRACTICE")["difficulty"], "CAT_LEVEL")

    def test_low_accuracy_repairs_future_plan_but_preserves_manual_material(self):
        topic = self.con.execute("SELECT * FROM topics WHERE subject='Quant' AND name='Averages'").fetchone()
        source_task = self.add_task(topic, "2026-09-01")
        future_task = self.add_task(topic, "2026-09-03")
        assignment = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE task_id=? ORDER BY id LIMIT 1",
            (future_task,),
        ).fetchone()
        self.con.execute(
            "UPDATE task_resource_assignments SET manual_override=1 WHERE id=?",
            (assignment["id"],),
        )
        main.apply_task_result_to_topic(
            self.con,
            source_task,
            {"attempted": 20, "correct": 10, "accuracy": 50, "time_spent": 55, "confidence": 2},
        )
        updated = self.con.execute("SELECT * FROM topics WHERE id=?", (topic["id"],)).fetchone()
        preserved = self.con.execute("SELECT * FROM task_resource_assignments WHERE id=?", (assignment["id"],)).fetchone()
        future = self.con.execute("SELECT * FROM tasks WHERE id=?", (future_task,)).fetchone()
        self.assertEqual(updated["progression_level"], "FOUNDATION")
        self.assertEqual(future["difficulty"], "FOUNDATION")
        self.assertEqual(preserved["resource_id"], assignment["resource_id"])
        self.assertEqual(preserved["manual_override"], 1)
        stages = self.con.execute(
            "SELECT tra.stage,sr.id FROM task_resource_assignments tra JOIN study_resources sr ON sr.id=tra.resource_id WHERE tra.task_id=?",
            (future_task,),
        ).fetchall()
        self.assertEqual({row["stage"] for row in stages}, {"LEARN", "PRACTICE"})
        self.assertEqual(next(row for row in stages if row["stage"] == "PRACTICE")["id"], "2iim-question-bank")

    def test_dilr_and_varc_analysis(self):
        dilr_topic = self.con.execute("SELECT * FROM topics WHERE subject='DILR' AND name='Arrangements'").fetchone()
        task_id = self.add_task(dilr_topic, "2026-09-02", "DILR")
        self.con.execute(
            """
            INSERT INTO task_results(
                task_id,attempted,correct,time_spent,confidence,accuracy,average_time,
                dilr_solved,dilr_representation,dilr_selectability,dilr_sets_solved
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (task_id, 1, 1, 28, 4, 100, 28, 1, "GRID", "YES", 1),
        )
        self.con.execute(
            "INSERT INTO errors(date,subject,topic,error_type) VALUES('2026-09-02','VARC','Reading Comprehension','Scope shift')"
        )
        category = next(row for row in adaptive.dilr_performance(self.con) if row["category"] == "Arrangements")
        varc = adaptive.varc_analysis(self.con)
        self.assertEqual(category["sets_attempted"], 1)
        self.assertEqual(category["solve_rate"], 100)
        self.assertEqual(category["median_time"], 28)
        self.assertEqual(varc["most_common"], "SCOPE_SHIFT")
        self.assertIn("scope", varc["recommendation"].lower())

    def test_mock_weakness_retargets_future_assignment(self):
        topic = self.con.execute("SELECT * FROM topics WHERE subject='Quant' AND name='Percentages'").fetchone()
        future_task = self.add_task(topic, "2026-09-10")
        mock_id = main.insert_named(
            self.con,
            "mocks",
            {"date": "2026-09-05", "provider": "IMS", "name": "Test mock", "weak_topics": "Averages"},
            ["date", "provider", "name", "weak_topics"],
        )
        main.connect_mock_to_adaptive_signals(
            self.con,
            mock_id,
            {"date": "2026-09-05", "weak_topics": "Averages"},
        )
        changed = self.con.execute("SELECT * FROM tasks WHERE id=?", (future_task,)).fetchone()
        signal = self.con.execute("SELECT * FROM adaptive_signals WHERE source_type='MOCK' AND source_id=?", (mock_id,)).fetchone()
        self.assertEqual(changed["topic"], "Averages")
        self.assertIn("Mock/error signal", changed["adaptive_reason"])
        self.assertIsNotNone(signal)

    def test_resource_effectiveness_and_coverage(self):
        topic = self.con.execute("SELECT * FROM topics WHERE subject='Quant' AND name='Percentages'").fetchone()
        task_id = self.add_task(topic, "2026-09-06")
        self.con.execute(
            "INSERT INTO task_results(task_id,attempted,correct,time_spent,confidence,accuracy,average_time) VALUES(?,?,?,?,?,?,?)",
            (task_id, 10, 8, 25, 4, 80, 2.5),
        )
        effectiveness = adaptive.resource_effectiveness(self.con)
        coverage = adaptive.coverage_report(self.con)
        self.assertTrue(effectiveness)
        self.assertTrue(any(row["average_accuracy"] >= 0 for row in effectiveness))
        self.assertTrue(coverage["valid"], coverage["issues"])
        self.con.execute("UPDATE user_resource_access SET enabled=0 WHERE resource_provider='GMAC'")
        broken = adaptive.coverage_report(self.con)
        self.assertFalse(broken["valid"])
        self.assertTrue(any("GMAT" in issue for issue in broken["issues"]))


if __name__ == "__main__":
    unittest.main()
