import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import db, insights


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for key, value in (("DATA", Path(self.tmp.name)), ("DB", Path(self.tmp.name) / "test.db")):
            p = patch.object(db, key, value)
            p.start()
            self.addCleanup(p.stop)
        db.init()
        app = FastAPI()
        app.include_router(insights.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_empty(self):
        self.assertEqual(self.client.get("/api/insights/dashboard").json()["devices"], 0)

    def test_duplicate_ips(self):
        for ip in ("10.0.0.1", "10.0.0.1", " ", " "):
            db.insert("devices", {"name": "test", "ip": ip})
        result = self.client.get("/api/insights/dashboard").json()
        self.assertEqual(len(result["duplicate_ips"]), 1)
        self.assertEqual(result["duplicate_ips"][0]["ip"], "10.0.0.1")

    def test_cycle(self):
        a = db.insert("devices", {"name": "a"})
        b = db.insert("devices", {"name": "b", "parent_id": a})
        db.update("devices", a, {"parent_id": b})
        self.assertEqual(self.client.get(f"/api/insights/impact/{a}").json()["contained_device_ids"], [b])

    def test_missing(self):
        self.assertEqual(self.client.get("/api/insights/impact/999").status_code, 404)

    def test_history(self):
        a = db.insert("devices", {"name": "a"})
        db.update("devices", a, {"status": "offline"})
        db.update("devices", a, {"status": "offline"})
        first = self.client.get("/api/insights/history?limit=1").json()
        self.assertEqual(first["events"][0]["after_value"]["status"], "offline")
        second = self.client.get("/api/insights/history", params={"before_id": first["next_before_id"]}).json()
        self.assertEqual(len(second["events"]), 1)
        self.assertEqual(second["events"][0]["action"], "insert")

    def test_rollback(self):
        with self.assertRaises(RuntimeError):
            with db.conn() as c:
                c.execute("INSERT INTO devices(name) VALUES ('rollback')")
                raise RuntimeError("rollback")
        self.assertEqual(db.q("SELECT * FROM infrastructure_history"), [])

    def test_init_idempotent(self):
        db.init()
        db.insert("devices", {"name": "test"})
        self.assertEqual(len(db.q("SELECT * FROM infrastructure_history")), 1)
