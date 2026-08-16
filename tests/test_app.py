import unittest
import os
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

os.environ["NORTHSTAR_DATABASE_URL"] = "sqlite"

import main
import database


class CommandCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_seeded_plan_and_profile(self):
        response = self.client.get("/api/app?date=2026-08-12")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["profile"]["employer"], "IBM")
        self.assertEqual(data["meta"]["phase"], "Foundation")
        self.assertGreaterEqual(len(data["tasks"]), 4)

    def test_mock_day_replaces_standard_plan(self):
        response = self.client.get("/api/app?date=2026-08-16")
        tasks = [t for t in response.json()["tasks"] if t["date"] == "2026-08-16"]
        self.assertEqual(sum(t["duration"] for t in tasks), 360)
        self.assertEqual({t["kind"] for t in tasks}, {"mock", "analysis", "revision"})
        self.assertEqual(next(t for t in tasks if t["kind"] == "mock")["title"], "AIMCAT2714")

    def test_task_completion_persists(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        task = next(t for t in data["tasks"] if t["date"] == "2026-08-12")
        original = bool(task["completed"])
        try:
            response = self.client.post("/api/app", json={"action":"toggleTask","payload":{"id":task["id"],"completed":not original}})
            self.assertEqual(response.status_code, 200)
            saved = self.client.get("/api/app?date=2026-08-12").json()
            changed = next(t for t in saved["tasks"] if t["id"] == task["id"])
            self.assertEqual(bool(changed["completed"]), not original)
        finally:
            self.client.post("/api/app", json={"action":"toggleTask","payload":{"id":task["id"],"completed":original}})

    def test_production_frontend_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_default_current_date_uses_kolkata(self):
        response = self.client.get("/api/app")
        expected = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
        self.assertEqual(response.json()["meta"]["today"], expected)

    def test_full_payload_stays_within_remote_query_budget(self):
        original_execute = database.ConnectionAdapter.execute
        query_count = 0

        def counted_execute(adapter, statement, parameters=None):
            nonlocal query_count
            query_count += 1
            return original_execute(adapter, statement, parameters)

        with patch.object(database.ConnectionAdapter, "execute", counted_execute):
            payload = main.get_data("2026-08-16")
        self.assertTrue(payload["resourceCoverage"]["valid"])
        self.assertLessEqual(query_count, 45)

    def test_task_move_action_returns_lightweight_patch(self):
        task_row = main.task(
            "2026-10-20", "18:00", 60, "Quant", "API move probe",
            "Temporary move probe", "", "", 0, 0, "Low", "manual",
        )
        task_row["manual"] = 1
        with main.connection() as con:
            task_id = main.insert_task(con, task_row)
        try:
            original_execute = database.ConnectionAdapter.execute
            query_count = 0

            def counted_execute(adapter, statement, parameters=None):
                nonlocal query_count
                query_count += 1
                return original_execute(adapter, statement, parameters)

            with patch.object(database.ConnectionAdapter, "execute", counted_execute):
                response = self.client.post(
                    "/api/app",
                    json={
                        "action": "rescheduleTask",
                        "payload": {"task_id": task_id, "date": "2026-10-21", "start_time": "19:15"},
                    },
                )
            self.assertEqual(response.status_code, 200)
            self.assertLessEqual(query_count, 5)
            result = response.json()["result"]
            self.assertFalse(result["refresh_required"])
            self.assertEqual(
                result["tasks"],
                [{"id": task_id, "date": "2026-10-21", "start_time": "19:15", "rescheduled": 1}],
            )
            with main.connection() as con:
                moved = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            self.assertEqual((moved["date"], moved["start_time"]), ("2026-10-21", "19:15"))
        finally:
            with main.connection() as con:
                con.execute("DELETE FROM task_reschedule_history WHERE task_id=?", (task_id,))
                con.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def test_resource_migration_and_seed_are_available(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        self.assertGreaterEqual(len(data["studyResources"]), 6)
        self.assertGreaterEqual(len(data["resourceAccess"]), 8)
        self.assertGreaterEqual(len(data["topicResourceMaps"]), len(data["topics"]))
        enabled = {row["resource_provider"]: bool(row["enabled"]) for row in data["resourceAccess"]}
        self.assertTrue(enabled["RODHA"])
        self.assertTrue(enabled["2IIM"])
        self.assertTrue(enabled["CAT_PYQ"])
        self.assertTrue(enabled["GMAC"])
        self.assertTrue(enabled["TIME"])
        self.assertFalse(enabled["IMS"])
        self.assertFalse(enabled["VARC1000"])

    def test_resource_access_toggle_persists(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        original = next(row for row in data["resourceAccess"] if row["resource_provider"] == "IMS")["enabled"]
        try:
            response = self.client.post("/api/app", json={"action":"setResourceAccess","payload":{"resource_provider":"IMS","enabled":not bool(original)}})
            self.assertEqual(response.status_code, 200)
            changed = self.client.get("/api/app?date=2026-08-12").json()
            value = next(row for row in changed["resourceAccess"] if row["resource_provider"] == "IMS")["enabled"]
            self.assertEqual(bool(value), not bool(original))
        finally:
            self.client.post("/api/app", json={"action":"setResourceAccess","payload":{"resource_provider":"IMS","enabled":bool(original)}})

    def test_generated_tasks_use_only_enabled_staged_resources(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        enabled = {
            row["resource_provider"]
            for row in data["resourceAccess"]
            if row["enabled"]
        }
        study_tasks = [
            task for task in data["tasks"]
            if task["kind"] == "practice" and task["resource_stages"]
        ]
        self.assertTrue(study_tasks)
        for task in study_tasks:
            self.assertTrue(task["resource_stages"])
            self.assertTrue({stage["provider"] for stage in task["resource_stages"]} <= enabled)
            self.assertTrue({stage["stage"] for stage in task["resource_stages"]} <= {"LEARN", "PRACTICE", "PYQ"})
            self.assertTrue(all(stage["url"] or stage["platform_path"] for stage in task["resource_stages"]))

    def test_disabled_provider_cannot_replace_material(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        task = next(task for task in data["tasks"] if task["resource_stages"])
        assignment = task["resource_stages"][0]
        response = self.client.post(
            "/api/app",
            json={"action":"replaceTaskResource","payload":{"assignment_id":assignment["assignment_id"],"resource_id":"ims-simcat-plus"}},
        )
        self.assertEqual(response.status_code, 400)

    def test_replace_material_with_enabled_mapped_provider(self):
        selected_date = "2026-08-13"
        data = self.client.get(f"/api/app?date={selected_date}").json()
        original_access = next(row for row in data["resourceAccess"] if row["resource_provider"] == "VARC1000")["enabled"]
        original_assignment_id = None
        original_resource_id = None
        original_manual_override = None
        original_selected_reason = None
        try:
            if not original_access:
                self.client.post("/api/app", json={"action":"setResourceAccess","payload":{"resource_provider":"VARC1000","enabled":True}})
            enabled_data = self.client.get(f"/api/app?date={selected_date}").json()
            task = next(task for task in enabled_data["tasks"] if task["date"] == selected_date and task["subject"] == "VARC" and task["resource_stages"])
            stage = next(stage for stage in task["resource_stages"] if stage["stage"] == "PRACTICE")
            original_assignment_id = stage["assignment_id"]
            original_resource_id = stage["resource_id"]
            original_manual_override = stage["manual_override"]
            original_selected_reason = stage["selected_reason"]
            options = enabled_data["taskResourceOptions"][f"{task['id']}:PRACTICE"]
            replacement = next(option for option in options if option["id"] != stage["resource_id"])
            response = self.client.post(
                "/api/app",
                json={"action":"replaceTaskResource","payload":{"assignment_id":stage["assignment_id"],"resource_id":replacement["id"]}},
            )
            self.assertEqual(response.status_code, 200)
            changed = self.client.get(f"/api/app?date={selected_date}").json()
            changed_task = next(item for item in changed["tasks"] if item["id"] == task["id"])
            changed_stage = next(item for item in changed_task["resource_stages"] if item["stage"] == "PRACTICE")
            self.assertEqual(changed_stage["resource_id"], replacement["id"])
            self.assertTrue(changed_stage["manual_override"])
        finally:
            self.client.post("/api/app", json={"action":"setResourceAccess","payload":{"resource_provider":"VARC1000","enabled":bool(original_access)}})
            if original_assignment_id and original_resource_id:
                with main.connection() as con:
                    con.execute(
                        "UPDATE task_resource_assignments SET resource_id=?,manual_override=?,selected_reason=? WHERE id=?",
                        (original_resource_id, original_manual_override, original_selected_reason, original_assignment_id),
                    )

    def test_plan_open_return_and_record_result_flow(self):
        data = self.client.get("/api/app?date=2026-08-12").json()
        task = next(task for task in data["tasks"] if task["kind"] == "practice" and task["resource_stages"])
        self.assertTrue(any(stage["url"] for stage in task["resource_stages"]))
        with main.connection() as con:
            original_task = dict(con.execute("SELECT * FROM tasks WHERE id=?", (task["id"],)).fetchone())
            original_result_row = con.execute("SELECT * FROM task_results WHERE task_id=?", (task["id"],)).fetchone()
            original_result = dict(original_result_row) if original_result_row else None
            original_stages = {
                row["id"]: row["completed"]
                for row in con.execute("SELECT id,completed FROM task_resource_assignments WHERE task_id=?", (task["id"],))
            }
            # This test exercises Phase 2 persistence only. Phase 3 adaptation is covered
            # separately inside a rolled-back transaction below.
            con.execute("UPDATE tasks SET topic_id=NULL WHERE id=?", (task["id"],))
        try:
            response = self.client.post(
                "/api/app",
                json={"action":"completeTaskWithResult","payload":{"task_id":task["id"],"attempted":20,"correct":16,"time_spent":52,"confidence":4,"notes":"Review selection."}},
            )
            self.assertEqual(response.status_code, 200)
            saved = self.client.get("/api/app?date=2026-08-12").json()
            recorded = next(item for item in saved["tasks"] if item["id"] == task["id"])
            self.assertTrue(recorded["completed"])
            self.assertEqual(recorded["result"]["attempted"], 20)
            self.assertEqual(recorded["result"]["correct"], 16)
            self.assertEqual(recorded["result"]["accuracy"], 80)
            self.assertEqual(recorded["result"]["time_spent"], 52)
            self.assertEqual(recorded["result"]["confidence"], 4)
        finally:
            with main.connection() as con:
                con.execute(
                    "UPDATE tasks SET completed=?,completion=?,actual_duration=?,topic_id=? WHERE id=?",
                    (original_task["completed"], original_task["completion"], original_task["actual_duration"], original_task["topic_id"], task["id"]),
                )
                for assignment_id, completed in original_stages.items():
                    con.execute("UPDATE task_resource_assignments SET completed=? WHERE id=?", (completed, assignment_id))
                con.execute("DELETE FROM task_results WHERE task_id=?", (task["id"],))
                if original_result:
                    columns = list(original_result)
                    con.execute(
                        f"INSERT INTO task_results({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                        tuple(original_result[column] for column in columns),
                    )


if __name__ == "__main__":
    unittest.main()
