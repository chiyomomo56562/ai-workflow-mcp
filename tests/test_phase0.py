import unittest
import tempfile
from pathlib import Path

from workflow_mcp.db import connect, create_workflow, decode_payload, initialize, insert_artifact, transition_workflow
from workflow_mcp.models import WorkflowState
from workflow_mcp.services import WorkflowService
from workflow_mcp.spec_loader import load_spec


class Phase0Tests(unittest.TestCase):
    def test_spec_loads(self) -> None:
        spec = load_spec()
        self.assertEqual(spec["name"], "workflow-mcp")
        self.assertEqual(spec["version"], "0.2.0")

    def test_workflow_start_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = WorkflowService(database=str(Path(directory) / "workflow.sqlite3"))
            started = service.start("Implement the workflow server")
            status = service.status(started["workflowId"])
            service.connection.close()
        self.assertTrue(started["ok"])
        self.assertEqual(started["state"], "DISCOVERY")
        self.assertTrue(status["ok"])
        self.assertEqual(status["state"], "DISCOVERY")
        self.assertIsNone(status["planVersion"])

    def test_validation_and_not_found(self) -> None:
        service = WorkflowService()
        self.assertEqual(service.status("missing")["error"]["code"], "WORKFLOW_NOT_FOUND")

    def test_foreign_keys_and_start_event(self) -> None:
        connection = connect()
        initialize(connection)
        started = create_workflow(connection, "workflow-1", "task")
        self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        event = connection.execute(
            "SELECT event_type, to_state FROM workflow_event WHERE workflow_id = ?", (started["workflowId"],)
        ).fetchone()
        self.assertEqual(tuple(event), ("WORKFLOW_STARTED", "DISCOVERY"))
        with self.assertRaises(Exception):
            connection.execute(
                "INSERT INTO artifact(id, workflow_id, artifact_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                ("a", "missing", "CONTEXT", "{}", "now"),
            )

    def test_plan_and_approval_versions_are_unique(self) -> None:
        connection = connect()
        initialize(connection)
        create_workflow(connection, "workflow-1", "task")
        insert = (
            "INSERT INTO artifact(id, workflow_id, artifact_type, plan_version, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        )
        connection.execute(insert, ("p1", "workflow-1", "PLAN", 1, "{}", "now"))
        with self.assertRaises(Exception):
            connection.execute(insert, ("p2", "workflow-1", "PLAN", 1, "{}", "now"))
        connection.execute(insert, ("a1", "workflow-1", "APPROVAL", 1, "{}", "now"))
        with self.assertRaises(Exception):
            connection.execute(insert, ("a2", "workflow-1", "APPROVAL", 1, "{}", "now"))

    def test_transition_and_payload_are_atomic(self) -> None:
        connection = connect()
        initialize(connection)
        create_workflow(connection, "workflow-1", "task")
        transition_workflow(
            connection,
            "workflow-1",
            to_state=WorkflowState.PLANNING,
            event_type="DISCOVERY_COMPLETED",
            artifact={"id": "context-1", "artifact_type": "CONTEXT", "payload": {"sources": []}},
        )
        row = connection.execute("SELECT current_state FROM workflow WHERE id = 'workflow-1'").fetchone()
        payload = connection.execute("SELECT payload FROM artifact WHERE id = 'context-1'").fetchone()[0]
        self.assertEqual(row[0], "PLANNING")
        self.assertEqual(decode_payload(payload), {"sources": []})

        with self.assertRaises(ValueError):
            transition_workflow(
                connection,
                "workflow-1",
                to_state=WorkflowState.WAITING_APPROVAL,
                event_type="PLAN_CREATED",
                artifact={"id": "bad", "artifact_type": "PLAN", "payload": ["not", "an", "object"]},
            )
        self.assertEqual(connection.execute("SELECT current_state FROM workflow WHERE id = 'workflow-1'").fetchone()[0], "PLANNING")
        self.assertIsNone(connection.execute("SELECT 1 FROM artifact WHERE id = 'bad'").fetchone())

    def test_standalone_artifact_insert_is_transactional_and_transition_is_guarded(self) -> None:
        connection = connect()
        initialize(connection)
        create_workflow(connection, "workflow-1", "task")
        insert_artifact(connection, "context-1", "workflow-1", "CONTEXT", {"value": 1})
        self.assertIsNotNone(connection.execute("SELECT 1 FROM artifact WHERE id = 'context-1'").fetchone())
        with self.assertRaises(ValueError):
            transition_workflow(connection, "workflow-1", to_state=WorkflowState.COMPLETED, event_type="REVIEW_PASSED")
        self.assertEqual(connection.execute("SELECT current_state FROM workflow WHERE id = 'workflow-1'").fetchone()[0], "DISCOVERY")


if __name__ == "__main__":
    unittest.main()
