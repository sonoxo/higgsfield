"""Run: .venv/bin/python -m unittest discover -s studio/tests -v"""
import os
import tempfile
import unittest

with tempfile.TemporaryDirectory() as_unused:
    pass


class StudioSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ["CINEMA_DATA_DIR"] = cls.temp.name
        from fastapi.testclient import TestClient
        from studio import server
        from pathlib import Path
        server.ROOT = Path(cls.temp.name)
        server.DB = server.ROOT / 'projects.sqlite3'
        cls.client = TestClient(server.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.temp.cleanup()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_static_frontend(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CINEMA", response.text)

    def test_project_and_shot(self):
        create = self.client.post("/api/projects", json={"name": "Production"})
        self.assertEqual(create.status_code, 201)
        project_id = create.json()["id"]
        shot = self.client.post(f"/api/projects/{project_id}/shots",
                                json={"prompt": "An establishing shot", "duration": 4})
        self.assertEqual(shot.status_code, 201)
        project = self.client.get(f"/api/projects/{project_id}").json()
        self.assertEqual(len(project["shots"]), 1)
        self.assertEqual(project["shots"][0]["prompt"], "An establishing shot")
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/render").status_code, 400
                         if self.client.get("/api/health").json()["ffmpeg"] else 503)

    def test_model_configuration(self):
        response = self.client.get("/api/models")
        self.assertEqual(response.status_code, 200)
        self.assertIn("providers", response.json())

    def test_deterministic_prompt(self):
        response = self.client.post("/api/prompts/expand", json={"idea": "Rain on neon streets"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Rain on neon streets", response.json()["prompt"])
