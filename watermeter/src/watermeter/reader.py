"""Orquesta la lectura de un fotograma y guarda el estado compartido."""

import threading
import time

from .config import save_calibration, validate_calibration
from .daynight import DayNightDetector, dials_red_ratio
from .odometer import read_odometer
from .reading import IntegerTracker, combine_dials, compose_reading
from .vision import analyse_dial, black_mask, red_mask


class Reader:
    """
    Estado compartido entre el bucle de captura y el servidor web:
    último fotograma, calibración en caliente, ciclo día/noche y parte
    entera. Todos los accesos pasan por un lock.
    """

    def __init__(self, cfg, calibration, calibration_path=None, state_path=None):
        self.cfg = cfg
        self.calibration = calibration
        self.calibration_path = calibration_path
        self.detector = DayNightDetector(cfg.get("day_night"))
        odo_cfg = cfg.get("odometer", {})
        self.use_ocr = bool(odo_cfg.get("ocr", True))
        # El OCR (Tesseract) cuesta ~2 s por fotograma: en el bucle sólo se
        # ejecuta como verificación periódica, no en cada ciclo.
        self.ocr_interval = float(odo_cfg.get("ocr_interval", 600))
        self._last_ocr = 0.0
        self._mismatch = False
        self.tracker = IntegerTracker(
            state_path,
            ocr_trust_below=float(odo_cfg.get("ocr_trust_below", 0.8)),
            auto_seed=bool(odo_cfg.get("auto_seed", False)),
        )
        self._lock = threading.RLock()
        self._frame = None
        self._frame_ts = None
        self.last_reading = None

    # -- fotograma ---------------------------------------------------------
    def set_frame(self, frame):
        with self._lock:
            self._frame = frame
            self._frame_ts = time.time()

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None, None
            return self._frame.copy(), self._frame_ts

    # -- calibración ---------------------------------------------------------
    def get_calibration(self):
        with self._lock:
            return validate_calibration(self.calibration)

    def update_calibration(self, cal, frame_shape=None):
        """Valida, guarda en disco (si hay ruta) y aplica en caliente."""
        cal = dict(cal)
        if frame_shape is not None:
            cal["image_height"], cal["image_width"] = frame_shape[:2]
        with self._lock:
            if self.calibration_path:
                clean = save_calibration(self.calibration_path, cal)
            else:
                clean = validate_calibration(cal)
            self.calibration = clean
            return clean

    # -- parte entera ----------------------------------------------------------
    def set_integer(self, value):
        with self._lock:
            frac = (self.last_reading or {}).get("fraction")
            self.tracker.set_integer(value, frac)

    def _ocr_due(self, frac):
        """¿Toca verificar/sembrar con OCR en este ciclo del bucle?"""
        if frac is None or frac >= self.tracker.ocr_trust_below:
            return False                       # rodillo de unidades a medio giro
        if self.tracker.integer is None and not self.tracker.auto_seed:
            return False                       # el OCR no tendría efecto
        return time.time() - self._last_ocr >= self.ocr_interval

    # -- lectura -------------------------------------------------------------
    def process(self, frame, calibration=None, commit=True, with_strip=False):
        """
        Lee un fotograma. Con commit=False (vista previa de una calibración
        sin guardar) no se modifica ningún estado.
        """
        with self._lock:
            cal = validate_calibration(calibration) if calibration else self.calibration
            dials = cal.get("dials", [])

            red = red_mask(frame)
            ratio = dials_red_ratio(red, dials) if dials else 0.0
            if commit:
                mode = self.detector.update(ratio)
            else:
                mode = self.detector.decide(ratio)
            mask = red if mode == "day" else black_mask(frame)

            results = [analyse_dial(mask, frame.shape, d, mode) for d in dials]
            digits_text, frac = combine_dials(results)

            odo_result = None
            ocr_integer = None
            odo_cfg = cal.get("odometer")
            if odo_cfg:
                do_ocr = self.use_ocr and (not commit or self._ocr_due(frac))
                if do_ocr or with_strip:
                    odo_result = read_odometer(frame, odo_cfg, do_ocr)
                    ocr_integer = odo_result["integer"]
                    if commit and do_ocr:
                        self._last_ocr = time.time()

            tracked = self.tracker.update(frac, ocr_integer, commit=commit)
            mismatch = self._mismatch
            if ocr_integer is not None and frac is not None and frac < self.tracker.ocr_trust_below:
                mismatch = tracked["ocr_mismatch"]
                if commit:
                    self._mismatch = mismatch
            reading = {
                "timestamp": int(time.time()),
                "mode": mode,
                "day_ratio": round(float(ratio), 4),
                "dials": results,
                "decimal": digits_text,
                "fraction": None if frac is None else round(frac, 6),
                "integer": tracked["integer"],
                "integer_source": tracked["integer_source"],
                "ocr_mismatch": mismatch,
                "reading": compose_reading(tracked["integer"], digits_text, frac),
                "odometer": None
                if odo_result is None
                else {
                    "ocr": odo_result["ocr"],
                    "text": odo_result["text"],
                    "digits": odo_result["digits"],
                },
            }
            if with_strip and odo_result is not None:
                reading["_strip"] = odo_result["strip"]
            if commit:
                self.last_reading = {k: v for k, v in reading.items() if k != "_strip"}
            return reading
