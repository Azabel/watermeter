// Servidor MJPEG mínimo para GOOUUU ESP32-S3-CAM (N16R8, OV5640/OV2640)
// Dependencias: solo el core ESP32 de Arduino (WiFi.h y esp_camera.h).
// Ajustes del IDE: ESP32S3 Dev Module, PSRAM "OPI PSRAM", Flash 16MB.
// Stream:  http://<IP>/stream

#include <WiFi.h>
#include "esp_camera.h"

// ---------------- Configuración manual ----------------
const char *WIFI_SSID = "TU_WIFI";
const char *WIFI_PASS = "TU_CLAVE";

// Resolución: FRAMESIZE_QVGA, _VGA, _SVGA, _XGA, _HD, _SXGA, _UXGA, _FHD...
const framesize_t FRAME_SIZE = FRAMESIZE_HD;
const int JPEG_QUALITY = 15;        // 4 (mejor) .. 63 (más compresión)
const int XCLK_HZ = 20000000;       // baja a 10000000 si aparece "FB-OVF"
// -------------------------------------------------------

WiFiServer server(80);

static bool initCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = 11;  c.pin_d1 = 9;   c.pin_d2 = 8;   c.pin_d3 = 10;
  c.pin_d4 = 12;  c.pin_d5 = 18;  c.pin_d6 = 17;  c.pin_d7 = 16;
  c.pin_xclk = 15;
  c.pin_pclk = 13;
  c.pin_vsync = 6;
  c.pin_href = 7;
  c.pin_sccb_sda = 4;
  c.pin_sccb_scl = 5;
  c.pin_pwdn = -1;
  c.pin_reset = -1;
  c.xclk_freq_hz = XCLK_HZ;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAME_SIZE;
  c.jpeg_quality = JPEG_QUALITY;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }
  return true;
}

static void streamTo(WiFiClient &client) {
  client.print("HTTP/1.1 200 OK\r\n"
               "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
               "Cache-Control: no-cache\r\n"
               "Connection: close\r\n\r\n");
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) break;
    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    size_t sent = client.write(fb->buf, fb->len);
    client.print("\r\n");
    size_t len = fb->len;
    esp_camera_fb_return(fb);
    if (sent != len) break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  if (!psramFound()) Serial.println("AVISO: PSRAM no detectada (PSRAM: OPI PSRAM en el IDE)");
  if (!initCamera()) return;

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("WiFi conectando");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nStream: http://%s/stream\n", WiFi.localIP().toString().c_str());
  server.begin();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
    delay(2000);
    return;
  }

  WiFiClient client = server.available();
  if (!client) return;
  client.setNoDelay(true);
  client.setTimeout(2000);

  String request = client.readStringUntil('\n');
  while (client.connected()) {               // descartar el resto de cabeceras
    String h = client.readStringUntil('\n');
    if (h.length() <= 1) break;
  }

  if (request.startsWith("GET /stream")) {
    streamTo(client);
  } else {
    client.print("HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\nUsa /stream");
  }
  client.stop();
}
