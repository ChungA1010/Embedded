// =====================================================
// oneM2M DHT11 + HC-SR04 실습 - Arduino UNO R4 WiFi
// 온습도 / 착석 상태 데이터(A)를 oneM2M 플랫폼으로 전송
// =====================================================

#define ARDUINOJSON_SLOT_ID_SIZE       1
#define ARDUINOJSON_STRING_LENGTH_SIZE 1
#define ARDUINOJSON_USE_DOUBLE         0
#define ARDUINOJSON_USE_LONG_LONG      0

// ── 라이브러리 포함 ──────────────────────────────────
#include <WiFiS3.h>           // Arduino UNO R4 WiFi 모듈 제어
#include <WiFiSSLClient.h>    // HTTPS(TLS/SSL) 통신 클라이언트
#include <ArduinoJson.h>      // JSON 직렬화/역직렬화
#include <DHT.h>              // DHT11 온습도 센서 제어

#include "secrets.h"          // WiFi SSID/PW 및 API 인증 정보 (별도 파일)

// ── DHT11 센서 설정 ──────────────────────────────────
#define DHTPIN   2
#define DHTTYPE  DHT11

// ── HC-SR04 센서 설정 ─────────────────────────────────
#define TRIG_PIN 9
#define ECHO_PIN 8

// ── 타이밍 및 네트워크 설정 ───────────────────────────
const unsigned long LOOP_DELAY_MS = 10000;      // 데이터 전송 주기 (10초)
const unsigned long WIFI_WAIT_MS  = 30000;      // WiFi 연결 최대 대기 시간
const unsigned long HTTP_WAIT_MS  = 10000;      // HTTP 응답 최대 대기 시간
const int PORT = 443;
const char* HOST = "onem2m.iotcoss.ac.kr";

// ── oneM2M 인증 정보 ─────────────────────────────────
const char* ONEM2M_ORIGIN = ORIGIN;    // 학번_임의값 등으로 설정
const char* RVI           = "2a";

// ── oneM2M 리소스 경로 설정 ───────────────────────────
const char* CSEBASE  = "/Mobius";
const char* AE_RN    = "ae_table";
const char* TEM_CNT  = "tem";
const char* HUM_CNT  = "hum";
const char* SEAT_CNT = "seatA";

// ── 착석 판정 설정 ───────────────────────────────────
const int OCCUPIED_DISTANCE_CM = 30;   // 이 거리보다 가까우면 착석으로 판정
const int DISTANCE_SAMPLES      = 5;   // 평균을 위한 측정 횟수

// ── 전역 변수 ─────────────────────────────────────────
bool networkReady = false;     // 네트워크 송신 가능 여부
bool prevOccupied = false;     // 이전 착석 상태
bool firstSeatUpload = true;   // 초기 상태 1회 업로드 여부
uint32_t reqSeq = 1;           // HTTP 요청 ID 시퀀스

// ── 객체 생성 ─────────────────────────────────────────
DHT dht(DHTPIN, DHTTYPE);
WiFiSSLClient wifi;

// =====================================================
// 함수 선언
// =====================================================
bool ensureWifiConnected(unsigned long maxWaitMs);
String nextRI();
int readHttpStatusLine();

int get(String path);
int post(String path, String resourceType, int ty, String body);

String serializeAE(String resourceName);
String serializeCNT(String resourceName);
String serializeCIN(String content);

int postAE(String path, String resourceName);
int postCNT(String path, String resourceName);
int postCIN(String path, String content);

int readDistanceRaw();
int readDistanceAveraged();
void uploadSeat(int distance, bool occupied);

// =====================================================
// setup()
// =====================================================
void setup() {
    Serial.begin(115200);
    while (!Serial);

    dht.begin();

    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);
    digitalWrite(TRIG_PIN, LOW);

    if (WiFi.status() == WL_NO_MODULE) {
        Serial.println("[FATAL] Communication with WiFi module failed!");
        while (true) delay(1000);
    }

    Serial.println("[SETUP] Connecting WiFi...");
    if (!ensureWifiConnected(WIFI_WAIT_MS)) {
        Serial.println("[FATAL] WiFi connect failed.");
        while (true) delay(1000);
    }

    delay(3000);   // 네트워크 안정화 대기
    networkReady = true;

    Serial.println("[SETUP] Complete. Entering loop...");
}

