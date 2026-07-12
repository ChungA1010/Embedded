// =====================================================
// oneM2M seatB 업로드 코드 - Arduino UNO R4 WiFi
// HC-SR04 초음파 센서로 착석 여부를 측정하고
// oneM2M 플랫폼의 seatB 컨테이너에 저장
// =====================================================

// ── ArduinoJson 메모리 최적화 설정 ─────────────────────
#define ARDUINOJSON_SLOT_ID_SIZE       1
#define ARDUINOJSON_STRING_LENGTH_SIZE 1
#define ARDUINOJSON_USE_DOUBLE         0
#define ARDUINOJSON_USE_LONG_LONG      0

// ── 라이브러리 포함 ──────────────────────────────────
#include <WiFiS3.h>
#include <WiFiSSLClient.h>
#include <ArduinoJson.h>

#include "secrets.h"   // SECRET_SSID, SECRET_PASS, API_KEY, LECTURE, CREATOR

// ── HC-SR04 센서 핀 설정 ──────────────────────────────
#define TRIG_PIN 9
#define ECHO_PIN 8

// ── 네트워크 / 타이밍 설정 ────────────────────────────
const unsigned long LOOP_DELAY_MS = 3000;   // 측정 주기
const unsigned long WIFI_WAIT_MS  = 30000;  // WiFi 연결 최대 대기
const unsigned long HTTP_WAIT_MS  = 10000;  // HTTP 응답 최대 대기
const int PORT = 443;
const char* HOST = "onem2m.iotcoss.ac.kr";

// ── oneM2M 설정 ──────────────────────────────────────
const char* ONEM2M_ORIGIN = "SOrigin_tableB"; // seatB 보드용으로 구분 권장
const char* RVI           = "2a";

const char* CSEBASE  = "/Mobius";
const char* AE_RN    = "ae_table";    // 기존 AE 이름과 동일하게 사용 가능
const char* SEAT_CNT = "seatB";       // seatB 컨테이너에 저장

// ── 착석 판정 설정 ───────────────────────────────────
const int OCCUPIED_DISTANCE_CM = 30;  // 30cm 이하면 착석
const int DISTANCE_SAMPLES = 5;       // 평균 측정 횟수

// ── 전역 변수 ─────────────────────────────────────────
bool networkReady = false;
bool prevOccupied = false;
bool firstSeatUpload = true;
uint32_t reqSeq = 1;

// ── 객체 생성 ─────────────────────────────────────────
WiFiSSLClient wifi;

// =====================================================
// 함수 선언
// =====================================================
bool ensureWifiConnected(unsigned long maxWaitMs);
String nextRI();
int readHttpStatusLine();
int post(String path, int ty, String body);
String serializeCIN(String content);
int postCIN(String path, String content);

int readDistanceRaw();
int readDistanceAveraged();
void uploadSeatB(int distance, bool occupied);

// =====================================================
// setup()
// =====================================================
void setup() {
    Serial.begin(115200);
    while (!Serial);

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    digitalWrite(TRIG_PIN, LOW);

    if (WiFi.status() == WL_NO_MODULE) {
        Serial.println("[FATAL] WiFi module not found.");
        while (true) delay(1000);
    }

    Serial.println("[SETUP] Connecting WiFi...");
    if (!ensureWifiConnected(WIFI_WAIT_MS)) {
        Serial.println("[FATAL] WiFi connection failed.");
        while (true) delay(1000);
    }

    delay(3000);
    networkReady = true;

    Serial.println("[SETUP] seatB uploader ready.");
}

// =====================================================
// loop()
// =====================================================
void loop() {
    // 1. WiFi 연결 확인
    if (WiFi.status() != WL_CONNECTED) {
        networkReady = false;
        Serial.println("[WiFi] Disconnected. Reconnecting...");

        if (ensureWifiConnected(WIFI_WAIT_MS)) {
            networkReady = true;
            Serial.println("[WiFi] Reconnected.");
            delay(1000);
        } else {
            Serial.println("[WiFi] Reconnect failed.");
            delay(3000);
            return;
        }
    }

    if (!networkReady) {
        delay(3000);
        return;
    }

    // 2. 거리 측정
    int distance = readDistanceAveraged();

    bool occupied = false;
    if (distance != -1) {
        occupied = (distance < OCCUPIED_DISTANCE_CM);
    }

    // 3. 시리얼 출력
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

    // 4. 초기 1회 또는 상태 변화 시 업로드
    if (firstSeatUpload || occupied != prevOccupied) {
        Serial.println("[POST] Uploading seatB state...");
        uploadSeatB(distance, occupied);
        prevOccupied = occupied;
        firstSeatUpload = false;
    } else {
        Serial.println("[POST] seatB unchanged. Skip upload.");
    }

    delay(LOOP_DELAY_MS);
}

// =====================================================
// readDistanceRaw()
// - 초음파 센서 1회 측정
// - 실패 시 -1 반환
// =====================================================
int readDistanceRaw() {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);

    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);

    long duration = pulseIn(ECHO_PIN, HIGH, 30000);

    if (duration == 0) {
        return -1;
    }

    int distance = duration * 17 / 1000;
    return distance;
}

// =====================================================
// readDistanceAveraged()
// - 여러 번 측정 후 평균값 반환
// - 유효값 없으면 -1
// =====================================================
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

    if (validCount == 0) {
        return -1;
    }

    return sum / validCount;
}

// =====================================================
// uploadSeatB()
// - seatB 상태를 JSON으로 만들어 oneM2M에 업로드
// =====================================================
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

// =====================================================
// ensureWifiConnected()
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

            Serial.print("SSID: ");
            Serial.println(WiFi.SSID());

            IPAddress ip = WiFi.localIP();
            Serial.print("IP Address: ");
            Serial.println(ip);

            long rssi = WiFi.RSSI();
            Serial.print("Signal strength (RSSI): ");
            Serial.print(rssi);
            Serial.println(" dBm");

            return true;
        }

        Serial.print(".");
        delay(250);
    }

    Serial.println();
    return false;
}

// =====================================================
// nextRI()
// =====================================================
String nextRI() {
    String ri = "r-";
    ri += String(reqSeq++);
    return ri;
}

// =====================================================
// readHttpStatusLine()
// =====================================================
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

// =====================================================
// post()
// =====================================================
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

// =====================================================
// serializeCIN()
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

// =====================================================
// postCIN()
// =====================================================
int postCIN(String path, String content) {
    String body = serializeCIN(content);
    return post(path, 4, body);
}
