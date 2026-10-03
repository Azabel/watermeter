"""Análisis de imagen: detección de la aguja de cada esfera y su dígito."""

import math

import cv2
import numpy as np

# Las cuatro esferas tienen 10 posiciones.
DIAL_STEP_DEG = 36.0


def red_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 70, 40], dtype=np.uint8)
    upper1 = np.array([12, 255, 255], dtype=np.uint8)
    lower2 = np.array([165, 70, 40], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)

    m1 = cv2.inRange(hsv, lower1, upper1)
    m2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(m1, m2)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def black_mask(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower = np.array([0, 0, 0], dtype=np.uint8)
    upper = np.array([180, 120, 100], dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return mask


def dial_geometry(img_or_shape, dial):
    shape = getattr(img_or_shape, "shape", img_or_shape)
    h, w = shape[:2]
    cx = float(dial["x"]) * w
    cy = float(dial["y"]) * h
    radius = float(dial["r"]) * min(w, h)
    return cx, cy, radius


def crop_dial(mask, cx, cy, radius, crop_ratio=1.0):
    """Recorta la máscara al círculo del dial."""
    r = radius * float(crop_ratio)
    x0 = max(0, int(math.floor(cx - r)))
    y0 = max(0, int(math.floor(cy - r)))
    x1 = min(mask.shape[1], int(math.ceil(cx + r)) + 1)
    y1 = min(mask.shape[0], int(math.ceil(cy + r)) + 1)

    roi = mask[y0:y1, x0:x1].copy()

    local_cx = cx - x0
    local_cy = cy - y0

    yy, xx = np.ogrid[:roi.shape[0], :roi.shape[1]]
    circle = ((xx - local_cx) ** 2 + (yy - local_cy) ** 2 <= r * r)
    roi[~circle] = 0

    return roi, x0, y0


def find_needle_component(mask, cx, cy, radius, min_area=20):
    """
    Localiza el componente rojo/oscuro que contiene la aguja.

    En modo día, la aguja y su "culo" circular forman un único
    componente. Ese componente es precisamente lo que queremos.
    """
    roi, x0, y0 = crop_dial(mask, cx, cy, radius)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(roi, 8)
    candidates = []

    for label in range(1, n_labels):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            continue

        component = (labels == label).astype(np.uint8)

        # El centro del círculo del culo de la aguja es el punto
        # interior con mayor distancia al borde de su componente.
        dt = cv2.distanceTransform(component * 255, cv2.DIST_L2, 5)
        my, mx = np.unravel_index(int(np.argmax(dt)), dt.shape)
        base_x = float(x0 + mx)
        base_y = float(y0 + my)
        base_radius = float(dt[my, mx])

        ys, xs = np.where(component > 0)
        if len(xs) == 0:
            continue

        points_x = xs.astype(np.float64) + x0
        points_y = ys.astype(np.float64) + y0
        distances = np.hypot(points_x - base_x, points_y - base_y)
        tip_idx = int(np.argmax(distances))

        tip_x = float(points_x[tip_idx])
        tip_y = float(points_y[tip_idx])
        tip_distance = float(distances[tip_idx])

        # Distancia del centro detectado del culo al centro geométrico
        # calibrado del dial. No decide por sí sola, sólo ayuda a
        # distinguir artefactos muy alejados.
        center_distance = math.hypot(base_x - cx, base_y - cy)

        candidates.append(
            {
                "label": label,
                "area": area,
                "base": (base_x, base_y),
                "tip": (tip_x, tip_y),
                "base_radius": base_radius,
                "tip_distance": tip_distance,
                "center_distance": center_distance,
            }
        )

    if not candidates:
        return None

    # En el modo día, el conjunto formado por círculo + aguja suele
    # ser el componente rojo de mayor área. Priorizamos área, pero
    # exigimos que tenga una región realmente gruesa y una extensión
    # suficiente desde el centro de esa región.
    candidates.sort(
        key=lambda c: (
            c["area"],
            c["tip_distance"],
            c["base_radius"],
        ),
        reverse=True,
    )

    return candidates[0]


def component_angle(component):
    base_x, base_y = component["base"]
    tip_x, tip_y = component["tip"]

    dx = tip_x - base_x
    dy = tip_y - base_y

    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0

    # 0° arriba; 90° derecha; 180° abajo; 270° izquierda.
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0
    return float(angle)


def angle_to_position(angle, zero_angle):
    """
    Posición continua de la aguja en la esfera: 0.0 <= p < 10.0.

    Sentido horario y 36° por dígito, fijos para todas las esferas.
    """
    delta = (float(angle) - float(zero_angle)) % 360.0
    return (delta / DIAL_STEP_DEG) % 10.0


def analyse_dial(mask, shape, dial, mode):
    """Localiza la aguja de una esfera en `mask` y devuelve su posición."""
    cx, cy, radius = dial_geometry(shape, dial)
    component = find_needle_component(mask, cx, cy, radius)

    result = {
        "name": dial.get("name", "dial"),
        "digit": -1,
        "position": None,
        "angle": 0.0,
        "score": 0.0,
        "mode": mode,
        "base": None,
        "tip": None,
        "base_radius": 0.0,
        "tip_distance": 0.0,
    }
    if component is None:
        return result

    angle = component_angle(component)
    position = angle_to_position(angle, float(dial["zero_angle"]))

    # Confianza simple: qué tanto sobresale la punta respecto al tamaño
    # de la zona circular del "culo".
    score = min(1.0, component["tip_distance"] / max(1.0, radius * 0.60))

    result.update(
        {
            "position": float(round(position, 4)),
            "angle": float(round(angle, 2)),
            "score": float(round(score, 4)),
            "base": [
                int(round(component["base"][0])),
                int(round(component["base"][1])),
            ],
            "tip": [
                int(round(component["tip"][0])),
                int(round(component["tip"][1])),
            ],
            "base_radius": float(round(component["base_radius"], 2)),
            "tip_distance": float(round(component["tip_distance"], 2)),
        }
    )
    return result
