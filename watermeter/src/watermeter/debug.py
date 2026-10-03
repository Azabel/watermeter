"""Imagen de depuración y salida por consola."""

import os

import cv2

import numpy as np

from .odometer import odometer_quads
from .vision import dial_geometry


def draw_debug(img, reading, calibration):
    output = img.copy()
    results = reading["dials"]

    for dial, result in zip(calibration["dials"], results):
        cx, cy, radius = dial_geometry(output, dial)
        cx_i = int(round(cx))
        cy_i = int(round(cy))
        r_i = int(round(radius))

        # Círculo calibrado y centro calibrado.
        cv2.circle(output, (cx_i, cy_i), r_i, (255, 255, 255), 2)
        cv2.circle(output, (cx_i, cy_i), 3, (255, 255, 0), -1)

        base = result.get("base")
        tip = result.get("tip")

        if base and tip:
            bx, by = base
            tx, ty = tip

            # Centro del "culo" encontrado por distance transform.
            cv2.circle(output, (bx, by), 6, (0, 255, 0), -1)

            # Punta extrema del componente conectado.
            cv2.circle(output, (tx, ty), 5, (255, 0, 0), -1)

            # Vector real usado para el ángulo.
            cv2.line(output, (bx, by), (tx, ty), (255, 255, 255), 3)

        label = (
            f'{result["name"]} '
            f'd={result["digit"]} '
            f'a={result["angle"]:.1f}deg '
            f'{result["mode"]} '
            f's={result["score"]:.2f}'
        )

        text_x = max(5, cx_i - r_i)
        text_y = max(20, cy_i - r_i - 8)

        cv2.putText(
            output,
            label,
            (text_x, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    odo = calibration.get("odometer")
    if odo:
        for quad in odometer_quads(output.shape, odo):
            pts = np.array(quad, dtype=np.int32).reshape(-1, 1, 2)
            cv2.polylines(output, [pts], True, (0, 255, 255), 2)

    total = reading.get("reading")
    header = (
        f'{reading["mode"]}  '
        f'int={reading["integer"] if reading["integer"] is not None else "?"}  '
        f'dec={reading["decimal"]}  '
        f'total={"?" if total is None else f"{total:.4f}"} m3'
    )
    cv2.rectangle(output, (0, output.shape[0] - 34), (output.shape[1], output.shape[0]), (0, 0, 0), -1)
    cv2.putText(output, header, (10, output.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    return output


def save_debug(frame, reading, calibration, debug_dir):
    os.makedirs(debug_dir, exist_ok=True)
    debug = draw_debug(frame, reading, calibration)
    path = os.path.join(debug_dir, "latest.jpg")
    if not cv2.imwrite(path, debug):
        raise RuntimeError(f"No se pudo escribir {path}")
    return path


def print_results(reading, image_path=None):
    print("\nRESULTADOS")
    print("=" * 72)

    for result in reading["dials"]:
        pos = result["position"]
        print(
            f'{result["name"]:10s} '
            f'digit={result["digit"]:2d} '
            f'pos={"  -  " if pos is None else f"{pos:5.2f}"} '
            f'angle={result["angle"]:7.2f}° '
            f'score={result["score"]:5.3f} '
            f'base={str(result.get("base")):>14s} '
            f'tip={str(result.get("tip")):>14s}'
        )

    print("-" * 72)
    print(f'Modo:       {reading["mode"]} (rojo={reading["day_ratio"]:.3f})')
    print(f'Decimal:    {reading["decimal"]}')
    odo = reading.get("odometer")
    if odo is not None:
        state = "" if odo["ocr"] else "  (OCR no disponible: instala tesseract)"
        print(f'OCR rodillos: {odo["text"]}{state}')
    integer = reading["integer"]
    if integer is None:
        print("Entero:     sin sembrar (usa --set-integer N o la web)")
    else:
        print(f"Entero:     {integer} ({reading['integer_source']})")
    total = reading["reading"]
    print(f'LECTURA:    {"desconocida" if total is None else f"{total:.4f} m3"}')
    if reading.get("ocr_mismatch"):
        print("AVISO: el OCR de los rodillos no coincide con el entero seguido")
    if image_path:
        print(f"Debug:      {image_path}")
    print()
