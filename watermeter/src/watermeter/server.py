"""
Servidor HTTP integrado (sólo librería estándar) para calibrar desde el
navegador. Se ejecuta en un hilo dentro de la propia aplicación y comparte
el estado (`Reader`) con el bucle de captura: al guardar la calibración se
aplica en caliente, sin reiniciar.

  GET  /                   interfaz de calibración
  GET  /api/frame.jpg      último fotograma capturado (sin dibujos)
  GET  /api/calibration    calibración activa
  POST /api/calibration    valida, guarda en disco y aplica
  POST /api/analyse        lee el último fotograma con una calibración SIN
                           guardar (vista previa); no altera el estado
  GET  /api/status         última lectura publicada
  POST /api/integer        fija la parte entera {"integer": 17}

Sin autenticación: pensado para la red local. Cambia http.host en
config.json a 127.0.0.1 si no quieres exponerlo.
"""

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from .publisher import json_default

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_BODY = 1024 * 1024


def _make_handler(reader):
    class Handler(BaseHTTPRequestHandler):
        server_version = "watermeter"

        def log_message(self, fmt, *args):  # silencio: el bucle ya imprime
            pass

        # -- utilidades ----------------------------------------------------
        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False, default=json_default).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def _error(self, code, message):
            self._json(code, {"error": message})

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            if length > MAX_BODY:
                raise ValueError("Cuerpo demasiado grande")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        # -- GET ---------------------------------------------------------------
        def do_GET(self):
            # lstrip: el proxy de ingress puede entregar "//api/..."
            path = "/" + self.path.split("?", 1)[0].lstrip("/")
            try:
                if path in ("/", "/index.html"):
                    with open(os.path.join(WEB_DIR, "index.html"), "rb") as f:
                        self._send(200, f.read(), "text/html; charset=utf-8")
                elif path == "/api/frame.jpg":
                    frame, ts = reader.get_frame()
                    if frame is None:
                        return self._error(503, "Aún no hay ningún fotograma de la cámara")
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    if not ok:
                        return self._error(500, "No se pudo codificar el fotograma")
                    self._send(200, buf.tobytes(), "image/jpeg",
                               {"X-Frame-Time": str(int(ts))})
                elif path == "/api/calibration":
                    self._json(200, reader.get_calibration())
                elif path == "/api/status":
                    self._json(200, {
                        "reading": reader.last_reading,
                        "integer": reader.tracker.integer,
                        "integer_source": reader.tracker.source,
                    })
                else:
                    self._error(404, "No encontrado")
            except Exception as exc:  # noqa: BLE001
                self._error(500, str(exc))

        # -- POST --------------------------------------------------------------
        def do_POST(self):
            path = "/" + self.path.split("?", 1)[0].lstrip("/")
            try:
                data = self._body()
                if path == "/api/calibration":
                    frame, _ = reader.get_frame()
                    shape = None if frame is None else frame.shape
                    clean = reader.update_calibration(data, shape)
                    self._json(200, {"saved": True, "calibration": clean})
                elif path == "/api/analyse":
                    frame, _ = reader.get_frame()
                    if frame is None:
                        return self._error(503, "Aún no hay ningún fotograma de la cámara")
                    reading = reader.process(
                        frame,
                        calibration=data.get("calibration"),
                        commit=False,
                        with_strip=True,
                    )
                    strip = reading.pop("_strip", None)
                    if strip is not None:
                        ok, buf = cv2.imencode(".png", strip)
                        if ok:
                            reading["strip_png"] = (
                                "data:image/png;base64,"
                                + base64.b64encode(buf.tobytes()).decode("ascii")
                            )
                    self._json(200, reading)
                elif path == "/api/integer":
                    value = data.get("integer")
                    if isinstance(value, bool) or not isinstance(value, int):
                        return self._error(400, "integer debe ser un entero")
                    reader.set_integer(value)
                    self._json(200, {"integer": reader.tracker.integer,
                                     "integer_source": reader.tracker.source})
                else:
                    self._error(404, "No encontrado")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                self._error(400, str(exc))
            except Exception as exc:  # noqa: BLE001
                self._error(500, str(exc))

    return Handler


class WebServer:
    def __init__(self, reader, host="0.0.0.0", port=8080):
        self.httpd = ThreadingHTTPServer((host, int(port)), _make_handler(reader))
        self.httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self.httpd.serve_forever, name="watermeter-http", daemon=True
        )

    @property
    def port(self):
        return self.httpd.server_address[1]

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
