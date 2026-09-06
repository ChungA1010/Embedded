// =====================================================
// Arduino UNO R4 WiFi
// 1) cmd/la 에서 ac 명령 polling -> 에어컨 IR ON/OFF
// 2) HC-SR04로 seatB 측정 -> 상태 변화 시 oneM2M 업로드
// =====================================================

// ── ArduinoJson 메모리 최적화 ─────────────────────────
#define ARDUINOJSON_SLOT_ID_SIZE       1
#define ARDUINOJSON_STRING_LENGTH_SIZE 1
#define ARDUINOJSON_USE_DOUBLE         0
#define ARDUINOJSON_USE_LONG_LONG      0

#include <WiFiS3.h>
#include <WiFiSSLClient.h>
#include <IRremote.hpp>
#include <ArduinoJson.h>
#include "secrets.h"

// =========================
// 핀 설정
// =========================
#define IR_SEND_PIN 3
#define TRIG_PIN 9
#define ECHO_PIN 8

// =========================
// oneM2M / 네트워크 설정
// =========================
const char* HOST = API_HOST;
const int PORT = HTTPS_PORT;

const char* ONEM2M_ORIGIN = ORIGIN;   // secrets.h의 ORIGIN 사용
const char* RVI = "2a";

const char* CSEBASE = "/Mobius";
const char* AE_RN   = "ae_table";
const char* SEAT_CNT = "seatB";

// cmd latest 경로 - 실제 경로로 수정
const char* CMD_LA_PATH = "/Mobius/ae_table/cmd/la";

// =========================
// 타이밍 설정
// =========================
const unsigned long WIFI_WAIT_MS  = 30000;
const unsigned long HTTP_WAIT_MS  = 10000;
const unsigned long CMD_POLL_INTERVAL_MS = 5000;
const unsigned long SEAT_CHECK_INTERVAL_MS = 3000;

// =========================
// 초음파 착석 판정 설정
// =========================
const int OCCUPIED_DISTANCE_CM = 30;
const int DISTANCE_SAMPLES = 5;

// =========================
// 상태 변수
// =========================
bool networkReady = false;
bool airconOn = false;

bool prevOccupied = false;
bool firstSeatUpload = true;

String lastProcessedRI = "";
uint32_t reqSeq = 1;

unsigned long lastCmdPollMillis = 0;
unsigned long lastSeatCheckMillis = 0;

// =========================
// 클라이언트
// =========================
WiFiSSLClient wifi;

// =========================
// IR RAW 데이터
// =========================
uint16_t powerOnRaw[] = {
  600, 12750, 3000, 8950, 500, 500,
  500, 1500, 500, 500, 500, 500,
  500, 450, 500, 500, 550, 450,
  550, 450, 500, 500, 500, 1500,
  500, 450, 550, 450, 550, 1450,
  550, 450, 500, 500, 500, 1500,
  500, 1500, 500, 1450, 550, 1450,
  550, 1450, 500, 500, 500, 500,
  500, 450, 550, 450, 550, 450,
  550, 450, 550, 450, 500, 500,
  500, 500, 450, 550, 450, 550,
  500, 500, 500, 500, 500, 500,
  500, 450, 550, 450, 550, 450,
  550, 450, 500, 500, 500, 500,
  500, 500, 500, 450, 550, 450,
  550, 450, 550, 450, 550, 450,
  500, 500, 450, 550, 450, 550,
  500, 500, 500, 500, 500, 500,
  500, 1450, 550, 1450, 550, 1450,
  500, 1500, 500, 2950, 3000, 8950,
  500, 1450, 500, 500, 500, 550,
  500, 450, 450, 550, 500, 500,
  500, 500, 500, 500, 500, 500,
  500, 1500, 500, 450, 550, 450,
  550, 1450, 500, 500, 500, 1500,
  500, 1450, 550, 1450, 500, 1500,
  450, 1550, 450, 1550, 500, 500,
  500, 450, 550, 450, 550, 450,
  550, 450, 550, 450, 500, 500,
  500, 500, 500, 450, 550, 450,

  550, 450, 550, 450, 550, 450,
  500, 500, 500, 500, 450, 550,
  450, 550, 500, 500, 500, 500,
  500, 450, 550, 450, 550, 450,
  550, 450, 550, 450, 500, 500,
  550, 450, 500, 450, 600, 400,
  600, 400, 550, 450, 550, 450,
  550, 450, 500, 500, 450, 550,
  450, 550, 450, 550, 500, 2950,
  3000, 8900, 550, 1500, 500, 450,
  550, 450, 550, 450, 550, 450,
  500, 500, 500, 500, 500, 500,
  500, 450, 500, 1550, 500, 500,
  450, 500, 500, 1500, 500, 500,
  500, 1500, 500, 1450, 500, 500,
  500, 1500, 500, 1500, 500, 1450,
  500, 1500, 500, 1500, 500, 1500,
  500, 1500, 500, 1500, 450, 550,
  450, 500, 500, 500, 500, 1500,
  500, 1500, 500, 1450, 500, 500,
  500, 500, 500, 500, 500, 500,
  500, 500, 500, 550, 400, 550,
  450, 550, 500, 1500, 450, 1500,
  500, 550, 450, 1500, 500, 500,
  450, 1500, 500, 550, 450, 550,
  450, 500, 500, 500, 500, 500,
  500, 500, 450, 500, 500, 1550,
  450, 1500, 500, 1500, 500, 1500,
  500
};
const uint16_t powerOnLen = sizeof(powerOnRaw) / sizeof(powerOnRaw[0]);

