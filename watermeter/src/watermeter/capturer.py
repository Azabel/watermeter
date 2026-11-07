"""
Lectura bajo demanda: conecta a la cámara, lee, publica y desconecta. La
disparan el botón de Home Assistant (MQTT) y el botón "Leer ahora" de la web;
no hay lectura periódica (la luz del contador la enciende una automatización).
"""

import threading
import time

from .camera import capture_frame
from .debug import save_debug
from .log import log
from .publisher import build_payload, payload_to_json


def summary(reading):
    total = reading["reading"]
    value = "desconocida" if total is None else f"{total:.4f} m3"
    warn = " [OCR no coincide]" if reading["ocr_mismatch"] else ""
    if reading.get("held"):
        warn += " [retenida: la lectura no puede bajar]"
    return (f"Lectura: {value} (decimal {reading['decimal']}, "
            f"entero {reading['integer_source'] or 'sin sembrar'}, "
            f"modo {reading['mode']}){warn}")


class Capturer:
    def __init__(self, reader, cfg, debug_dir):
        camera_cfg = cfg["camera"]
        self.reader = reader
        self.url = camera_cfg["url"]
        # Espera tras la petición, p. ej. a que la cámara ajuste la exposición
        # cuando se enciende la luz.
        self.delay = float(camera_cfg.get("capture_delay", 0))
        self.debug_dir = debug_dir
        self.mqtt_client = None
        self.topic = cfg.get("mqtt", {}).get("topic", "watermeter/state")
        self._lock = threading.Lock()  # una lectura a la vez

    def read_now(self):
        with self._lock:
            log("Lectura solicitada")
            if self.delay > 0:
                time.sleep(self.delay)
            frame = capture_frame(self.url)
            self.reader.set_frame(frame)
            reading = self.reader.process(frame)
            log(summary(reading))
            if self.mqtt_client is not None:
                self.mqtt_client.publish(
                    self.topic, payload_to_json(build_payload(reading)), retain=True
                )
            save_debug(frame, reading, self.reader.calibration, self.debug_dir)
            return reading
