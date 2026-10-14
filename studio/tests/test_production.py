"""Production API integration tests with FastAPI TestClient."""
import os
import tempfile
import unittest

class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        os.environ["CINEMA_DATA_DIR"] = cls.dir.name
        from fastapi.testclient import TestClient
        from studio import server
        from pathlib import Path
        server.ROOT = Path(cls.dir.name)
        server.DB = server.ROOT / 'projects.sqlite3'
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.dir.cleanup()

    def test_shot_edit_move_export(self):
        c = self.client
        project = c.post("/api/projects", json={"name": "Feature Validation"}).json()["id"]
        a = c.post(f"/api/projects/{project}/shots",json={"prompt":"First shot","duration":2})
        b = c.post(f"/api/projects/{project}/shots",json={"prompt":"Second shot","duration":3})
        self.assertEqual(a.status_code,201)
        self.assertEqual(b.status_code,201)
        a_id,b_id=a.json()["id"],b.json()["id"]
        edited=c.patch(f"/api/projects/{project}/shots/{a_id}",
                       json={"prompt":"Revised first shot","duration":4.5})
        self.assertEqual(edited.status_code,200)
        self.assertEqual(edited.json()["duration"],4.5)
        moved=c.put(f"/api/projects/{project}/sequence",json={"shot_ids":[b_id,a_id]})
        self.assertEqual(moved.status_code,200)
        export=c.get(f"/api/projects/{project}/export")
        self.assertEqual(export.status_code,200)
        self.assertEqual(export.json()["runtime_seconds"],7.5)
        self.assertEqual(export.json()["timeline"][0]["shot_id"],b_id)
        self.assertEqual(export.json()["timeline"][1]["start_seconds"],3.0)

    def test_reject_invalid_sequence(self):
        c=self.client
        project=c.post("/api/projects",json={"name":"Guardrails"}).json()["id"]
        shot=c.post(f"/api/projects/{project}/shots",json={"prompt":"A shot"}).json()["id"]
        bad=c.put(f"/api/projects/{project}/sequence",json={"shot_ids":[shot,shot]})
        self.assertEqual(bad.status_code,400)
        invalid=c.patch(f"/api/projects/{project}/shots/{shot}",
                        json={"duration":-1})
        self.assertEqual(invalid.status_code,422)
