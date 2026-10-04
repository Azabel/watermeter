"""
Composición de la lectura final.

* Esferas decimales: cada aguja da una posición continua (0-10). El dígito
  de una esfera se corrige con la posición de la esfera más fina que la
  sigue (la de la derecha en la lista): si la fina acaba de pasar por 0,
  la gruesa debe estar justo pasada la marca, aunque su aguja parezca
  quedarse un poco antes. Sin esta corrección, redondear cada esfera por
  separado da lecturas absurdas en los cambios de dígito.

* Parte entera (rodillos): el OCR de rodillos borrosos o a medio giro no es
  fiable, así que el entero se SIGUE: cuando la fracción decimal da la
  vuelta (0.99 -> 0.01) el entero sube 1. Se siembra una vez (a mano, o
  por OCR si está activado) y se guarda en un fichero de estado.
"""

import json
import math
import os
import time

from .log import log


def combine_dials(results):
    """
    Asigna `digit` a cada resultado de esfera (orden: de la más gruesa a la
    más fina). Devuelve (cadena de dígitos, fracción continua 0-1 o None).
    """
    n = len(results)
    digits = [None] * n
    finer = None  # posición continua de la esfera más fina ya procesada

    for i in range(n - 1, -1, -1):
        p = results[i].get("position")
        if p is None:
            finer = None
            continue
        if finer is None:
            digit = int(math.floor(p)) % 10
        else:
            digit = int(math.floor(p - finer / 10.0 + 0.5)) % 10
        digits[i] = digit
        finer = p

    for result, digit in zip(results, digits):
        result["digit"] = -1 if digit is None else int(digit)

    text = "".join("?" if d is None else str(d) for d in digits)

    if n == 0 or any(d is None for d in digits):
        return text, None

    t = results[-1]["position"] / 10.0
    for i in range(n - 2, -1, -1):
        t = (digits[i] + t) / 10.0
    return text, float(t)


class IntegerTracker:
    """Sigue la parte entera del contador a partir de las vueltas de la fracción."""

    SAVE_EVERY_S = 60.0
    # La lectura publicada nunca baja (ver floor_reading). Como esa "marca
    # máxima" haría permanente un pico erróneo, un salto hacia arriba mayor
    # que JUMP_CONFIRM m³ sólo se acepta si dos ciclos seguidos coinciden
    # (dentro de JUMP_TOLERANCE).
    JUMP_CONFIRM = 0.1
    JUMP_TOLERANCE = 0.05

    def __init__(self, state_path=None, ocr_trust_below=0.8, auto_seed=False):
        self.state_path = state_path
        self.ocr_trust_below = float(ocr_trust_below)
        self.auto_seed = bool(auto_seed)
        self.integer = None
        self.source = None
        self.prev_frac = None
        self.high_water = None   # mayor lectura total publicada (m³)
        self._pending = None     # salto grande a la espera de confirmación
        self._last_save = 0.0
        self._load()

    # -- persistencia ---------------------------------------------------
    def _load(self):
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("integer") is not None:
                self.integer = int(data["integer"])
                self.source = data.get("source", "state")
                pf = data.get("prev_frac")
                self.prev_frac = None if pf is None else float(pf)
                hw = data.get("high_water")
                self.high_water = None if hw is None else float(hw)
        except (OSError, ValueError, TypeError) as exc:
            log(f"AVISO: no se pudo leer {self.state_path}: {exc}")

    def save(self):
        if not self.state_path:
            return
        data = {
            "integer": self.integer,
            "source": self.source,
            "prev_frac": self.prev_frac,
            "high_water": self.high_water,
            "updated": int(time.time()),
        }
        tmp = self.state_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.state_path)
            self._last_save = time.time()
        except OSError as exc:
            log(f"AVISO: no se pudo guardar {self.state_path}: {exc}")

    # -- API --------------------------------------------------------------
    def set_integer(self, value, frac=None):
        value = int(value)
        if value < 0:
            raise ValueError("La parte entera no puede ser negativa")
        self.integer = value
        self.source = "manual"
        # Corrección manual: es la única vía para que la lectura baje.
        self.high_water = None
        self._pending = None
        if frac is not None:
            self.prev_frac = float(frac)
        self.save()

    def floor_reading(self, reading, commit=True):
        """
        Hace que la lectura total nunca disminuya. Devuelve (valor, retenida):
        si la lectura nueva es menor que la máxima ya vista, o es un salto
        grande aún sin confirmar, se devuelve la máxima y retenida=True.
        Con commit=False no se modifica el estado (vista previa).
        """
        if reading is None:
            return None, False
        hw = self.high_water
        if hw is None:
            if commit:
                self.high_water = reading
            return reading, False
        if reading < hw - 1e-9:
            if commit:
                self._pending = None
            return hw, True
        if reading - hw > self.JUMP_CONFIRM:
            confirmed = (
                self._pending is not None
                and abs(reading - self._pending) <= self.JUMP_TOLERANCE
            )
            if not confirmed:
                if commit:
                    self._pending = reading
                    log(f"AVISO: salto de {reading - hw:.4f} m3 a la espera de "
                        "confirmación; se mantiene la lectura anterior")
                return hw, True
        if commit:
            self.high_water = max(hw, reading)
            self._pending = None
        return max(hw, reading), False

    def update(self, frac, ocr_integer=None, commit=True):
        """
        frac: fracción decimal actual (0-1) o None si alguna esfera falló.
        ocr_integer: entero leído por OCR (todos los rodillos legibles) o None.
        Devuelve dict con integer, source y ocr_mismatch.
        """
        integer = self.integer
        source = self.source
        prev = self.prev_frac

        if integer is not None and prev is not None and frac is not None:
            delta = frac - prev
            if delta < -0.5:        # la fracción dio la vuelta: 0.99 -> 0.01
                integer += 1
                source = "tracked"
            elif delta > 0.5:       # vuelta atrás: 0.01 -> 0.99
                integer = max(0, integer - 1)
                source = "tracked"

        # El rodillo de unidades sólo está quieto (y legible) mientras la
        # fracción está lejos de la vuelta.
        ocr_usable = (
            ocr_integer is not None
            and frac is not None
            and frac < self.ocr_trust_below
        )
        mismatch = False
        if ocr_usable:
            if integer is None:
                if self.auto_seed:
                    integer = int(ocr_integer)
                    source = "ocr"
            else:
                mismatch = int(ocr_integer) != integer

        if commit:
            changed = integer != self.integer
            self.integer = integer
            self.source = source
            if frac is not None:
                self.prev_frac = float(frac)
            if changed or (
                integer is not None
                and time.time() - self._last_save >= self.SAVE_EVERY_S
            ):
                self.save()

        return {"integer": integer, "integer_source": source, "ocr_mismatch": mismatch}


def compose_reading(integer, digits_text, frac):
    """Lectura total en m³, o None si falta la parte entera o alguna esfera."""
    if integer is None or frac is None or "?" in digits_text:
        return None
    return round(int(integer) + int(digits_text) / (10 ** len(digits_text)), len(digits_text))
