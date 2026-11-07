# Contador de agua (OpenCV)

Lee un contador de agua analógico (4 esferas + rodillos) desde un stream RTSP
y publica la lectura por MQTT. Crea solo los sensores en Home Assistant.

## Primeros pasos

1. Instala y configura **Mosquitto broker** y la integración MQTT.
2. En la pestaña **Configuración** del add-on indica al menos `camera_url`.
3. Inicia el add-on y ábrelo desde la barra lateral (**Contador de agua**).
4. Calibra las esferas y los rodillos en la web (ver README) y pulsa **Fijar**
   con la parte entera actual del contador (o rellena `initial_integer`).
5. **No hay lectura periódica**: el add-on espera a que pulses el botón
   **Leer ahora**, que aparece en el mismo dispositivo de HA (o en la web del
   add-on). Cada pulsación conecta a la cámara, lee, publica y desconecta.
6. Aparecerá el dispositivo **Contador de agua** con `sensor.contador_de_agua_lectura`
   (m³, `total_increasing`), listo para el panel de Energía.

## Opciones

| Opción | Descripción |
|---|---|
| `camera_url` | URL RTSP de la cámara |
| `capture_delay` | Segundos de espera tras pulsar «Leer ahora» antes de capturar |
| `initial_integer` | Parte entera inicial; sólo si aún no hay una guardada |
| `mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password` | Broker propio. Vacío = usa el broker de HA |
| `mqtt_topic` | Topic del JSON de estado |
| `mqtt_discovery`, `mqtt_discovery_prefix` | Creación automática de entidades |
| `day_night_mode`, `day_ratio`, `night_ratio` | Ciclo día/noche |
| `ocr`, `ocr_interval`, `ocr_trust_below`, `auto_seed` | Verificación OCR de los rodillos |

Los cambios en las opciones requieren reiniciar el add-on. La calibración y la
parte entera se guardan en `/data` y entran en las copias de seguridad de HA.

## Automatización con la luz del contador

El add-on no enciende la luz: lo hace tu automatización. Entidades del
dispositivo: `button.contador_de_agua_leer_ahora` (dispara la lectura) y
`sensor.contador_de_agua_ultima_lectura` (cambia en cada lectura, aunque el
valor sea el mismo). Ejemplo:

```yaml
alias: Leer contador de agua
triggers:
  - trigger: time_pattern
    minutes: "/15"
actions:
  - action: switch.turn_on
    target: { entity_id: switch.luz_contador }
  - delay: "00:00:05"            # que la cámara se adapte a la luz
  - action: button.press
    target: { entity_id: button.contador_de_agua_leer_ahora }
  - wait_for_trigger:
      - trigger: state
        entity_id: sensor.contador_de_agua_ultima_lectura
    timeout: "00:00:30"
    continue_on_timeout: true
  - action: switch.turn_off
    target: { entity_id: switch.luz_contador }
```

Los nombres exactos de las entidades pueden variar; compruébalos en el
dispositivo. Si prefieres no usar el `delay`, la opción `capture_delay` hace la
espera dentro del add-on.

## La lectura nunca baja

La lectura publicada es siempre ≥ la máxima ya publicada (se guarda en
`/data/state.json`). Si una lectura es menor, se retiene la máxima y el log lo
indica (`[retenida…]`). Un salto hacia arriba de más de 0,1 m³ sólo se acepta
si dos ciclos seguidos coinciden, para que un pico erróneo no quede fijado.

La única forma de bajarla es el botón **Fijar** de la web: escribe el valor
correcto de la parte entera y pulsa Fijar; eso reinicia la lectura máxima.

## Limitación

Si el contador avanza 0,5 m³ o más mientras el add-on está parado, la parte
entera se pierde: revisa `integer_source` / `ocr_mismatch` al arrancar.
