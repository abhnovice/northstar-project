import sqlite3
import unittest
import os

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

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

    def test_full_catalogue_is_ranked_and_preference_is_opt_in(self):
        task = dict(self.con.execute(
            "SELECT * FROM tasks WHERE id=?", (self.assignment["task_id"],)
        ).fetchone())
        task["resource_stages"] = [dict(self.assignment)]
        catalogue = main.resource_catalogue(self.con)
        options = main.task_resource_options(self.con, [task], catalogue)[
            f"{task['id']}:{self.assignment['stage']}"
        ]
        self.assertEqual(len(options), len(catalogue))
        self.assertTrue(next(item for item in options if item["available"])["recommended"])
        enabled_alternative = next(
            item for item in options
            if item["available"] and item["id"] != self.assignment["resource_id"]
        )

        main.replace_task_resource(
            self.con, self.assignment["id"], enabled_alternative["id"], False
        )
        preference = self.con.execute(
            "SELECT * FROM topic_resource_preferences WHERE topic_id=? AND stage=?",
            (task["topic_id"], self.assignment["stage"]),
        ).fetchone()
        self.assertIsNone(preference)

        main.replace_task_resource(
            self.con, self.assignment["id"], enabled_alternative["id"], True
        )
        preference = self.con.execute(
            "SELECT * FROM topic_resource_preferences WHERE topic_id=? AND stage=?",
            (task["topic_id"], self.assignment["stage"]),
        ).fetchone()
        self.assertEqual(preference["resource_id"], enabled_alternative["id"])
        with self.assertRaises(HTTPException):
            main.add_custom_study_material(
                self.con,
                {"assignment_id": self.assignment["id"], "title": "No location"},
            )

    def test_replace_material_can_prefer_one_resource_for_entire_subject(self):
        task = self.con.execute(
            "SELECT * FROM tasks WHERE id=?", (self.assignment["task_id"],)
        ).fetchone()
        alternative = next(
            row for row in main.resource_candidates(self.con, task, "PRACTICE")
            if row["id"] != self.assignment["resource_id"]
        )
        main.replace_task_resource(
            self.con, self.assignment["id"], alternative["id"], "SUBJECT"
        )
        quant_topics = self.con.execute(
            "SELECT * FROM topics WHERE subject='Quant' ORDER BY id"
        ).fetchall()
        preferences = self.con.execute(
            """SELECT * FROM topic_resource_preferences
               WHERE stage='PRACTICE' AND resource_id=?""",
            (alternative["id"],),
        ).fetchall()
        self.assertEqual(
            {row["topic_id"] for row in preferences}, {row["id"] for row in quant_topics}
        )
        other_topic = next(row for row in quant_topics if row["id"] != task["topic_id"])
        other_task = dict(task)
        other_task["topic_id"] = other_topic["id"]
        other_task["topic"] = other_topic["name"]
        ranked = main.resource_candidates(self.con, other_task, "PRACTICE")
        self.assertEqual(ranked[0]["id"], alternative["id"])
        selected = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE id=?", (self.assignment["id"],)
        ).fetchone()
        self.assertTrue(selected["manual_override"])

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

    def test_subject_wide_material_maps_every_quant_topic_and_can_be_edited(self):
        resource_id = main.add_custom_study_material(
            self.con,
            {
                "mapping_scope": "SUBJECT",
                "subject": "Quant",
                "stage": "PRACTICE",
                "title": "Complete Quant practice bank",
                "url": "https://example.com/quant",
                "type": "QUESTION_BANK",
                "access": "FREE",
                "difficulty": "INTERMEDIATE",
            },
        )
        quant_topics = self.con.execute(
            "SELECT id FROM topics WHERE subject='Quant' ORDER BY id"
        ).fetchall()
        mappings = self.con.execute(
            "SELECT * FROM topic_resource_maps WHERE resource_id=? ORDER BY topic_id",
            (resource_id,),
        ).fetchall()
        self.assertEqual(
            {row["topic_id"] for row in mappings}, {row["id"] for row in quant_topics}
        )
        self.assertTrue(all(row["purpose"] == "PRACTICE" for row in mappings))

        main.update_custom_study_material(
            self.con,
            {
                "resource_id": resource_id,
                "mapping_scope": "SUBJECT",
                "subject": "DILR",
                "stage": "LEARN",
                "title": "Complete DILR learning course",
                "platform_path": "My portal → DILR",
                "type": "COURSE",
                "access": "SUBSCRIPTION",
                "difficulty": "FOUNDATION",
            },
        )
        changed = self.con.execute(
            "SELECT * FROM study_resources WHERE id=?", (resource_id,)
        ).fetchone()
        changed_mappings = self.con.execute(
            """SELECT map.*,topic.subject FROM topic_resource_maps map
               JOIN topics topic ON topic.id=map.topic_id WHERE map.resource_id=?""",
            (resource_id,),
        ).fetchall()
        self.assertEqual(changed["title"], "Complete DILR learning course")
        self.assertEqual(changed["subject"], "DILR")
        self.assertTrue(changed["requires_subscription"])
        self.assertTrue(changed_mappings)
        self.assertTrue(all(row["subject"] == "DILR" for row in changed_mappings))
        self.assertTrue(all(row["purpose"] == "LEARN" for row in changed_mappings))

    def test_delete_custom_material_replaces_unfinished_assignment(self):
        resource_id = main.add_custom_study_material(
            self.con,
            {
                "assignment_id": self.assignment["id"],
                "title": "Temporary practice bank",
                "url": "https://example.com/temporary",
                "type": "QUESTION_BANK",
                "access": "FREE",
                "difficulty": "FOUNDATION",
            },
        )
        result = main.delete_custom_study_material(self.con, resource_id)
        resource = self.con.execute(
            "SELECT * FROM study_resources WHERE id=?", (resource_id,)
        ).fetchone()
        changed = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE id=?", (self.assignment["id"],)
        ).fetchone()
        self.assertFalse(resource["active"])
        self.assertNotEqual(changed["resource_id"], resource_id)
        self.assertFalse(changed["manual_override"])
        self.assertEqual(result["replaced_assignments"], 1)
        self.assertEqual(
            self.con.execute(
                "SELECT COUNT(*) FROM topic_resource_maps WHERE resource_id=?", (resource_id,)
            ).fetchone()[0],
            0,
        )
        repeated = main.delete_custom_study_material(self.con, resource_id)
        self.assertEqual(repeated["already_deleted"], 1)

    def test_delete_custom_material_preserves_completed_task_history(self):
        resource_id = main.add_custom_study_material(
            self.con,
            {
                "assignment_id": self.assignment["id"],
                "title": "Completed historical worksheet",
                "url": "https://example.com/history",
            },
        )
        self.con.execute(
            "UPDATE tasks SET completed=1 WHERE id=?", (self.assignment["task_id"],)
        )
        result = main.delete_custom_study_material(self.con, resource_id)
        historical = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE id=?", (self.assignment["id"],)
        ).fetchone()
        self.assertEqual(historical["resource_id"], resource_id)
        self.assertEqual(result["preserved_history"], 1)


if __name__ == "__main__":
    unittest.main()