// 실제 OFF 신호로 교체
uint16_t powerOffRaw[] = {
  600, 12750, 3000, 8950, 500, 500
};
const uint16_t powerOffLen = sizeof(powerOffRaw) / sizeof(powerOffRaw[0]);

// =====================================================
// 함수 선언
// =====================================================
bool ensureWifiConnected(unsigned long maxWaitMs);
void ensureWiFiConnectedLoop();

String nextRI();
int readHttpStatusLine();

String getHttpBody(const String& response);
String extractJsonValue(const String& src, const String& key);
String extractRI(const String& body);
String extractAC(const String& body);

bool fetchLatestCommand(String& outRi, String& outAc, String& rawBody);

int post(String path, int ty, String body);
String serializeCIN(String content);
int postCIN(String path, String content);

int readDistanceRaw();
int readDistanceAveraged();
void uploadSeatB(int distance, bool occupied);
void seatTask();

void sendRawRepeated(const uint16_t* rawData, uint16_t rawLen, int repeatCount = 3);
void sendAirconOn();
void sendAirconOff();
void processACCommand(const String& acValue);
void pollLatestCommand();

// =====================================================
// setup()
// =====================================================
void setup() {
  Serial.begin(115200);
  while (!Serial);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);

  IrSender.begin(IR_SEND_PIN);

  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("[FATAL] WiFi module not found.");
    while (true) delay(1000);
  }

  Serial.println("[SETUP] Connecting WiFi...");
  if (!ensureWifiConnected(WIFI_WAIT_MS)) {
    Serial.println("[FATAL] WiFi connection failed.");
    while (true) delay(1000);
  }

  delay(2000);
  networkReady = true;

  Serial.println("[SETUP] System ready.");
}

// =====================================================
// loop()
// =====================================================
void loop() {
  ensureWiFiConnectedLoop();
  if (!networkReady) {
    delay(1000);
    return;
  }

  unsigned long now = millis();

  if (now - lastCmdPollMillis >= CMD_POLL_INTERVAL_MS) {
    lastCmdPollMillis = now;
    pollLatestCommand();
  }

  if (now - lastSeatCheckMillis >= SEAT_CHECK_INTERVAL_MS) {
    lastSeatCheckMillis = now;
    seatTask();
  }
}

// =====================================================
// WiFi
// =====================================================
bool ensureWifiConnected(unsigned long maxWaitMs) {
  if (WiFi.status() == WL_CONNECTED) return true;

  Serial.print("[WiFi] Connecting to SSID: ");
  Serial.println(SECRET_SSID);

  WiFi.begin(SECRET_SSID, SECRET_PASS);

  unsigned long start = millis();
  while (millis() - start < maxWaitMs) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println();
      Serial.println("[WiFi] Connected.");
      Serial.print("IP Address: ");
      Serial.println(WiFi.localIP());
      return true;
    }
    Serial.print(".");
    delay(250);
  }

  Serial.println();
  return false;
}

void ensureWiFiConnectedLoop() {
  if (WiFi.status() != WL_CONNECTED) {
    networkReady = false;
    Serial.println("[WiFi] Disconnected. Reconnecting...");

    if (ensureWifiConnected(WIFI_WAIT_MS)) {
      networkReady = true;
      Serial.println("[WiFi] Reconnected.");
      delay(1000);
    } else {
      Serial.println("[WiFi] Reconnect failed.");
    }
  }
}

// =====================================================
// 공통 유틸
// =====================================================
String nextRI() {
  String ri = "r-";
  ri += String(reqSeq++);
  return ri;
}

