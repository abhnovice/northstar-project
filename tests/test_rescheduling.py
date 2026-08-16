import sqlite3
import unittest
import os

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

from fastapi import HTTPException

import main


class TaskReschedulingTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(main.DB_PATH)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys=ON")
        self.con.execute("BEGIN")

    def tearDown(self):
        self.con.rollback()
        self.con.close()

    def reset_plan_date(self, day):
        self.con.execute("DELETE FROM tasks WHERE date=?", (day,))
        self.con.execute("DELETE FROM plan_days WHERE date=?", (day,))

    def test_single_task_move_preserves_identity_material_and_override(self):
        source = "2026-09-08"
        target = "2026-09-09"
        self.reset_plan_date(source)
        self.reset_plan_date(target)
        main.ensure_plan(self.con, source)
        task = self.con.execute(
            "SELECT * FROM tasks WHERE date=? AND kind='practice' ORDER BY id LIMIT 1",
            (source,),
        ).fetchone()
        assignment = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE task_id=? ORDER BY id LIMIT 1",
            (task["id"],),
        ).fetchone()
        self.con.execute(
            "UPDATE task_resource_assignments SET manual_override=1 WHERE id=?",
            (assignment["id"],),
        )

        result = main.reschedule_task(self.con, task["id"], target, "19:10")

        moved = self.con.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone()
        preserved = self.con.execute(
            "SELECT * FROM task_resource_assignments WHERE id=?", (assignment["id"],)
        ).fetchone()
        history = self.con.execute(
            "SELECT * FROM task_reschedule_history WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task["id"],),
        ).fetchone()
        self.assertEqual(result["task_ids"], [task["id"]])
        self.assertFalse(result["refresh_required"])
        self.assertEqual(
            result["tasks"],
            [{"id": task["id"], "date": target, "start_time": "19:10", "rescheduled": 1}],
        )
        self.assertFalse(result["grouped"])
        self.assertEqual((moved["date"], moved["start_time"], moved["rescheduled"]), (target, "19:10", 1))
        self.assertEqual(preserved["resource_id"], assignment["resource_id"])
        self.assertEqual(preserved["manual_override"], 1)
        self.assertEqual((history["from_date"], history["to_date"], history["grouped"]), (source, target, 0))

    def test_mock_day_moves_as_one_bundle_and_does_not_regenerate(self):
        source = "2026-09-13"
        target = "2026-09-14"
        self.reset_plan_date(source)
        self.reset_plan_date(target)
        main.ensure_plan(self.con, source)
        before = self.con.execute(
            "SELECT * FROM tasks WHERE date=? ORDER BY start_time", (source,)
        ).fetchall()
        self.assertEqual({row["kind"] for row in before}, {"mock", "analysis", "revision"})
        assignment_snapshot = self.con.execute(
            "SELECT id,task_id,resource_id,manual_override FROM task_resource_assignments WHERE task_id IN (SELECT id FROM tasks WHERE date=?) ORDER BY id",
            (source,),
        ).fetchall()
        mock = next(row for row in before if row["kind"] == "mock")

        result = main.reschedule_task(self.con, mock["id"], target, "18:00")

        moved = self.con.execute(
            "SELECT * FROM tasks WHERE date=? ORDER BY start_time", (target,)
        ).fetchall()
        self.assertTrue(result["grouped"])
        self.assertTrue(result["refresh_required"])
        self.assertEqual(result["tasks"], [])
        self.assertEqual(len(result["task_ids"]), 3)
        self.assertEqual([row["start_time"] for row in moved if row["aimcat_schedule_id"]], ["18:00", "20:00", "23:00"])
        self.assertTrue(all(row["rescheduled"] for row in moved))
        after_assignments = self.con.execute(
            "SELECT id,task_id,resource_id,manual_override FROM task_resource_assignments WHERE task_id IN (SELECT id FROM tasks WHERE date=?) ORDER BY id",
            (target,),
        ).fetchall()
        self.assertEqual([tuple(row) for row in after_assignments], [tuple(row) for row in assignment_snapshot])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM tasks WHERE date=? AND archived=0", (source,)).fetchone()[0], 4)
        main.ensure_plan(self.con, source)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM tasks WHERE date=? AND archived=0", (source,)).fetchone()[0], 4)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM task_reschedule_history WHERE grouped=1 AND task_id IN (SELECT id FROM tasks WHERE date=?)", (target,)).fetchone()[0],
            3,
        )

    def test_completed_task_must_be_reopened_before_move(self):
        source = "2026-09-10"
        self.reset_plan_date(source)
        main.ensure_plan(self.con, source)
        task = self.con.execute("SELECT * FROM tasks WHERE date=? LIMIT 1", (source,)).fetchone()
        self.con.execute("UPDATE tasks SET completed=1 WHERE id=?", (task["id"],))
        with self.assertRaises(HTTPException) as raised:
            main.reschedule_task(self.con, task["id"], "2026-09-11", "18:00")
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
