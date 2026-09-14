import unittest

from workflow_mcp.server import workflow_start, workflow_status
from workflow_mcp.spec_loader import load_spec


class Phase0Tests(unittest.TestCase):
    def test_spec_loads(self) -> None:
        spec = load_spec()
        self.assertEqual(spec["name"], "workflow-mcp")
        self.assertEqual(spec["version"], "0.2.0")

    def test_workflow_start_and_status(self) -> None:
        started = workflow_start("Implement the workflow server")
        self.assertTrue(started["ok"])
        self.assertEqual(started["state"], "DISCOVERY")

        status = workflow_status(started["workflowId"])
        self.assertTrue(status["ok"])
        self.assertEqual(status["state"], "DISCOVERY")
        self.assertIsNone(status["planVersion"])

    def test_validation_and_not_found(self) -> None:
        self.assertEqual(workflow_start(" ")["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(workflow_status("missing")["error"]["code"], "WORKFLOW_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()

