"""Construcción del payload y publicación MQTT."""

import json

import numpy as np

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


def json_default(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def build_payload(reading):
    """
    Payload MQTT. `decimal` (4 dígitos de las esferas), `integer` (parte
    entera, null si aún no está sembrada) y `reading` (m³ totales, null si
    falta algo) — pensado para un sensor total_increasing de Home Assistant.
    """
    return {
        "reading": reading["reading"],
        "integer": reading["integer"],
        "decimal": reading["decimal"],
        "integer_source": reading["integer_source"],
        "ocr_mismatch": reading["ocr_mismatch"],
        "held": reading.get("held", False),
        "mode": reading["mode"],
        "dials": reading["dials"],
        "timestamp": reading["timestamp"],
    }


def payload_to_json(payload):
    return json.dumps(payload, ensure_ascii=False, default=json_default)


def availability_topic(mqtt_cfg):
    return mqtt_cfg.get("topic", "watermeter/state").rsplit("/", 1)[0] + "/availability"


def discovery_messages(mqtt_cfg):
    """
    Mensajes de MQTT Discovery de Home Assistant: [(topic, payload_json)].
    Crean un dispositivo con el contador (m³, total_increasing, apto para el
    panel de Energía), el modo día/noche y el aviso de discrepancia del OCR.
    """
    state_topic = mqtt_cfg.get("topic", "watermeter/state")
    prefix = mqtt_cfg.get("discovery_prefix", "homeassistant")
    device = {
        "identifiers": ["watermeter"],
        "name": "Contador de agua",
        "manufacturer": "watermeter",
        "model": "Lector OpenCV",
    }
    common = {
        "state_topic": state_topic,
        "availability_topic": availability_topic(mqtt_cfg),
        "device": device,
    }
    # `reading` es null hasta sembrar la parte entera: 'unknown' lo deja
    # como estado desconocido en vez de provocar un error de conversión.
    reading_tpl = ("{{ value_json.reading if value_json.reading is not none "
                   "else 'unknown' }}")
    entities = [
        ("sensor", "reading", {
            "name": "Lectura",
            "unique_id": "watermeter_reading",
            "value_template": reading_tpl,
            "device_class": "water",
            "state_class": "total_increasing",
            "unit_of_measurement": "m³",
            "suggested_display_precision": 3,
        }),
        ("sensor", "mode", {
            "name": "Modo de imagen",
            "unique_id": "watermeter_mode",
            "value_template": "{{ value_json.mode }}",
            "icon": "mdi:theme-light-dark",
            "entity_category": "diagnostic",
        }),
        ("binary_sensor", "ocr_mismatch", {
            "name": "Discrepancia OCR",
            "unique_id": "watermeter_ocr_mismatch",
            "value_template": "{{ 'ON' if value_json.ocr_mismatch else 'OFF' }}",
            "device_class": "problem",
            "entity_category": "diagnostic",
        }),
    ]
    out = []
    for component, key, extra in entities:
        topic = f"{prefix}/{component}/watermeter/{key}/config"
        out.append((topic, json.dumps({**common, **extra}, ensure_ascii=False)))
    return out


def create_mqtt_client(mqtt_cfg):
    if mqtt is None:
        raise RuntimeError(
            "paho-mqtt no está instalado. Ejecuta: python3 -m pip install paho-mqtt"
        )

    # paho-mqtt >= 2.0 exige indicar la versión de la API de callbacks;
    # 1.x no tiene CallbackAPIVersion.
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    else:
        client = mqtt.Client()

    username = mqtt_cfg.get("username", "")
    if username:
        client.username_pw_set(username, mqtt_cfg.get("password", ""))
    return client
