"""Línea de comandos: imagen estática, captura única, o modo continuo + web."""

import argparse
import time

from .camera import get_frame_from_camera, get_frame_from_image, open_camera
from .config import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_DEBUG_DIR,
    calibration_path,
    load_calibration,
    load_config,
    state_path,
)
from .debug import print_results, save_debug
from .addon import load_addon_config
from .publisher import (
    availability_topic,
    build_payload,
    create_mqtt_client,
    discovery_messages,
    payload_to_json,
)
from .reader import Reader
from .server import WebServer


def _print_once(reader, frame, debug_dir):
    reading = reader.process(frame, commit=False)
    debug_path = save_debug(frame, reading, reader.calibration, debug_dir)
    print_results(reading, debug_path)


def _start_web(reader, cfg):
    http = cfg["http"]
    if not http.get("enabled", True):
        return None
    server = WebServer(reader, http["host"], http["port"]).start()
    print(f"Interfaz web: http://{http['host']}:{server.port}/", flush=True)
    return server


def _setup_discovery(client, mqtt_cfg):
    """Disponibilidad (LWT) y MQTT Discovery; se republica en cada reconexión."""
    avail = availability_topic(mqtt_cfg)
    client.will_set(avail, "offline", retain=True)

    def on_connect(cl, userdata, *args):  # firma distinta en paho 1.x y 2.x
        for topic, payload in discovery_messages(mqtt_cfg):
            cl.publish(topic, payload, retain=True)
        cl.publish(avail, "online", retain=True)

    client.on_connect = on_connect


def run_continuous(reader, cfg, debug_dir, use_mqtt=True):
    camera_cfg = cfg["camera"]
    interval = float(camera_cfg.get("interval", 10))
    mqtt_cfg = cfg.get("mqtt", {})
    mqtt_client = None
    cap = None
    web = _start_web(reader, cfg)

    try:
        if use_mqtt and mqtt_cfg.get("host"):
            mqtt_client = create_mqtt_client(mqtt_cfg)
            if mqtt_cfg.get("discovery"):
                _setup_discovery(mqtt_client, mqtt_cfg)
            mqtt_client.connect(mqtt_cfg["host"], int(mqtt_cfg.get("port", 1883)), 60)
            mqtt_client.loop_start()

        while True:
            try:
                if cap is None:
                    cap = open_camera(camera_cfg["url"])
                frame = get_frame_from_camera(cap)
                reader.set_frame(frame)

                reading = reader.process(frame)
                payload_json = payload_to_json(build_payload(reading))
                print(payload_json, flush=True)

                if mqtt_client is not None:
                    mqtt_client.publish(
                        mqtt_cfg.get("topic", "watermeter/state"),
                        payload_json,
                        retain=True,
                    )
                save_debug(frame, reading, reader.calibration, debug_dir)

            except Exception as exc:
                print(f"ERROR: {exc}", flush=True)
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None  # se reintenta en el siguiente ciclo

            time.sleep(interval)

    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        if web is not None:
            web.stop()
        if mqtt_client is not None:
            try:
                mqtt_client.loop_stop()
                mqtt_client.disconnect()
            except Exception:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lectura OpenCV de contador de agua")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE)
    parser.add_argument("--addon", action="store_true",
                        help="add-on de Home Assistant: configuración desde /data/options.json")
    parser.add_argument("--calibration", default=None,
                        help="fichero de calibración (por defecto el de config.json)")
    parser.add_argument("--image", default=None,
                        help="analizar una imagen estática, sin cámara ni MQTT")
    parser.add_argument("--serve", action="store_true",
                        help="con --image: dejar la web de calibración activa sobre esa imagen")
    parser.add_argument("--debug", action="store_true",
                        help="una sola captura de la cámara, sin MQTT")
    parser.add_argument("--no-mqtt", action="store_true",
                        help="modo continuo sin publicar en MQTT (p. ej. para calibrar)")
    parser.add_argument("--set-integer", type=int, default=None, metavar="N",
                        help="fija la parte entera del contador (m³) y sale")
    args = parser.parse_args(argv)

    cfg = load_addon_config() if args.addon else load_config(args.config)
    cal_path = calibration_path(cfg, args.config, args.calibration)
    calibration = load_calibration(cal_path)
    debug_dir = cfg.get("debug_dir", DEFAULT_DEBUG_DIR)
    reader = Reader(cfg, calibration, cal_path, state_path(cfg, args.config))

    # Opción "initial_integer" del add-on: sólo siembra si aún no hay entero,
    # para no pisar el seguimiento en cada reinicio.
    if cfg.get("initial_integer") is not None and reader.tracker.integer is None:
        reader.tracker.set_integer(cfg["initial_integer"])
        print(f"Parte entera inicial: {cfg['initial_integer']}", flush=True)

    if args.set_integer is not None:
        reader.tracker.set_integer(args.set_integer)
        print(f"Parte entera fijada a {args.set_integer} "
              f"(guardada en {reader.tracker.state_path})")
        return 0

    if args.image:
        print(f"Cargando imagen: {args.image}")
        frame = get_frame_from_image(args.image)
        reader.set_frame(frame)
        _print_once(reader, frame, debug_dir)
        if args.serve:
            web = _start_web(reader, cfg)
            if web is None:
                print("http.enabled=false en config.json: no hay servidor que mantener")
                return 1
            print("Ctrl+C para salir")
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                web.stop()
        return 0

    if args.debug:
        print("Capturando imagen de la cámara...")
        cap = open_camera(cfg["camera"]["url"])
        try:
            frame = get_frame_from_camera(cap)
        finally:
            cap.release()
        reader.set_frame(frame)
        _print_once(reader, frame, debug_dir)
        return 0

    try:
        run_continuous(reader, cfg, debug_dir, use_mqtt=not args.no_mqtt)
    except KeyboardInterrupt:
        pass
    return 0
