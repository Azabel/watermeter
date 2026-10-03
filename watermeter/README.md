# watermeter

Lee un contador de agua analógico (4 esferas decimales + rodillos numéricos)
con OpenCV a partir de un stream RTSP (Frigate / go2rtc), publica la lectura
por MQTT y trae una interfaz web integrada para calibrar desde el navegador.

## Estructura

```
watermeter/
├── config/
│   ├── config.example.json   # plantilla sin credenciales (se versiona)
│   ├── config.json           # tu config real (ignorado por git)
│   ├── calibration.json      # esferas y rodillos (lo escribe la web)
│   └── state.json            # parte entera y última fracción (se crea solo)
├── src/watermeter/
│   ├── cli.py                # modos de ejecución
│   ├── config.py             # carga/validación/guardado de config y calibración
│   ├── camera.py             # RTSP o imagen estática
│   ├── vision.py             # máscaras, aguja, ángulo -> posición 0-10
│   ├── daynight.py           # ciclo día/noche con histéresis
│   ├── reading.py            # cascada de esferas + seguimiento del entero
│   ├── odometer.py           # rodillos: enderezado de la tira + OCR
│   ├── reader.py             # orquesta un fotograma; estado compartido
│   ├── server.py             # servidor HTTP integrado (stdlib)
│   ├── web/index.html        # interfaz de calibración
│   ├── publisher.py          # payload y cliente MQTT
│   └── debug.py              # debug/latest.jpg y salida por consola
└── tests/
```

## Instalación

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
sudo apt install tesseract-ocr && pip install pytesseract   # OCR de rodillos (opcional)
cp config/config.example.json config/config.json            # y edita URL / host MQTT
export WATERMETER_MQTT_PASSWORD='...'                       # la contraseña no va en el fichero
```

## Add-on de Home Assistant (HA OS / Supervised)

Este directorio es también un add-on (`config.yaml`, `Dockerfile`, `run.sh`).
Las opciones se editan en la UI de add-ons de HA (ver `DOCS.md`), la web de
calibración se abre por ingress desde la barra lateral y las entidades se crean
solas por MQTT Discovery. `repository.yaml` (un nivel por encima) permite
añadir el repositorio completo en la tienda de add-ons. Modo add-on a mano:
`python -m watermeter --addon` (lee `/data/options.json`).

## Uso

```bash
watermeter                       # modo continuo: lee, publica en MQTT y sirve la web
watermeter --no-mqtt             # igual, sin publicar (para calibrar)
watermeter --image foto.jpg      # analiza una imagen y sale
watermeter --image foto.jpg --serve   # ídem y deja la web abierta sobre esa imagen
watermeter --debug               # una captura de la cámara, sin MQTT
watermeter --set-integer 17      # fija la parte entera (m³) y sale
```

Sin instalar: `PYTHONPATH=src python3 -m watermeter ...`

## Calibración (web)

Abre `http://<host>:8080/` (configurable en `http` de `config.json`).

1. Elige una esfera y haz clic: **centro → borde → el 0 impreso**. Repite en las 4,
   de la ×0.1 a la más fina (el orden importa).
2. Rodillos: **centro del primero → centro del último → borde de una caja**, e
   indica cuántos rodillos hay. El orden de lectura es primero → último, sea cual
   sea el ángulo de la cámara.
3. Arrastra cualquier punto para afinar. Las 10 marcas de cada esfera se dibujan
   cada 36° en sentido horario: deben caer sobre los números impresos.
4. La vista previa se actualiza sola (agujas detectadas, dígitos, tira de
   rodillos). **Guardar** escribe `calibration.json` y se aplica en caliente,
   sin reiniciar.
5. Escribe la parte entera actual (léela en los rodillos) y pulsa **Fijar**.

El servidor no tiene autenticación: usa `http.host: "127.0.0.1"` si no quieres
exponerlo en la red, o `http.enabled: false` para desactivarlo.

## Cómo se lee

**Esferas.** Cada aguja da una posición continua 0–10 (36° por dígito, sentido
horario, fijos). El dígito de cada esfera se corrige con la posición de la más
fina que la sigue: si la fina acaba de pasar por 0, la gruesa ya pasó su marca
aunque la aguja parezca quedarse un poco antes.

**Día/noche.** De día la aguja es roja; de noche la cámara pasa a IR y se busca
la aguja oscura. Se mide la fracción de rojo dentro de las 4 esferas (global,
no por esfera) con histéresis: `>= day_ratio` → día, `< night_ratio` → noche,
entre ambos se mantiene el modo. `day_night.mode` puede forzar `"day"`/`"night"`.

**Parte entera.** El OCR de rodillos borrosos o a medio giro no es fiable, así
que el entero se **sigue**: cuando la fracción da la vuelta (0,99 → 0,01) sube 1
(y baja 1 si retrocede). Se siembra una vez (web o `--set-integer`) y se guarda
en `state.json` cada minuto y en cada cambio. El OCR, si está instalado, sólo
verifica: cada `odometer.ocr_interval` s, con la fracción `< ocr_trust_below`
(rodillo de unidades quieto), y acepta un dígito únicamente si todas las
variantes de preprocesado coinciden; si no, devuelve `?`. Si lee todos los
rodillos y discrepan del entero seguido, `ocr_mismatch` pasa a `true`.
`odometer.auto_seed: true` permite sembrar por OCR (no recomendado con imagen
borrosa).

## Payload MQTT

Topic `watermeter/state` (retain):

```json
{"reading": 17.878, "integer": 17, "decimal": "8780", "integer_source": "manual",
 "ocr_mismatch": false, "mode": "day", "dials": [...], "timestamp": 1789000000}
```

`reading` (m³ totales) y `integer` son `null` hasta sembrar el entero o si
alguna aguja no se detecta. Para Home Assistant, `value_template:
"{{ value_json.reading }}"`, `device_class: water`, `state_class: total_increasing`.

## Limitaciones conocidas

- **La parte entera se pierde si el contador avanza ≥ 0,5 m³ mientras la
  aplicación está parada** (la vuelta de la fracción no se observa). Al
  arrancar, revisa `integer_source` / `ocr_mismatch`.
- El camino de **noche** está probado con una imagen simulada (gris con la aguja
  oscurecida), no con una captura IR real. Si el umbral de `black_mask` no
  acierta con tu cámara, habrá que ajustarlo con una imagen nocturna real.
- Con el intervalo de 10 s, el búfer RTSP puede devolver un fotograma viejo;
  conviene descartar algunos con `cap.grab()` antes de `cap.read()`.
- Enfocar la cámara mejoraría mucho la lectura de los rodillos.

## Tests

```bash
pip install pytest && pytest
```
