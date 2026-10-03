"""Servidor HTTP integrado: cámara falsa = snapshot."""

import http.client
import json
import os

import cv2

from watermeter.config import load_calibration, load_config
from watermeter.reader import Reader
from watermeter.server import WebServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "config.example.json")
CAL = os.path.join(ROOT, "config", "calibration.json")
SNAP = os.path.join(ROOT, "tests", "data", "snapshot.jpg")


class Client:
    def __init__(self, port):
        self.port = port

    def call(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        data = None if body is None else json.dumps(body)
        c.request(method, path, body=data, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, r.getheader("Content-Type"), raw


def start(tmp_path, with_frame=True):
    cal_path = str(tmp_path / "calibration.json")
    reader = Reader(load_config(CFG), load_calibration(CAL), cal_path, str(tmp_path / "state.json"))
    if with_frame:
        reader.set_frame(cv2.imread(SNAP))
    server = WebServer(reader, "127.0.0.1", 0).start()
    return reader, server, Client(server.port), cal_path


def test_index_and_frame(tmp_path):
    reader, server, c, _ = start(tmp_path)
    try:
        st, ct, body = c.call("GET", "/")
        assert st == 200 and "text/html" in ct and b"Calibraci" in body
        st, ct, body = c.call("GET", "/api/frame.jpg")
        assert st == 200 and ct == "image/jpeg" and body[:2] == b"\xff\xd8"
        assert c.call("GET", "/nope")[0] == 404
    finally:
        server.stop()


def test_no_frame_yet(tmp_path):
    _, server, c, _ = start(tmp_path, with_frame=False)
    try:
        assert c.call("GET", "/api/frame.jpg")[0] == 503
        assert c.call("POST", "/api/analyse", {})[0] == 503
    finally:
        server.stop()


def test_analyse_preview_does_not_touch_state(tmp_path):
    reader, server, c, _ = start(tmp_path)
    try:
        cal = reader.get_calibration()
        st, _, raw = c.call("POST", "/api/analyse", {"calibration": cal})
        out = json.loads(raw)
        assert st == 200 and out["decimal"] == "8780"
        assert out["strip_png"].startswith("data:image/png;base64,")
        assert reader.last_reading is None           # vista previa: sin commit
        assert reader.tracker.prev_frac is None
    finally:
        server.stop()


def test_save_calibration_hot_reload(tmp_path):
    reader, server, c, cal_path = start(tmp_path)
    try:
        cal = reader.get_calibration()
        cal["dials"][0]["zero_angle"] = 100.0        # cambia el cero de la 1ª esfera
        st, _, raw = c.call("POST", "/api/calibration", cal)
        assert st == 200
        saved = json.load(open(cal_path))
        assert saved["dials"][0]["zero_angle"] == 100.0
        assert saved["image_width"] == 1920 and saved["image_height"] == 1080
        assert reader.calibration["dials"][0]["zero_angle"] == 100.0   # aplicada ya
        assert not os.path.exists(cal_path + ".tmp")
    finally:
        server.stop()


def test_invalid_calibration_rejected(tmp_path):
    reader, server, c, cal_path = start(tmp_path)
    try:
        before = reader.get_calibration()
        bad = {"dials": [{"name": "a", "x": 5, "y": .5, "r": .05, "zero_angle": 0}]}
        st, _, raw = c.call("POST", "/api/calibration", bad)
        assert st == 400 and "error" in json.loads(raw)
        assert reader.get_calibration() == before and not os.path.exists(cal_path)
        assert c.call("POST", "/api/calibration", {"dials": "x"})[0] == 400
    finally:
        server.stop()


def test_set_integer_and_status(tmp_path):
    reader, server, c, _ = start(tmp_path)
    try:
        assert c.call("POST", "/api/integer", {"integer": "17"})[0] == 400
        assert c.call("POST", "/api/integer", {"integer": -1})[0] == 400
        st, _, raw = c.call("POST", "/api/integer", {"integer": 17})
        assert st == 200 and json.loads(raw)["integer"] == 17
        reader.process(reader.get_frame()[0])        # commit
        st, _, raw = c.call("GET", "/api/status")
        s = json.loads(raw)
        assert s["reading"]["reading"] == 17.878 and s["integer_source"] == "manual"
    finally:
        server.stop()
