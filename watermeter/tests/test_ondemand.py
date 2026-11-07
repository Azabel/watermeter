"""Lectura bajo demanda: botón de HA (MQTT) y botón de la web."""

import json
import types

import cv2

from test_core import SNAP, make_reader
from test_server import start
from watermeter import capturer
from watermeter.cli import _setup_mqtt
from watermeter.publisher import create_mqtt_client


class FakeMqtt:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, json.loads(payload), retain))


def make_capturer(monkeypatch, tmp_path, delay=0):
    monkeypatch.setattr(capturer, "capture_frame", lambda url: cv2.imread(SNAP))
    monkeypatch.setattr(capturer, "save_debug", lambda *a, **k: None)
    cfg = {"camera": {"url": "rtsp://x", "capture_delay": delay},
           "mqtt": {"topic": "watermeter/state"}}
    reader = make_reader()
    reader.tracker.set_integer(17)
    cap = capturer.Capturer(reader, cfg, str(tmp_path))
    cap.mqtt_client = FakeMqtt()
    return cap


def test_read_now_publishes_retained_state(monkeypatch, tmp_path):
    cap = make_capturer(monkeypatch, tmp_path)
    reading = cap.read_now()
    assert reading["reading"] == 17.878
    topic, payload, retain = cap.mqtt_client.published[0]
    assert topic == "watermeter/state" and retain and payload["reading"] == 17.878


def test_capture_delay_is_applied(monkeypatch, tmp_path):
    slept = []
    monkeypatch.setattr(capturer.time, "sleep", slept.append)
    make_capturer(monkeypatch, tmp_path, delay=4).read_now()
    assert slept == [4.0]


def _message(payload, retain=False):
    return types.SimpleNamespace(payload=payload, retain=retain)


def test_mqtt_read_command_triggers_once_per_press():
    calls = []
    client = create_mqtt_client({})
    _setup_mqtt(client, {"host": "h", "topic": "watermeter/state"}, lambda: calls.append(1))
    client.on_message(client, None, _message(b"READ"))
    client.on_message(client, None, _message(b" read\n"))
    client.on_message(client, None, _message(b"OTRA"))
    client.on_message(client, None, _message(b"READ", retain=True))   # retenido: se ignora
    assert len(calls) == 2


def test_web_capture_button(monkeypatch, tmp_path):
    cap = make_capturer(monkeypatch, tmp_path)
    reader = cap.reader
    from watermeter.server import WebServer
    from test_server import Client
    server = WebServer(reader, "127.0.0.1", 0, capture=cap.read_now).start()
    try:
        status, _, raw = Client(server.port).call("POST", "/api/capture", {})
        assert status == 200 and json.loads(raw)["reading"] == 17.878
        assert reader.get_frame()[0] is not None
    finally:
        server.stop()


def test_web_capture_without_camera_is_501(tmp_path):
    _, server, client, _ = start(tmp_path)
    try:
        assert client.call("POST", "/api/capture", {})[0] == 501
    finally:
        server.stop()


def test_web_capture_reports_camera_error(tmp_path):
    reader, server, client, _ = start(tmp_path)
    server.stop()
    from watermeter.server import WebServer
    from test_server import Client

    def boom():
        raise RuntimeError("sin señal")

    s = WebServer(reader, "127.0.0.1", 0, capture=boom).start()
    try:
        status, _, raw = Client(s.port).call("POST", "/api/capture", {})
        assert status == 502 and "sin señal" in json.loads(raw)["error"]
    finally:
        s.stop()
