"""Captura de fotogramas: imagen estática o stream RTSP (Frigate/go2rtc)."""

import cv2


def get_frame_from_image(path):
    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"No se pudo leer la imagen: {path}")
    return frame


TIMEOUT_MS = 10000  # apertura y lectura: un stream colgado no bloquea el bucle


def open_camera(url):
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, TIMEOUT_MS,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC, TIMEOUT_MS,
        ])
    except Exception:  # OpenCV sin esos parámetros
        cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        raise RuntimeError("No se puede abrir el stream de cámara")
    return cap


def get_frame_from_camera(cap):
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError("No se pudo capturar una imagen de la cámara")
    return frame


def capture_frame(url, discard=2):
    """
    Conecta al stream, devuelve un fotograma actual y se desconecta. Una
    conexión nueva evita el búfer atrasado de un stream abierto de forma
    permanente; se descartan los primeros fotogramas (arranque del decodificador).
    """
    cap = open_camera(url)
    try:
        frame = None
        for _ in range(max(0, int(discard)) + 1):
            frame = get_frame_from_camera(cap)
        return frame
    finally:
        cap.release()
