"""Captura de fotogramas: imagen estática o stream RTSP (Frigate/go2rtc)."""

import cv2


def get_frame_from_image(path):
    frame = cv2.imread(path)
    if frame is None:
        raise RuntimeError(f"No se pudo leer la imagen: {path}")
    return frame


def open_camera(url):
    cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    if not cap.isOpened():
        raise RuntimeError(f"No se puede abrir el stream de cámara: {url}")
    return cap


def get_frame_from_camera(cap):
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError("No se pudo capturar una imagen de la cámara")
    return frame