int readHttpStatusLine() {
  String line = wifi.readStringUntil('\n');
  line.trim();

  if (!line.startsWith("HTTP/")) return -1;

  int sp1 = line.indexOf(' ');
  if (sp1 < 0) return -1;

  int sp2 = line.indexOf(' ', sp1 + 1);
  if (sp2 < 0) sp2 = line.length();

  String codeStr = line.substring(sp1 + 1, sp2);
  return codeStr.toInt();
}

String getHttpBody(const String& response) {
  int bodyStart = response.indexOf("\r\n\r\n");
  if (bodyStart < 0) return "";
  return response.substring(bodyStart + 4);
}

String extractJsonValue(const String& src, const String& key) {
  String pattern = "\"" + key + "\"";
  int keyPos = src.indexOf(pattern);
  if (keyPos < 0) return "";

  int colonPos = src.indexOf(':', keyPos);
  if (colonPos < 0) return "";

  int firstQuote = src.indexOf('\"', colonPos + 1);
  if (firstQuote < 0) return "";

  int secondQuote = src.indexOf('\"', firstQuote + 1);
  if (secondQuote < 0) return "";

  return src.substring(firstQuote + 1, secondQuote);
}

String extractRI(const String& body) {
  return extractJsonValue(body, "ri");
}

String extractAC(const String& body) {
  return extractJsonValue(body, "ac");
}

// =====================================================
// cmd/la GET
// =====================================================
bool fetchLatestCommand(String& outRi, String& outAc, String& rawBody) {
  WiFiSSLClient client;

  Serial.println("[HTTPS] cmd/la 조회 시작");

  if (!client.connect(HOST, PORT)) {
    Serial.println("[HTTPS] 서버 연결 실패");
    return false;
  }

  client.print(String("GET ") + CMD_LA_PATH + " HTTP/1.1\r\n");
  client.print(String("Host: ") + HOST + "\r\n");
  client.print(String("X-M2M-Origin: ") + ONEM2M_ORIGIN + "\r\n");
  client.print(String("X-M2M-RI: ") + nextRI() + "\r\n");
  client.print(String("X-M2M-RVI: ") + RVI + "\r\n");
  client.print(String("X-API-KEY: ") + API_KEY + "\r\n");
  client.print(String("X-AUTH-CUSTOM-LECTURE: ") + LECTURE + "\r\n");
  client.print(String("X-AUTH-CUSTOM-CREATOR: ") + CREATOR + "\r\n");
  client.print("Accept: application/json\r\n");
  client.print("Connection: close\r\n\r\n");

  unsigned long timeout = millis();
  String response = "";

  while (client.connected() || client.available()) {
    if (client.available()) {
      char c = client.read();
      response += c;
      timeout = millis();
    } else {
      if (millis() - timeout > HTTP_WAIT_MS) {
        Serial.println("[HTTPS] 응답 타임아웃");
        client.stop();
        return false;
      }
    }
  }

  client.stop();

  rawBody = getHttpBody(response);
  if (rawBody.length() == 0) {
    Serial.println("[HTTPS] body 파싱 실패");
    return false;
  }

  Serial.println("[HTTPS] body 수신:");
  Serial.println(rawBody);

  outRi = extractRI(rawBody);
  outAc = extractAC(rawBody);
  return true;
}

void pollLatestCommand() {
  String ri, acValue, body;

  bool ok = fetchLatestCommand(ri, acValue, body);
  if (!ok) {
    Serial.println("[POLL] latest command 조회 실패");
    return;
  }

  Serial.print("[POLL] ri = ");
  Serial.println(ri);

  Serial.print("[POLL] ac = ");
  Serial.println(acValue);

  if (ri.length() == 0) {
    Serial.println("[POLL] ri를 찾지 못함");
    return;
  }

  if (ri == lastProcessedRI) {
    Serial.println("[POLL] 이미 처리한 latest instance. 재실행 안 함");
    return;
  }

  lastProcessedRI = ri;
  processACCommand(acValue);
}

// =====================================================
// AC 제어
// =====================================================
void sendRawRepeated(const uint16_t* rawData, uint16_t rawLen, int repeatCount) {
  for (int i = 0; i < repeatCount; i++) {
    IrSender.sendRaw(rawData, rawLen, 38);
    delay(100);
  }
}

void sendAirconOn() {
  Serial.println("[IR] 에어컨 ON 송신");
  sendRawRepeated(powerOnRaw, powerOnLen, 3);
}

void sendAirconOff() {
  Serial.println("[IR] 에어컨 OFF 송신");
  sendRawRepeated(powerOffRaw, powerOffLen, 3);
}

