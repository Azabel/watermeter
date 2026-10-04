"""Captura por ciclo (conectar, leer, desconectar) y formato del log."""

import re

import pytest

from watermeter import camera
from watermeter.log import log


class FakeCap:
    def __init__(self, fail_at=None):
        self.reads = 0
        self.released = False
        self.fail_at = fail_at

    def read(self):
        self.reads += 1
        if self.reads == self.fail_at:
            return False, None
        return True, f"frame{self.reads}"

    def release(self):
        self.released = True


def test_capture_frame_discards_and_releases(monkeypatch):
    cap = FakeCap()
    monkeypatch.setattr(camera, "open_camera", lambda url: cap)
    assert camera.capture_frame("rtsp://x", discard=2) == "frame3"
    assert cap.reads == 3 and cap.released


def test_capture_frame_releases_on_error(monkeypatch):
    cap = FakeCap(fail_at=2)
    monkeypatch.setattr(camera, "open_camera", lambda url: cap)
    with pytest.raises(RuntimeError):
        camera.capture_frame("rtsp://x", discard=2)
    assert cap.released


def test_log_has_timestamp(capsys):
    log("hola")
    out = capsys.readouterr().out
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d hola\n", out)
