"""
Ciclo día/noche.

De día la aguja es roja; de noche la cámara pasa a infrarrojo (imagen sin
color) y la aguja se ve oscura. Se decide con la fracción de píxeles rojos
dentro de los círculos de las esferas, medida sobre TODAS las esferas a la
vez (una sola aguja no puede cambiar el modo) y con histéresis para que el
atardecer/amanecer no haga oscilar el modo.

  ratio >= day_ratio    -> día
  ratio <  night_ratio  -> noche
  entre ambos           -> se mantiene el modo anterior
"""

import numpy as np

from .vision import crop_dial, dial_geometry

DEFAULT_DAY_RATIO = 0.05
DEFAULT_NIGHT_RATIO = 0.02


def dials_red_ratio(red_mask_img, dials):
    """Fracción de píxeles rojos dentro de los círculos de todas las esferas."""
    ones = np.full(red_mask_img.shape[:2], 255, dtype=np.uint8)
    red_pixels = 0
    area = 0
    for dial in dials:
        cx, cy, radius = dial_geometry(red_mask_img.shape, dial)
        roi, _, _ = crop_dial(red_mask_img, cx, cy, radius)
        circle, _, _ = crop_dial(ones, cx, cy, radius)
        red_pixels += int(np.count_nonzero(roi))
        area += int(np.count_nonzero(circle))
    return red_pixels / area if area else 0.0


class DayNightDetector:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.forced = str(cfg.get("mode", "auto")).lower()
        self.day_ratio = float(cfg.get("day_ratio", DEFAULT_DAY_RATIO))
        self.night_ratio = float(cfg.get("night_ratio", DEFAULT_NIGHT_RATIO))
        if self.night_ratio > self.day_ratio:
            raise ValueError("day_night.night_ratio no puede ser mayor que day_ratio")
        self.mode = "day"

    def decide(self, ratio, current=None):
        """Modo resultante sin modificar el estado."""
        if self.forced in ("day", "night"):
            return self.forced
        current = current or self.mode
        if ratio >= self.day_ratio:
            return "day"
        if ratio < self.night_ratio:
            return "night"
        return current

    def update(self, ratio):
        self.mode = self.decide(ratio)
        return self.mode