// =====================================================
// loop()
// =====================================================
void loop() {
    // 1. WiFi 연결 확인 및 복구
    if (WiFi.status() != WL_CONNECTED) {
        networkReady = false;
        Serial.println("[WiFi] Disconnected. Reconnecting...");

        if (ensureWifiConnected(WIFI_WAIT_MS)) {
            networkReady = true;
            Serial.println("[WiFi] Reconnected successfully.");
            delay(1000);
        } else {
            Serial.println("[WiFi] Reconnect failed. Retry in next loop.");
            delay(3000);
            return;
        }
    }

    if (!networkReady) {
        delay(3000);
        return;
    }

    // 2. DHT11 읽기
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (isnan(temperature) || isnan(humidity)) {
        Serial.println("[ERROR] Failed to read from DHT11.");
        delay(2000);
        return;
    }

    // 3. 초음파 거리 읽기(평균)
    int distance = readDistanceAveraged();

    bool occupied = false;
    if (distance != -1) {
        occupied = (distance < OCCUPIED_DISTANCE_CM);
    }

    // 4. 시리얼 로그
    Serial.println("=================================");
    Serial.print("TEM: ");
    Serial.print(temperature);
    Serial.println(" °C");

    Serial.print("HUM: ");
    Serial.print(humidity);
    Serial.println(" %");

    if (distance == -1) {
        Serial.println("DIST: invalid");
        Serial.println("SEAT: unknown -> treated as not occupied");
    } else {
        Serial.print("DIST: ");
        Serial.print(distance);
        Serial.println(" cm");

        Serial.print("SEAT: ");
        Serial.println(occupied ? "OCCUPIED" : "EMPTY");
    }
    Serial.println("=================================");

    // 5. oneM2M 업로드
    Serial.println("[POST] Uploading temperature...");
    int scTem = postCIN(String(CSEBASE) + "/" + AE_RN + "/" + TEM_CNT, String(temperature, 1));
    Serial.print("[POST][TEM] status = ");
    Serial.println(scTem);

    Serial.println("[POST] Uploading humidity...");
    int scHum = postCIN(String(CSEBASE) + "/" + AE_RN + "/" + HUM_CNT, String(humidity, 1));
    Serial.print("[POST][HUM] status = ");
    Serial.println(scHum);

    // 6. 좌석 상태는 초기 1회 또는 상태 변화 시 업로드
    if (firstSeatUpload || occupied != prevOccupied) {
        Serial.println("[POST] Uploading seat state...");
        uploadSeat(distance, occupied);
        prevOccupied = occupied;
        firstSeatUpload = false;
    } else {
        Serial.println("[POST] Seat unchanged. Skip upload.");
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

    long duration = pulseIn(ECHO_PIN, HIGH, 30000);  // 최대 30ms 대기

    if (duration == 0) {
        return -1;
    }

    // cm 환산: duration(us) / 58 정도와 유사
    int distance = duration * 17 / 1000;
    return distance;
}

// =====================================================
// readDistanceAveraged()
// - 여러 번 측정 후 유효값 평균 반환
// - 유효값이 없으면 -1
// =====================================================
int readDistanceAveraged() {
    long sum = 0;
    int validCount = 0;

    for (int i = 0; i < DISTANCE_SAMPLES; i++) {
        int d = readDistanceRaw();

        if (d != -1 && d > 0 && d < 400) {  // HC-SR04 유효 범위 대략 필터
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
// uploadSeat()
// - 좌석 상태를 JSON 문자열로 만들어 oneM2M에 업로드
// =====================================================
void uploadSeat(int distance, bool occupied) {
    StaticJsonDocument<128> seatDoc;
    seatDoc["distance"] = distance;
    seatDoc["occupied"] = occupied;

    String payload;
    serializeJson(seatDoc, payload);

    int sc = postCIN(
        String(CSEBASE) + "/" + AE_RN + "/" + SEAT_CNT,
        payload
    );

    Serial.print("[POST][SEAT] status = ");
    Serial.println(sc);
}

// =====================================================
// ensureWifiConnected()
// - WiFi 연결 보장
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
// - 고유 요청 ID 생성
// =====================================================
String nextRI() {
    String ri = "r-";
    ri += String(reqSeq++);
    return ri;
}

// =====================================================
// readHttpStatusLine()
// - HTTP 상태 코드 파싱
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
// get()
// - GET 요청
// =====================================================
int get(String path) {
    Serial.println("----------------------");

    if (!wifi.connect(HOST, PORT)) {
        Serial.println("[ERROR] TLS connect failed (GET)");
        wifi.stop();
        return -1;
    }

    String ri = nextRI();

    wifi.println("GET " + path + " HTTP/1.1");
    wifi.println("Host: " + String(HOST));
    wifi.println("X-M2M-Origin: " + String(ONEM2M_ORIGIN));
    wifi.println("X-M2M-RI: " + ri);
    wifi.println("X-M2M-RVI: " + String(RVI));
    wifi.println("X-API-KEY: " + String(API_KEY));
    wifi.println("X-AUTH-CUSTOM-LECTURE: " + String(LECTURE));
    wifi.println("X-AUTH-CUSTOM-CREATOR: " + String(CREATOR));
    wifi.println("Accept: application/json");
    wifi.println("Connection: close");
    wifi.println();

    unsigned long t0 = millis();
    while (!wifi.available()) {
        if (millis() - t0 > HTTP_WAIT_MS) {
            Serial.println("[ERROR] Response timeout (GET)");
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
// post()
// - POST 요청 공통 함수
// =====================================================
int post(String path, String resourceType, int ty, String body) {
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
// serializeAE() / serializeCNT() / serializeCIN()
// =====================================================
String serializeAE(String resourceName) {
    StaticJsonDocument<128> doc;
    JsonObject m2m_ae = doc.createNestedObject("m2m:ae");
    m2m_ae["rn"]  = resourceName;
    m2m_ae["api"] = "N.test";
    m2m_ae["rr"]  = false;

    String out;
    serializeJson(doc, out);
    return out;
}

String serializeCNT(String resourceName) {
    StaticJsonDocument<64> doc;
    JsonObject m2m_cnt = doc.createNestedObject("m2m:cnt");
    m2m_cnt["rn"] = resourceName;

    String out;
    serializeJson(doc, out);
    return out;
}

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
// postAE() / postCNT() / postCIN()
// =====================================================
int postAE(String path, String resourceName) {
    String body = serializeAE(resourceName);
    return post(path, "AE", 2, body);
}

int postCNT(String path, String resourceName) {
    String body = serializeCNT(resourceName);
    return post(path, "CNT", 3, body);
}

int postCIN(String path, String content) {
    String body = serializeCIN(content);
    return post(path, "CIN", 4, body);
}
