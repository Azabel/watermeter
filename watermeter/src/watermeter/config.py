"""Carga de configuración y calibración."""

import json
import math
import os

DEFAULT_CONFIG_FILE = "config/config.json"
DEFAULT_CALIBRATION_FILE = "calibration.json"
DEFAULT_STATE_FILE = "state.json"
DEFAULT_DEBUG_DIR = "./debug"

DEFAULT_HTTP = {"enabled": True, "host": "0.0.0.0", "port": 8080}

# Variables de entorno que sobrescriben el bloque "mqtt" de config.json.
# Permiten no guardar credenciales en el fichero.
_MQTT_ENV = {
    "WATERMETER_MQTT_HOST": "host",
    "WATERMETER_MQTT_PORT": "port",
    "WATERMETER_MQTT_TOPIC": "topic",
    "WATERMETER_MQTT_USERNAME": "username",
    "WATERMETER_MQTT_PASSWORD": "password",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config(path):
    """Carga config.json y aplica las sobrescrituras por variable de entorno."""
    cfg = load_json(path)
    mqtt_cfg = cfg.setdefault("mqtt", {})
    for env_name, key in _MQTT_ENV.items():
        value = os.environ.get(env_name)
        if value:
            mqtt_cfg[key] = value
    http_cfg = dict(DEFAULT_HTTP)
    http_cfg.update(cfg.get("http", {}))
    cfg["http"] = http_cfg
    return cfg


def _beside_config(cfg_path, filename):
    if os.path.isabs(filename):
        return filename
    return os.path.join(os.path.dirname(os.path.abspath(cfg_path)), filename)


def calibration_path(cfg, config_path, override=None):
    """Ruta de la calibración (relativa al directorio del config.json)."""
    if override:
        return override
    return _beside_config(config_path, cfg.get("calibration_file", DEFAULT_CALIBRATION_FILE))


def state_path(cfg, config_path):
    return _beside_config(config_path, cfg.get("state_file", DEFAULT_STATE_FILE))


def load_calibration(path):
    if not os.path.exists(path):
        # Primera ejecución: sin calibrar; se hace desde la web.
        return {"dials": []}
    return validate_calibration(load_json(path))


# --------------------------------------------------------------------------
# Validación / guardado
# --------------------------------------------------------------------------

def _num(value, name, lo=None, hi=None):
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: no es un número")
    if not math.isfinite(x):
        raise ValueError(f"{name}: no es finito")
    if lo is not None and x < lo:
        raise ValueError(f"{name}: debe ser >= {lo}")
    if hi is not None and x > hi:
        raise ValueError(f"{name}: debe ser <= {hi}")
    return x


def validate_calibration(cal):
    """
    Devuelve una calibración limpia (sólo claves conocidas) o lanza
    ValueError. Las esferas van ordenadas de la más gruesa (×0.1) a la
    más fina. Claves antiguas (step_angle, tip_*_ratio) se descartan: el
    paso es fijo, 36° en sentido horario.
    """
    if not isinstance(cal, dict):
        raise ValueError("La calibración debe ser un objeto JSON")
    dials_in = cal.get("dials")
    if not isinstance(dials_in, list) or len(dials_in) > 8:
        raise ValueError("dials debe ser una lista (máx. 8 esferas)")

    dials = []
    for i, d in enumerate(dials_in):
        if not isinstance(d, dict):
            raise ValueError(f"dials[{i}] no es un objeto")
        dials.append(
            {
                "name": str(d.get("name", f"dial{i + 1}")),
                "x": _num(d.get("x"), f"dials[{i}].x", 0, 1),
                "y": _num(d.get("y"), f"dials[{i}].y", 0, 1),
                "r": _num(d.get("r"), f"dials[{i}].r", 0.001, 0.5),
                "zero_angle": _num(d.get("zero_angle"), f"dials[{i}].zero_angle") % 360.0,
            }
        )

    out = {"dials": dials}
    for key in ("image_width", "image_height"):
        if cal.get(key) is not None:
            out[key] = int(_num(cal[key], key, 1))

    odo = cal.get("odometer")
    if odo:
        n = int(_num(odo.get("digits"), "odometer.digits", 2, 12))
        out["odometer"] = {
            "digits": n,
            "x1": _num(odo.get("x1"), "odometer.x1", 0, 1),
            "y1": _num(odo.get("y1"), "odometer.y1", 0, 1),
            "x2": _num(odo.get("x2"), "odometer.x2", 0, 1),
            "y2": _num(odo.get("y2"), "odometer.y2", 0, 1),
            "hw": _num(odo.get("hw"), "odometer.hw", 0.001, 0.5),
        }
        o = out["odometer"]
        if math.hypot(o["x2"] - o["x1"], o["y2"] - o["y1"]) < 1e-4:
            raise ValueError("odometer: el primer y el último rodillo coinciden")
    return out


def save_calibration(path, cal):
    """Valida y escribe la calibración de forma atómica."""
    clean = validate_calibration(cal)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return clean
