"""
Rodillos numéricos (parte entera).

Geometría (en coordenadas normalizadas, como las esferas):
  x1,y1  centro del primer rodillo (el más significativo)
  x2,y2  centro del último rodillo (unidades)
  hw     semialto de la caja de un rodillo (relativo a min(ancho, alto))
  digits número de rodillos

El eje primero->último es el sentido de lectura: se endereza la tira para
que ese eje quede horizontal y los dígitos derechos (la parte superior de
los dígitos queda a la izquierda del eje, según se avanza de primero a
último), sea cual sea el ángulo al que esté montada la cámara.
"""

import math
import shutil

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:  # OCR opcional
    pytesseract = None

CELL_W = 96
OCR_MARGINS = (0.08, 0.10, 0.12, 0.14, 0.16)
OCR_MIN_CONF = 60


def ocr_available():
    return pytesseract is not None and shutil.which("tesseract") is not None


def odometer_points(shape, odo):
    """(primero, último, semialto en px, nº de rodillos, paso en px)."""
    h, w = shape[:2]
    n = int(odo["digits"])
    first = np.array([float(odo["x1"]) * w, float(odo["y1"]) * h])
    last = np.array([float(odo["x2"]) * w, float(odo["y2"]) * h])
    hw = float(odo["hw"]) * min(w, h)
    pitch = np.linalg.norm(last - first) / max(1, n - 1)
    return first, last, hw, n, pitch


def odometer_quads(shape, odo):
    """Un cuadrilátero (4 puntos en px) por rodillo, para dibujar."""
    first, last, hw, n, pitch = odometer_points(shape, odo)
    axis = last - first
    length = np.linalg.norm(axis)
    if length < 1e-6:
        return []
    u = axis / length
    v = np.array([-u[1], u[0]])
    origin = first - u * pitch / 2
    quads = []
    for i in range(n):
        a = origin + u * pitch * i
        quads.append([a - v * hw, a + u * pitch - v * hw,
                      a + u * pitch + v * hw, a + v * hw])
    return quads


def extract_strip(frame, odo, cell_w=CELL_W):
    """Tira enderezada con los n rodillos en fila. Devuelve la imagen BGR."""
    first, last, hw, n, pitch = odometer_points(frame.shape, odo)
    axis = last - first
    length = np.linalg.norm(axis)
    if length < 1e-6 or hw < 1 or pitch < 1:
        raise ValueError("Geometría de odómetro inválida")
    u = axis / length
    v = np.array([-u[1], u[0]])
    origin = first - u * pitch / 2 - v * hw
    ch = max(8, int(round(cell_w * 2 * hw / pitch)))
    src = np.float32([origin, origin + u * pitch * n, origin + v * 2 * hw])
    dst = np.float32([[0, 0], [cell_w * n, 0], [0, ch]])
    matrix = cv2.getAffineTransform(src, dst)
    return cv2.warpAffine(frame, matrix, (cell_w * n, ch), flags=cv2.INTER_CUBIC)


def _prepare(cell, margin):
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    mx, my = int(w * margin), int(h * margin)
    g = g[my:h - my, mx:w - mx]
    g = cv2.GaussianBlur(g, (3, 3), 0)
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(
        g, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=int(np.median(g))
    )


def _ocr_variant(cell, margin):
    data = pytesseract.image_to_data(
        _prepare(cell, margin),
        config="--psm 10 -c tessedit_char_whitelist=0123456789",
        output_type=pytesseract.Output.DICT,
    )
    found = [
        (t.strip(), float(c))
        for t, c in zip(data["text"], data["conf"])
        if t.strip()
    ]
    if len(found) != 1 or len(found[0][0]) != 1:
        return None
    return int(found[0][0]), found[0][1]


def ocr_drums(strip, n):
    """
    Lee cada rodillo repitiendo el OCR con varios recortes. Un dígito se
    acepta sólo si ninguna variante discrepa y al menos una lo lee con
    confianza alta; si no, se devuelve None (mejor "?" que un dígito
    inventado: con imagen borrosa Tesseract confunde 1 y 7 con seguridad).
    """
    cell_w = strip.shape[1] // n
    out = []
    for i in range(n):
        cell = strip[:, i * cell_w:(i + 1) * cell_w]
        votes = [v for v in (_ocr_variant(cell, m) for m in OCR_MARGINS) if v]
        digits = {v[0] for v in votes}
        if len(digits) != 1 or max(v[1] for v in votes) < OCR_MIN_CONF:
            out.append(None)
            continue
        out.append(digits.pop())
    return out


def read_odometer(frame, odo, use_ocr=True):
    """
    Devuelve {"strip": imagen, "digits": [int|None], "text": "0001?",
    "integer": int|None, "ocr": bool}. `integer` sólo si todos los
    rodillos se leyeron.
    """
    strip = extract_strip(frame, odo)
    n = int(odo["digits"])
    do_ocr = bool(use_ocr) and ocr_available()
    digits = ocr_drums(strip, n) if do_ocr else [None] * n
    text = "".join("?" if d is None else str(d) for d in digits)
    integer = None if (not do_ocr or any(d is None for d in digits)) else int(text)
    return {
        "strip": strip,
        "digits": digits,
        "text": text,
        "integer": integer,
        "ocr": do_ocr,
    }
