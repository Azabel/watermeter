"""La lectura publicada nunca baja; sólo "Fijar" (set_integer) la reinicia."""

import cv2

from test_core import SNAP, make_reader
from watermeter.reading import IntegerTracker


def test_reader_holds_and_reports_consistent_fields():
    frame = cv2.imread(SNAP)
    reader = make_reader()
    reader.tracker.set_integer(17)
    assert reader.process(frame)["reading"] == 17.878      # snapshot: 17,878
    reader.tracker.integer = 16                            # el seguimiento "retrocede"
    r = reader.process(frame)
    assert r["held"] and r["reading"] == 17.878
    assert (r["integer"], r["decimal"]) == (17, "8780")
    reader.set_integer(16)                                 # Fijar: permite bajar
    assert reader.process(frame)["reading"] == 16.878


def test_never_decreases():
    t = IntegerTracker(None)
    assert t.floor_reading(22.8776) == (22.8776, False)
    assert t.floor_reading(22.8780) == (22.8780, False)
    assert t.floor_reading(22.8770) == (22.8780, True)     # ruido hacia abajo
    assert t.floor_reading(21.9000) == (22.8780, True)     # entero mal seguido
    assert t.floor_reading(22.8790) == (22.8790, False)    # sigue subiendo


def test_unknown_reading_is_not_held():
    t = IntegerTracker(None)
    t.floor_reading(10.0)
    assert t.floor_reading(None) == (None, False)
    assert t.high_water == 10.0


def test_large_jump_needs_confirmation():
    t = IntegerTracker(None)
    t.floor_reading(10.0)
    assert t.floor_reading(11.0) == (10.0, True)           # pico aislado: retenido
    assert t.floor_reading(10.001) == (10.001, False)      # vuelve a lo normal
    assert t.floor_reading(11.0) == (10.001, True)         # el pico anterior ya no cuenta
    assert t.floor_reading(11.01) == (11.01, False)        # dos ciclos coherentes: real


def test_preview_does_not_change_state():
    t = IntegerTracker(None)
    t.floor_reading(10.0)
    assert t.floor_reading(10.5, commit=False) == (10.0, True)
    assert t.high_water == 10.0 and t._pending is None


def test_set_integer_resets_high_water(tmp_path):
    t = IntegerTracker(str(tmp_path / "s.json"))
    t.set_integer(22)
    t.floor_reading(22.9)
    t.set_integer(21)                                      # corrección manual hacia abajo
    assert t.high_water is None
    assert t.floor_reading(21.5) == (21.5, False)


def test_high_water_persists(tmp_path):
    path = str(tmp_path / "s.json")
    t = IntegerTracker(path)
    t.set_integer(22)
    t.floor_reading(22.9)
    t.save()
    assert IntegerTracker(path).high_water == 22.9
