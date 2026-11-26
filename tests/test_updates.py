import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import connectors, db, monitor, updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for key, value in (("DATA", Path(self.tmp.name)), ("DB", Path(self.tmp.name) / "test.db")):
            p = patch.object(db, key, value)
            p.start()
            self.addCleanup(p.stop)
        db.init()
        self.sent = []
        q = patch.object(monitor, "queue", lambda text, area="other", event="down": self.sent.append((text, event)))
        q.start()
        self.addCleanup(q.stop)
        app = FastAPI()
        app.include_router(updates.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def item(self, latest, avail=True):
        return [{"key": "unifi:firmware", "title": "Firmware", "installed": "6.6.77", "latest": latest, "available": avail}]

    def test_notify_once_per_version(self):
        d = db.insert("devices", {"name": "AP", "type": "ap"})
        self.assertEqual(updates.record(d, "unifi", self.item("6.7.10")), 1)
        updates.record(d, "unifi", self.item("6.7.10"))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][1], "update")
        updates.record(d, "unifi", self.item("6.7.12"))          # neuere Version → neue Meldung
        self.assertEqual(len(self.sent), 2)

    def test_skip_until_newer(self):
        d = db.insert("devices", {"name": "AP", "type": "ap"})
        updates.record(d, "unifi", self.item("6.7.10"))
        self.assertEqual(self.client.post(f"/api/updates/{d}/skip", json={"key": "unifi:firmware"}).status_code, 200)
        dev = db.one("SELECT * FROM devices WHERE id=?", (d,))
        self.assertEqual(updates.pending(dev), [])
        updates.record(d, "unifi", self.item("6.7.12"))
        dev = db.one("SELECT * FROM devices WHERE id=?", (d,))
        self.assertEqual(len(updates.pending(dev)), 1)

    def test_sources_are_kept_apart(self):
        d = db.insert("devices", {"name": "HA", "type": "server"})
        updates.record(d, "homeassistant", [{"key": "ha:update.core", "title": "Core", "available": True, "latest": "2"}])
        updates.record(d, "proxmox", [{"key": "proxmox:apt", "title": "Pakete", "available": False}])
        meta = db.one("SELECT meta FROM devices WHERE id=?", (d,))["meta"]
        self.assertEqual({u["source"] for u in meta["updates"]}, {"homeassistant", "proxmox"})

    def test_opnsense_parse(self):
        r = {"status": "update", "updates": "12", "product": {"product_version": "25.7.3", "product_latest": "25.7.5"}}
        it = connectors.opnsense_firmware_parse(r)
        self.assertTrue(it["available"])
        self.assertEqual(it["count"], 12)
        self.assertFalse(connectors.opnsense_firmware_parse({"status": "none", "product": {"product_version": "25.7.5",
                                                                                           "product_latest": "25.7.5"}})["available"])
        self.assertIsNone(connectors.opnsense_firmware_parse({"status": "error"}))

    def test_version_order(self):
        self.assertLess(connectors._vkey("24.7.10_1"), connectors._vkey("24.7.11"))
        self.assertLess(connectors._vkey("24.7.11"), connectors._vkey("25.1"))

    def test_synology_parse(self):
        it = connectors.synology_update_parse({"update": {"available": True, "version": "7.2.2-72806"}}, "DSM 7.2.1-69057")
        self.assertEqual((it["installed"], it["latest"], it["available"]), ("7.2.1-69057", "7.2.2-72806", True))
        self.assertIsNone(connectors.synology_update_parse({"something": 1}, "DSM 7.2"))
        self.assertIsNone(connectors.synology_update_parse(None, "DSM 7.2"))


if __name__ == "__main__":
    unittest.main()
