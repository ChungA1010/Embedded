#define RAW_BUFFER_LENGTH 1000
#define RECORD_GAP_MICROS 20000
#include <IRremote.hpp>

#define IR_RECEIVE_PIN 2

void printRawArray() {
  Serial.println("uint16_t rawData[] = {");

  for (uint16_t i = 1; i < IrReceiver.irparams.rawlen; i++) {
    uint32_t usec = IrReceiver.irparams.rawbuf[i] * 50;  // 보통 50us tick
    Serial.print(usec);

    if (i < IrReceiver.irparams.rawlen - 1) {
      Serial.print(", ");
    }

    if (i % 6 == 0) {
      Serial.println();
    }
  }

  Serial.println("\n};");
  Serial.print("uint16_t rawLen = ");
  Serial.print(IrReceiver.irparams.rawlen - 1);
  Serial.println(";");
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);
  Serial.println("에어컨 raw 수신 대기...");
}

void loop() {
  if (IrReceiver.decode()) {
    Serial.println("===== AIRCON IR CAPTURE =====");
    IrReceiver.printIRResultShort(&Serial);
    Serial.println();

    Serial.print("rawlen = ");
    Serial.println(IrReceiver.irparams.rawlen);

    printRawArray();
    Serial.println("-----------------------------");

    delay(500);
    IrReceiver.resume();
  }
}
