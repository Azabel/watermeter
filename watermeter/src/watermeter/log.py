"""Mensajes de log con fecha y hora (hora local; en el add-on, la zona de HA)."""

import time


def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)
