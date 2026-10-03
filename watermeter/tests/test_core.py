"""Regresión de lectura, cascada de esferas, día/noche y seguimiento del entero."""

import os

import cv2
import numpy as np

from watermeter.config import load_calibration, load_config, validate_calibration
from watermeter.daynight import DayNightDetector
from watermeter.reader import Reader
from watermeter.reading import IntegerTracker, combine_dials, compose_reading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "config", "config.example.json")
CAL = os.path.join(ROOT, "config", "calibration.json")
SNAP = os.path.join(ROOT, "tests", "data", "snapshot.jpg")


def make_reader():
    return Reader(load_config(CFG), load_calibration(CAL))


def test_snapshot_reading():
    frame = cv2.imread(SNAP)
    r = make_reader().process(frame, commit=False)
    assert r["mode"] == "day"
    assert r["decimal"] == "8780"
    assert [d["angle"] for d in r["dials"]] == [51.77, 13.83, 23.55, 112.83]
    assert r["integer"] is None and r["reading"] is None  # sin sembrar


def test_step_is_fixed_36_degrees():
    cal = validate_calibration(
        {"dials": [{"name": "a", "x": .5, "y": .5, "r": .05, "zero_angle": 90,
                    "step_angle": 12.3, "tip_min_radius_ratio": .5}]}
    )
    assert set(cal["dials"][0]) == {"name", "x", "y", "r", "zero_angle"}


def _dials(positions):
    return [{"position": p} for p in positions]


def test_cascade_fixes_coarse_dial_near_rollover():
    # Lectura real 0.3960: la esfera gruesa marca 3.96 (casi en el 4) pero
    # las finas (9.6 y 6.0) dicen que todavía es un 3. Redondear cada esfera
    # por separado daría 4.
    text, frac = combine_dials(_dials([3.96, 9.6, 6.0, 0.0]))
    assert text == "3960"
    assert abs(frac - 0.396) < 1e-9
    # Lectura real 0.4001: la gruesa marca 3.98 pero la fina (0.02·10)
    # confirma que ya pasó el 4.
    text, _ = combine_dials(_dials([3.98, 0.2, 0.0, 1.0]))
    assert text[0] == "4"


def test_cascade_wrap_is_continuous():
    below = combine_dials(_dials([9.99, 9.99, 9.99, 9.9]))
    above = combine_dials(_dials([0.00, 0.00, 0.00, 0.1]))
    assert below[1] > 0.999 and above[1] < 0.001
    assert below[0] == "9999" and above[0] == "0000"


def test_missing_needle_gives_unknown():
    text, frac = combine_dials(_dials([1.0, None, 3.0, 4.0]))
    assert "?" in text and frac is None
    assert compose_reading(5, text, frac) is None


def test_daynight_hysteresis_and_force():
    d = DayNightDetector({"day_ratio": 0.05, "night_ratio": 0.02})
    modes = [d.update(x) for x in (0.3, 0.04, 0.015, 0.03, 0.06)]
    assert modes == ["day", "day", "night", "night", "day"]
    assert DayNightDetector({"mode": "night"}).decide(0.9) == "night"


def test_night_uses_dark_needle():
    frame = cv2.imread(SNAP)
    reader = make_reader()
    ref = reader.process(frame, commit=False)
    red = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), (0, 70, 40), (12, 255, 255))
    night = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    night[red > 0] = 25
    r = reader.process(night, commit=False)
    assert r["mode"] == "night" and r["day_ratio"] == 0.0
    assert r["decimal"] == ref["decimal"]


def test_integer_tracker_follows_wraps():
    t = IntegerTracker(None)
    t.set_integer(17, 0.90)
    seen = [t.update(f)["integer"] for f in (0.95, 0.99, 0.01, 0.03, 0.99, 0.02)]
    assert seen == [17, 17, 18, 18, 17, 18]


def test_integer_tracker_ocr_rules():
    assert IntegerTracker(None).update(0.5, ocr_integer=17)["integer"] is None
    assert IntegerTracker(None, auto_seed=True).update(0.5, ocr_integer=17)["integer"] == 17
    # rodillo de unidades a medio giro: el OCR no se usa
    assert IntegerTracker(None, auto_seed=True).update(0.9, ocr_integer=17)["integer"] is None
    t = IntegerTracker(None)
    t.set_integer(17, 0.5)
    assert t.update(0.5, ocr_integer=18)["ocr_mismatch"] is True


def test_integer_tracker_persists(tmp_path):
    path = str(tmp_path / "state.json")
    t = IntegerTracker(path)
    t.set_integer(42, 0.3)
    t2 = IntegerTracker(path)
    assert t2.integer == 42 and t2.source == "manual" and t2.prev_frac == 0.3


def test_full_reading_with_integer():
    frame = cv2.imread(SNAP)
    reader = make_reader()
    reader.tracker.set_integer(17)
    r = reader.process(frame, commit=False)
    assert r["reading"] == 17.878


def test_loop_skips_expensive_ocr_but_preview_runs_it():
    import watermeter.reader as rd

    frame = cv2.imread(SNAP)
    reader = make_reader()
    reader.tracker.set_integer(17)
    reader.tracker.ocr_trust_below = 0.95   # el snapshot tiene fracción 0.878
    calls = []
    real = rd.read_odometer
    rd.read_odometer = lambda f, o, use: calls.append(use) or real(f, o, use)
    try:
        reader.process(frame)                                   # bucle: toca verificar
        reader.process(frame)                                   # no otra vez hasta ocr_interval
        reader.process(frame, commit=False, with_strip=True)    # vista previa: siempre
    finally:
        rd.read_odometer = real
    # 1ª: OCR real; 2ª: ni se llama al odómetro; 3ª: OCR real de la vista previa
    assert calls == [True, True]


def test_loop_without_seed_never_runs_ocr():
    import watermeter.reader as rd

    frame = cv2.imread(SNAP)
    reader = make_reader()                  # entero sin sembrar y auto_seed off
    calls = []
    real = rd.read_odometer
    rd.read_odometer = lambda f, o, use: calls.append(use) or real(f, o, use)
    try:
        reader.process(frame)
    finally:
        rd.read_odometer = real
    assert calls == []


def test_loop_does_not_ocr_while_units_drum_is_rolling():
    import watermeter.reader as rd

    frame = cv2.imread(SNAP)                # fracción 0.878 >= 0.8: rodillo a medio giro
    reader = make_reader()
    reader.tracker.set_integer(17)
    calls = []
    real = rd.read_odometer
    rd.read_odometer = lambda f, o, use: calls.append(use) or real(f, o, use)
    try:
        reader.process(frame)
    finally:
        rd.read_odometer = real
    assert calls == []
