"""Modo add-on: opciones de la UI -> configuración, y MQTT Discovery."""

import json

from watermeter.addon import build_config
from watermeter.publisher import availability_topic, discovery_messages

OPTS = {
    "camera_url": "rtsp://cam/stream",
    "interval": 15,
    "initial_integer": 22,
    "mqtt_host": "",
    "mqtt_topic": "watermeter/state",
    "mqtt_discovery": True,
    "mqtt_discovery_prefix": "homeassistant",
    "day_night_mode": "night",
    "day_ratio": 0.1,
    "night_ratio": 0.03,
    "ocr": False,
    "ocr_interval": 300,
    "ocr_trust_below": 0.5,
    "auto_seed": False,
}
SERVICE = {"host": "core-mosquitto", "port": 1883, "username": "u", "password": "p"}


def test_options_map_to_config():
    cfg = build_config(OPTS, SERVICE)
    assert cfg["camera"] == {"url": "rtsp://cam/stream", "interval": 15}
    assert cfg["day_night"] == {"mode": "night", "day_ratio": 0.1, "night_ratio": 0.03}
    assert cfg["odometer"]["ocr"] is False
    assert cfg["odometer"]["ocr_interval"] == 300
    assert cfg["initial_integer"] == 22
    assert cfg["calibration_file"] == "/data/calibration.json"
    assert cfg["http"]["port"] == 8099


def test_mqtt_from_supervisor_service():
    mqtt_cfg = build_config(OPTS, SERVICE)["mqtt"]
    assert (mqtt_cfg["host"], mqtt_cfg["username"], mqtt_cfg["password"]) == (
        "core-mosquitto", "u", "p")


def test_manual_mqtt_overrides_service():
    opts = dict(OPTS, mqtt_host="10.0.0.5", mqtt_port=1884, mqtt_username="x", mqtt_password="y")
    mqtt_cfg = build_config(opts, SERVICE)["mqtt"]
    assert (mqtt_cfg["host"], mqtt_cfg["port"], mqtt_cfg["username"]) == ("10.0.0.5", 1884, "x")


def test_no_initial_integer_when_unset():
    assert "initial_integer" not in build_config(dict(OPTS, initial_integer=None), SERVICE)


def test_discovery_messages():
    mqtt_cfg = build_config(OPTS, SERVICE)["mqtt"]
    msgs = dict(discovery_messages(mqtt_cfg))
    assert set(msgs) == {
        "homeassistant/sensor/watermeter/reading/config",
        "homeassistant/sensor/watermeter/mode/config",
        "homeassistant/binary_sensor/watermeter/ocr_mismatch/config",
    }
    reading = json.loads(msgs["homeassistant/sensor/watermeter/reading/config"])
    assert reading["state_topic"] == "watermeter/state"
    assert reading["availability_topic"] == availability_topic(mqtt_cfg) == "watermeter/availability"
    assert reading["state_class"] == "total_increasing"
    assert reading["device_class"] == "water"
