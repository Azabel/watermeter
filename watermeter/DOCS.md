# Contador de agua (OpenCV)

Lee un contador de agua analógico (4 esferas + rodillos) desde un stream RTSP
y publica la lectura por MQTT. Crea solo los sensores en Home Assistant.

## Primeros pasos

1. Instala y configura **Mosquitto broker** y la integración MQTT.
2. En la pestaña **Configuración** del add-on indica al menos `camera_url`.
3. Inicia el add-on y ábrelo desde la barra lateral (**Contador de agua**).
4. Calibra las esferas y los rodillos en la web (ver README) y pulsa **Fijar**
   con la parte entera actual del contador (o rellena `initial_integer`).
5. Aparecerá el dispositivo **Contador de agua** con `sensor.contador_de_agua_lectura`
   (m³, `total_increasing`), listo para el panel de Energía.

## Opciones

| Opción | Descripción |
|---|---|
| `camera_url` | URL RTSP de la cámara |
| `interval` | Segundos entre lecturas |
| `initial_integer` | Parte entera inicial; sólo si aún no hay una guardada |
| `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password` | Broker propio. Vacío = usa el broker de HA |
| `mqtt_topic` | Topic del JSON de estado |
| `mqtt_discovery`, `mqtt_discovery_prefix` | Creación automática de entidades |
| `day_night_mode`, `day_ratio`, `night_ratio` | Ciclo día/noche |
| `ocr`, `ocr_interval`, `ocr_trust_below`, `auto_seed` | Verificación OCR de los rodillos |

Los cambios en las opciones requieren reiniciar el add-on. La calibración y la
parte entera se guardan en `/data` y entran en las copias de seguridad de HA.

## Limitación

Si el contador avanza 0,5 m³ o más mientras el add-on está parado, la parte
entera se pierde: revisa `integer_source` / `ocr_mismatch` al arrancar.