void processACCommand(const String& acValue) {
  if (acValue == "on") {
    if (!airconOn) {
      sendAirconOn();
      airconOn = true;
      Serial.println("[STATE] airconOn = true");
    } else {
      Serial.println("[SKIP] 이미 ON 상태로 추정됨");
    }
  } else if (acValue == "off") {
    if (airconOn) {
      sendAirconOff();
      airconOn = false;
      Serial.println("[STATE] airconOn = false");
    } else {
      Serial.println("[SKIP] 이미 OFF 상태로 추정됨");
    }
  } else {
    Serial.print("[WARN] 알 수 없는 ac 값: ");
    Serial.println(acValue);
  }
}

// =====================================================
// 초음파 측정
// =====================================================
int readDistanceRaw() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return -1;

  int distance = duration * 17 / 1000;
  return distance;
}

int readDistanceAveraged() {
  long sum = 0;
  int validCount = 0;

  for (int i = 0; i < DISTANCE_SAMPLES; i++) {
    int d = readDistanceRaw();

    if (d != -1 && d > 0 && d < 400) {
      sum += d;
      validCount++;
    }
    delay(60);
  }

  if (validCount == 0) return -1;
  return sum / validCount;
}

// =====================================================
// seatB 업로드
// =====================================================
String serializeCIN(String content) {
  StaticJsonDocument<256> doc;
  JsonObject m2m_cin = doc.createNestedObject("m2m:cin");
  m2m_cin["cnf"] = "application/json";
  m2m_cin["con"] = content;

  String out;
  serializeJson(doc, out);
  return out;
}

int post(String path, int ty, String body) {
  Serial.println("----------------------");

  if (!wifi.connect(HOST, PORT)) {
    Serial.println("[ERROR] TLS connect failed (POST)");
    wifi.stop();
    return -1;
  }

  String ri = nextRI();

  wifi.println("POST " + path + " HTTP/1.1");
  wifi.println("Host: " + String(HOST));
  wifi.println("X-M2M-Origin: " + String(ONEM2M_ORIGIN));
  wifi.println("X-M2M-RI: " + ri);
  wifi.println("X-M2M-RVI: " + String(RVI));
  wifi.println("X-API-KEY: " + String(API_KEY));
  wifi.println("X-AUTH-CUSTOM-LECTURE: " + String(LECTURE));
  wifi.println("X-AUTH-CUSTOM-CREATOR: " + String(CREATOR));
  wifi.println("Content-Type: application/json;ty=" + String(ty));
  wifi.println("Content-Length: " + String(body.length()));
  wifi.println("Connection: close");
  wifi.println();
  wifi.print(body);

  unsigned long t0 = millis();
  while (!wifi.available()) {
    if (millis() - t0 > HTTP_WAIT_MS) {
      Serial.println("[ERROR] Response timeout (POST)");
      wifi.stop();
      return -1;
    }
    delay(10);
  }

  int sc = readHttpStatusLine();
  wifi.stop();
  return sc;
}

int postCIN(String path, String content) {
  String body = serializeCIN(content);
  return post(path, 4, body);
}

void uploadSeatB(int distance, bool occupied) {
  StaticJsonDocument<128> seatDoc;
  seatDoc["distance"] = distance;
  seatDoc["occupied"] = occupied;

  String payload;
  serializeJson(seatDoc, payload);

  int sc = postCIN(
    String(CSEBASE) + "/" + AE_RN + "/" + SEAT_CNT,
    payload
  );

  Serial.print("[POST][seatB] status = ");
  Serial.println(sc);
}

void seatTask() {
  int distance = readDistanceAveraged();

  bool occupied = false;
  if (distance != -1) {
    occupied = (distance < OCCUPIED_DISTANCE_CM);
  }

  Serial.println("=================================");
  if (distance == -1) {
    Serial.println("DIST: invalid");
    Serial.println("SEAT B: unknown -> treated as EMPTY");
  } else {
    Serial.print("DIST: ");
    Serial.print(distance);
    Serial.println(" cm");

    Serial.print("SEAT B: ");
    Serial.println(occupied ? "OCCUPIED" : "EMPTY");
  }
  Serial.println("=================================");

  if (firstSeatUpload || occupied != prevOccupied) {
    Serial.println("[POST] Uploading seatB state...");
    uploadSeatB(distance, occupied);
    prevOccupied = occupied;
    firstSeatUpload = false;
  } else {
    Serial.println("[POST] seatB unchanged. Skip upload.");
  }
}
