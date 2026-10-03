"""
Modo add-on de Home Assistant: la configuración sale de las opciones de la
UI de add-ons (/data/options.json) en lugar de config.json, y las credenciales
MQTT se piden al Supervisor si el usuario no las indica a mano.
"""

import json
import os
import urllib.request

OPTIONS_FILE = "/data/options.json"
DATA_DIR = "/data"
SUPERVISOR_MQTT_URL = "http://supervisor/services/mqtt"
HTTP_PORT = 8099  # puerto de ingress (ingress_port en config.yaml)


def load_options(path=OPTIONS_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def supervisor_mqtt(token=None, url=SUPERVISOR_MQTT_URL, timeout=10):
    """Datos del broker MQTT que el Supervisor ofrece al add-on, o {}."""
    token = token or os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return {}
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp).get("data") or {}
    except Exception as exc:  # noqa: BLE001
        print(f"AVISO: no se pudo obtener el servicio MQTT del Supervisor: {exc}", flush=True)
        return {}
    return {
        "host": data.get("host"),
        "port": data.get("port"),
        "username": data.get("username"),
        "password": data.get("password"),
    }


def build_config(opts, mqtt_service=None):
    """Construye el dict de configuración de la app a partir de las opciones."""
    mqtt_cfg = {
        "topic": opts.get("mqtt_topic") or "watermeter/state",
        "discovery": bool(opts.get("mqtt_discovery", True)),
        "discovery_prefix": opts.get("mqtt_discovery_prefix") or "homeassistant",
    }
    manual = {
        "host": opts.get("mqtt_host"),
        "port": opts.get("mqtt_port"),
        "username": opts.get("mqtt_username"),
        "password": opts.get("mqtt_password"),
    }
    if manual["host"]:
        source = manual
    else:
        source = mqtt_service if mqtt_service is not None else supervisor_mqtt()
    for key in ("host", "port", "username", "password"):
        value = source.get(key)
        if value not in (None, ""):
            mqtt_cfg[key] = value

    cfg = {
        "camera": {
            "url": opts["camera_url"],
            "interval": opts.get("interval", 10),
        },
        "mqtt": mqtt_cfg,
        "calibration_file": f"{DATA_DIR}/calibration.json",
        "state_file": f"{DATA_DIR}/state.json",
        "debug_dir": "/tmp/debug",
        "http": {"enabled": True, "host": "0.0.0.0", "port": HTTP_PORT},
        "day_night": {
            "mode": opts.get("day_night_mode", "auto"),
            "day_ratio": opts.get("day_ratio", 0.05),
            "night_ratio": opts.get("night_ratio", 0.02),
        },
        "odometer": {
            "ocr": bool(opts.get("ocr", True)),
            "auto_seed": bool(opts.get("auto_seed", False)),
            "ocr_trust_below": opts.get("ocr_trust_below", 0.8),
            "ocr_interval": opts.get("ocr_interval", 600),
        },
    }
    if opts.get("initial_integer") is not None:
        cfg["initial_integer"] = int(opts["initial_integer"])
    return cfg


def load_addon_config(path=OPTIONS_FILE, mqtt_service=None):
    return build_config(load_options(path), mqtt_service)
