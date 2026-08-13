import sqlite3
import unittest

from fastapi import HTTPException

import main


class CustomStudyMaterialTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")
        self.assignment = self.con.execute(
            """
            SELECT assignment.*,task.topic_id,task.id AS task_id
            FROM task_resource_assignments assignment
            JOIN tasks task ON task.id=assignment.task_id
            WHERE task.topic_id IS NOT NULL AND task.archived=0
              AND assignment.stage='PRACTICE'
            ORDER BY task.id LIMIT 1
            """
        ).fetchone()

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def test_add_custom_material_maps_and_selects_it(self):
        original_topic = self.con.execute(
            "SELECT topic_id FROM tasks WHERE id=?", (self.assignment["task_id"],)
        ).fetchone()[0]
        resource_id = main.add_custom_study_material(
            self.con,
            {
                "assignment_id": self.assignment["id"],
                "title": "My targeted practice sheet",
                "url": "https://example.com/practice",
                "description": "A verified personal worksheet.",
                "type": "QUESTION_BANK",
                "access": "FREE",
                "difficulty": "FOUNDATION",
            },
        )
        resource = self.con.execute(
            "SELECT * FROM study_resources WHERE id=?", (resource_id,)
        ).fetchone()
        changed = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE id=?", (self.assignment["id"],)
        ).fetchone()
        mapping = self.con.execute(
            "SELECT * FROM topic_resource_maps WHERE resource_id=?", (resource_id,)
        ).fetchone()
        access = self.con.execute(
            "SELECT * FROM user_resource_access WHERE resource_provider='USER'"
        ).fetchone()
        self.assertEqual(resource["provider"], "USER")
        self.assertEqual(resource["title"], "My targeted practice sheet")
        self.assertEqual(changed["resource_id"], resource_id)
        self.assertTrue(changed["manual_override"])
        self.assertEqual(mapping["topic_id"], original_topic)
        self.assertEqual(mapping["purpose"], "PRACTICE")
        self.assertTrue(access["enabled"])
        task = self.con.execute("SELECT * FROM tasks WHERE id=?", (self.assignment["task_id"],)).fetchone()
        options = main.resource_candidates(self.con, task, "PRACTICE")
        self.assertIn(resource_id, {row["id"] for row in options})
        self.assertEqual(task["topic_id"], original_topic)

    def test_custom_material_requires_safe_location(self):
        with self.assertRaises(HTTPException):
            main.add_custom_study_material(
                self.con,
                {
                    "assignment_id": self.assignment["id"],
                    "title": "Unsafe link",
                    "url": "javascript:alert(1)",
                },
            )
        with self.assertRaises(HTTPException):
            main.add_custom_study_material(
                self.con,
                {"assignment_id": self.assignment["id"], "title": "No location"},
            )

    def test_settings_material_appears_in_replace_candidates(self):
        topic = self.con.execute(
            "SELECT * FROM topics WHERE subject='Quant' ORDER BY id LIMIT 1"
        ).fetchone()
        resource_id = main.add_custom_study_material(
            self.con,
            {
                "topic_id": topic["id"],
                "stage": "PRACTICE",
                "title": "Settings practice material",
                "platform_path": "My course → Arithmetic → Practice 1",
                "type": "COURSE",
                "access": "SUBSCRIPTION",
                "difficulty": "INTERMEDIATE",
            },
        )
        mapping = self.con.execute(
            "SELECT * FROM topic_resource_maps WHERE resource_id=?", (resource_id,)
        ).fetchone()
        resource = self.con.execute(
            "SELECT * FROM study_resources WHERE id=?", (resource_id,)
        ).fetchone()
        task = self.con.execute(
            "SELECT * FROM tasks WHERE topic_id=? AND kind='practice' AND archived=0 LIMIT 1",
            (topic["id"],),
        ).fetchone()
        if not task:
            task_id = main.insert_task(
                self.con,
                main.task(
                    "2026-09-08", "18:00", 90, "Quant", topic["name"],
                    "Settings mapping test", "", "", 10, 70, "High", "practice",
                ),
            )
            task = self.con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        candidates = main.resource_candidates(self.con, task, "PRACTICE")
        self.assertEqual(mapping["topic_id"], topic["id"])
        self.assertEqual(mapping["purpose"], "PRACTICE")
        self.assertEqual(resource["platform_path"], "My course → Arithmetic → Practice 1")
        self.assertTrue(resource["requires_subscription"])
        self.assertIn(resource_id, {candidate["id"] for candidate in candidates})

    def test_settings_material_requires_topic_and_stage(self):
        with self.assertRaises(HTTPException):
            main.add_custom_study_material(
                self.con,
                {
                    "title": "Unmapped material",
                    "url": "https://example.com/unmapped",
                    "stage": "PRACTICE",
                },
            )


if __name__ == "__main__":
    unittest.main()
