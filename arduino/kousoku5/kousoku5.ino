#include <avr/io.h>
#include <avr/interrupt.h>
#include <math.h>

// デバッグLEDピン設定
const int debugLedPin = 52;
volatile unsigned int intCounter1 = 0; // 割込みカウンター

// 外部割り込みピン設定
const int extInterruptPins[3] = {18, 19, 20}; // INT3, INT2, INT1

// ==== HD44780 LCD制御用ピン設定（4bitモード） ====
const int lcdRS = 2;    // RS (Register Select)
const int lcdE  = 3;    // E  (Enable)
const int lcdD4 = 4;    // D4 (Data bit 4)
const int lcdD5 = 5;    // D5 (Data bit 5
const int lcdD6 = 6;    // D6 (Data bit 6)
const int lcdD7 = 7;    // D7 (Data bit 7)
// RWはGNDに接続（ソフト制御なし）

// LCD表示用バッファ
char lcdLine1[17];  // 1行目（16文字 + 終端）
char lcdLine2[17];  // 2行目（16文字 + 終端）

// ==== タイマー1による1ms処理用 ====
volatile unsigned long msCounter = 0; // ミリ秒カウンター
// 1秒カウンター（1000ミリ秒ごとにインクリメント）
volatile unsigned long oneSecondCounter = 0; 

// 外部割り込みカウンター
volatile unsigned long extInterruptCounter[3] = {0, 0, 0};

// 外部割り込みの時間計測用変数
volatile unsigned long lastInterruptTimeMs[3] = {0, 0, 0}; // 前回の割り込み時間[ms]
volatile unsigned long rotationTimeMs[3] = {0, 0, 0};      // 1回転にかかった時間[ms]

// ==== モータピン設定 ====
const int stepPins[3] = {22, 25, 28};  // M1〜M3 STEP (PUL+)
const int dirPins[3]  = {23, 26, 29};  // M1〜M3 DIR  (DIR+)
const int enaPins[3]  = {24, 27, 30};  // M1〜M3 ENA  (ENA+)

// ==== 基本モータ設定 ====
const int MICRO_STEP_1_2 = 2; // 1/2ステップ
const int MICRO_STEP_1_4 = 4; // 1/4ステップ
const int MICRO_STEP_1_8 = 8; // 1/8ステップ
const int stepsPerRev = 200 * MICRO_STEP_1_2; // 1回転あたりのマイクロステップ数

// ==== シリアル通信用バッファ ====
byte commandBuffer[11]; // コマンドバッファ
int commandIndex = 0;   // バッファのインデックス

volatile bool stepHigh[3] = {false, false, false};
volatile unsigned int stepInterval[3] = {0, 0, 0}; // µs (初期値は後で設定)
volatile bool motorEnabled[3] = {false, false, false};
volatile unsigned long remainingSteps[3] = {0, 0, 0}; // 0=無限動作
// 速度切替時の滑らかさ向上のため、タイマ再初期化を避けてOCRのみ更新するペンディング機構
volatile bool pendingIntervalUpdate[3] = {false, false, false};
volatile unsigned int pendingIntervalUs[3] = {0, 0, 0};

// ==== 台形（または三角）事前計画 ==== 
volatile bool planActive[3] = {false, false, false};
volatile unsigned long planTotalSteps[3] = {0, 0, 0};
volatile unsigned long planStepsDone[3]  = {0, 0, 0};
volatile unsigned long planAccelSteps[3] = {0, 0, 0};
volatile unsigned long planCruiseSteps[3]= {0, 0, 0};
volatile unsigned long planDecelSteps[3] = {0, 0, 0};
volatile float planPeakSpeedSps[3]       = {0.0f, 0.0f, 0.0f};

// ==== 加減速（台形）関連 ==== 
volatile bool useTrapezoid[3] = {false, false, false}; // モータ毎に台形ON/OFF
volatile float currentSpeedSps[3] = {0.0f, 0.0f, 0.0f}; // 現在速度 [steps/s]
volatile float targetSpeedSps[3]  = {0.0f, 0.0f, 0.0f}; // 目標速度 [steps/s]
volatile float accelerationSps2[3] = {4000.0f, 4000.0f, 4000.0f}; // 加速度 [steps/s^2]
const float minStartSpeedSps = 500.0f; // 立ち上がり開始速度（初速）[steps/s]
const float targetRampTimeSec = 0.2f;  // 初速から目標速度までの到達時間 [s]

// ==== STEPピン用ポートポインタとマスク ====
volatile uint8_t *stepPorts[3];
uint8_t stepMasks[3];

// ==== センサピン割り当て ====
// 漏液センサ: デジタル34,35,36（Active LOW想定）。INPUT_PULLUPで使用。
const int leakSensorPins[3]    = {34, 35, 36};

// ===================== デバッグLED制御関数 =====================
inline void setDebugLED(bool on) {
  digitalWrite(debugLedPin, on ? HIGH : LOW);
}

inline void toggleDebugLED() {
  digitalWrite(debugLedPin, !digitalRead(debugLedPin));
}

// ===================== HD44780 LCD制御関数 =====================
// 4bitデータをLCDに送信
void lcdWrite4Bits(byte data) {
  digitalWrite(lcdD4, (data >> 0) & 0x01);
  digitalWrite(lcdD5, (data >> 1) & 0x01);
  digitalWrite(lcdD6, (data >> 2) & 0x01);
  digitalWrite(lcdD7, (data >> 3) & 0x01);
  
  // Enableパルス
  digitalWrite(lcdE, HIGH);
  delayMicroseconds(1);
  digitalWrite(lcdE, LOW);
  delayMicroseconds(100);
}

// LCDにコマンドを送信
void lcdCommand(byte command) {
  digitalWrite(lcdRS, LOW);
  
  // 上位4bit
  lcdWrite4Bits(command >> 4);
  // 下位4bit
  lcdWrite4Bits(command & 0x0F);
  
  // コマンド実行待ち
  if (command == 0x01 || command == 0x02) {
    delay(2);
  } else {
    delayMicroseconds(100);
  }
}

// LCDにデータを送信
void lcdWrite(byte data) {
  digitalWrite(lcdRS, HIGH);
  
  // 上位4bit
  lcdWrite4Bits(data >> 4);
  // 下位4bit
  lcdWrite4Bits(data & 0x0F);
  
  delayMicroseconds(100);
}

// LCD初期化
void lcdInit() {
  // ピンモード設定
  pinMode(lcdRS, OUTPUT);
  pinMode(lcdE, OUTPUT);
  pinMode(lcdD4, OUTPUT);
  pinMode(lcdD5, OUTPUT);
  pinMode(lcdD6, OUTPUT);
  pinMode(lcdD7, OUTPUT);
  
  // 初期化待ち時間
  delay(50);
  
  // 4bitモード初期化シーケンス
  digitalWrite(lcdRS, LOW);
  digitalWrite(lcdE, LOW);
  
  // 3回の0x03送信（8bitモード設定）
  lcdWrite4Bits(0x03);
  delay(5);
  lcdWrite4Bits(0x03);
  delay(5);
  lcdWrite4Bits(0x03);
  delayMicroseconds(150);
  
  // 4bitモード設定
  lcdWrite4Bits(0x02);
  
  // 4bitモード、2行表示、5x8ドット
  lcdCommand(0x28);
  
  // 表示ON、カーソルOFF、ブリンクOFF
  lcdCommand(0x0C);
  
  // 画面クリア
  lcdCommand(0x01);
  delay(2);
  
  // エントリーモード設定（左シフト、インクリメント）
  lcdCommand(0x06);
  
  // 初期メッセージ表示
  lcdSetCursor(0, 0);
  lcdPrint("RaspberryPi");
  lcdSetCursor(0, 1);
  lcdPrint("Camera System");
}

// カーソル位置設定
void lcdSetCursor(byte col, byte row) {
  byte address = (row == 0) ? 0x00 : 0x40;
  address += col;
  lcdCommand(0x80 | address);
}

// 画面クリア
void lcdClear() {
  lcdCommand(0x01);
  delay(2);
}

// 文字列表示
void lcdPrint(const char* str) {
  while (*str) {
    lcdWrite(*str++);
  }
}

// 数値表示
void lcdPrint(int num) {
  char buf[16];
  sprintf(buf, "%d", num);
  lcdPrint(buf);
}

// 浮動小数点表示
void lcdPrint(float num, int decimals) {
  char buf[16];
  dtostrf(num, 0, decimals, buf);
  lcdPrint(buf);
}

// LCD表示更新（システム状態表示）
void lcdUpdateDisplay() {
  static unsigned long lastUpdate = 0;
  unsigned long currentTime = millis();
  
  // 500msごとに更新
  if (currentTime - lastUpdate < 500) return;
  lastUpdate = currentTime;
  
  // 1行目：システム状態とモータ情報
  lcdSetCursor(0, 0);
  int activeMotors = 0;
  for (int i = 0; i < 3; i++) {
    if (motorEnabled[i]) activeMotors++;
  }
  sprintf(lcdLine1, "M:%d/3 %s", activeMotors, 
    (motorEnabled[0] || motorEnabled[1] || motorEnabled[2]) ? "RUN" : "STOP");
  lcdPrint(lcdLine1);
  
  // 2行目：モータ速度とRPM情報
  lcdSetCursor(0, 1);
  if (activeMotors > 0) {
    // 動作中のモータの速度とRPMを表示
    for (int i = 0; i < 3; i++) {
      if (motorEnabled[i]) {
        int rpm = calculateRPM(i);
        sprintf(lcdLine2, "M%d:%drpm", i+1, rpm);
        lcdPrint(lcdLine2);
        break; // 最初の動作中モータのみ表示
      }
    }
  } else {
    // 停止中の場合
    sprintf(lcdLine2, "System Ready");
    lcdPrint(lcdLine2);
  }
}

// 詳細情報表示（コマンド受信時などに使用）
void lcdShowDetailedInfo() {
  // 1行目：モータ状態
  lcdSetCursor(0, 0);
  sprintf(lcdLine1, "M1:%s M2:%s M3:%s",
    motorEnabled[0] ? "ON" : "OFF",
    motorEnabled[1] ? "ON" : "OFF",
    motorEnabled[2] ? "ON" : "OFF");
  lcdPrint(lcdLine1);
  
  // 2行目：RPM情報
  lcdSetCursor(0, 1);
  sprintf(lcdLine2, "RPM:%d,%d,%d",
    calculateRPM(0), calculateRPM(1), calculateRPM(2));
  lcdPrint(lcdLine2);
}

// エラーメッセージ表示
void lcdShowError(const char* errorMsg) {
  lcdSetCursor(0, 0);
  lcdPrint("ERROR:");
  lcdSetCursor(0, 1);
  lcdPrint(errorMsg);
}

// ===================== RPM→Interval変換 =====================
unsigned int rpmToIntervalUs(long rpm) {
  if (rpm <= 0) return 0;
  float pps = (rpm * stepsPerRev) / 60.0;
  return (unsigned int)(1000000.0 / pps);
}

// steps/s 変換ユーティリティ
inline float rpmToSps(long rpm) {
  if (rpm <= 0) return 0.0f;
  return (float)rpm * (float)stepsPerRev / 60.0f;
}

inline unsigned int spsToIntervalUs(float sps) {
  if (sps <= 0.0f) return 0;
  return (unsigned int)(1000000.0f / sps);
}

// ===================== センサ読み出しユーティリティ =====================
inline bool isLeakDetected(int idx) {
  // INPUT_PULLUPのため、漏液検出時はLOWとする想定
  return digitalRead(leakSensorPins[idx]) == LOW;
}

// ===================== ステップトグル関数 =====================
inline void handleStep(int idx) {
  if (!motorEnabled[idx]) return;
  stepHigh[idx] = !stepHigh[idx];

  if (stepHigh[idx]) {
    *stepPorts[idx] |= stepMasks[idx]; // HIGH
    if (remainingSteps[idx] > 0) {
      remainingSteps[idx]--;
      if (planActive[idx]) { planStepsDone[idx]++; }
      if (remainingSteps[idx] == 0) {
        digitalWrite(enaPins[idx], HIGH);  // 励磁OFF
        motorEnabled[idx] = false;
        planActive[idx] = false;
      }
    }

    // 事前に要求されたインターバル更新を反映（CTCの連続性を保つ）
    if (pendingIntervalUpdate[idx]) {
      pendingIntervalUpdate[idx] = false;
      if (pendingIntervalUs[idx] > 0) {
        stepInterval[idx] = pendingIntervalUs[idx];
        switch (idx) {
          case 0: OCR3A = (uint16_t)((16UL * stepInterval[0] / 2UL) - 1UL); break;
          case 1: OCR4A = (uint16_t)((16UL * stepInterval[1] / 2UL) - 1UL); break;
          case 2: OCR5A = (uint16_t)((16UL * stepInterval[2] / 2UL) - 1UL); break;
        }
      }
    }
  } else {
    *stepPorts[idx] &= ~stepMasks[idx]; // LOW
  }

  // --- 台形加減速処理（半周期ごとに更新して滑らかさを向上） ---
  if (useTrapezoid[idx] && motorEnabled[idx]) {
    float accel = accelerationSps2[idx];
    if (accel < 1.0f) accel = 1.0f;

    if (currentSpeedSps[idx] < 1.0f) {
      currentSpeedSps[idx] = minStartSpeedSps;
    }

    // 半周期の時間 [s]
    float dt = (float)stepInterval[idx] / 2000000.0f;

    if (remainingSteps[idx] == 0) {
      // 無限動作（残ステップ=0）は従来通り目標速度へ追従
      if (targetSpeedSps[idx] > 0.0f && currentSpeedSps[idx] < targetSpeedSps[idx]) {
        currentSpeedSps[idx] += accel * dt;
        if (currentSpeedSps[idx] > targetSpeedSps[idx]) currentSpeedSps[idx] = targetSpeedSps[idx];
      } else if (targetSpeedSps[idx] > 0.0f) {
        currentSpeedSps[idx] = targetSpeedSps[idx];
      }
    } else if (planActive[idx]) {
      // 事前計画に基づく台形/三角プロファイル
      unsigned long s = planStepsDone[idx];
      unsigned long accelEnd = planAccelSteps[idx];
      unsigned long cruiseEnd = planAccelSteps[idx] + planCruiseSteps[idx];

      if (s < accelEnd) {
        // 加速フェーズ
        float peak = planPeakSpeedSps[idx];
        if (currentSpeedSps[idx] < peak) {
          currentSpeedSps[idx] += accel * dt;
          if (currentSpeedSps[idx] > peak) currentSpeedSps[idx] = peak;
        }
      } else if (s < cruiseEnd) {
        // 等速フェーズ
        currentSpeedSps[idx] = planPeakSpeedSps[idx];
      } else {
        // 減速フェーズ（最小開始速度まで）
        currentSpeedSps[idx] -= accel * dt;
        if (currentSpeedSps[idx] < minStartSpeedSps) currentSpeedSps[idx] = minStartSpeedSps;
      }
    } else {
      // フォールバック：残ステップからの動的判断（後方互換）
      bool shouldDecel = false;
      float stepsToStop = (currentSpeedSps[idx] * currentSpeedSps[idx]) / (2.0f * accel);
      if ((float)remainingSteps[idx] <= stepsToStop + 1.0f) {
        shouldDecel = true;
      }
      if (shouldDecel) {
        currentSpeedSps[idx] -= accel * dt;
        if (currentSpeedSps[idx] < minStartSpeedSps) currentSpeedSps[idx] = minStartSpeedSps;
      } else {
        if (targetSpeedSps[idx] > 0.0f && currentSpeedSps[idx] < targetSpeedSps[idx]) {
          currentSpeedSps[idx] += accel * dt;
          if (currentSpeedSps[idx] > targetSpeedSps[idx]) currentSpeedSps[idx] = targetSpeedSps[idx];
        } else if (targetSpeedSps[idx] > 0.0f) {
          currentSpeedSps[idx] = targetSpeedSps[idx];
        }
      }
    }

    // 次周期用のインターバルを更新
    unsigned int newInterval = spsToIntervalUs(currentSpeedSps[idx]);
    if (newInterval > 0 && newInterval != stepInterval[idx]) {
      stepInterval[idx] = newInterval;
      switch (idx) {
        case 0: OCR3A = (uint16_t)((16UL * stepInterval[0] / 2UL) - 1UL); break;
        case 1: OCR4A = (uint16_t)((16UL * stepInterval[1] / 2UL) - 1UL); break;
        case 2: OCR5A = (uint16_t)((16UL * stepInterval[2] / 2UL) - 1UL); break;
      }
    }
  }
}

// ===================== 外部割り込み処理 =====================
// 外部割り込み1 (ポート20) のハンドラ
ISR(INT1_vect) {
  extInterruptCounter[2]++;  // 外部割り込みカウンタを増加
  
  // 1回転にかかった時間を計測
  unsigned long currentTimeMs = msCounter;
  if (lastInterruptTimeMs[2] > 0) {
    // 前回の割り込みからの経過時間を計算（時間の保存のみ）
    rotationTimeMs[2] = currentTimeMs - lastInterruptTimeMs[2];
  }
  lastInterruptTimeMs[2] = currentTimeMs;
}

// 外部割り込み2 (ポート19) のハンドラ
ISR(INT2_vect) {
  extInterruptCounter[1]++;  // 外部割り込みカウンタを増加
  
  // 1回転にかかった時間を計測
  unsigned long currentTimeMs = msCounter;
  if (lastInterruptTimeMs[1] > 0) {
    // 前回の割り込みからの経過時間を計算（時間の保存のみ）
    rotationTimeMs[1] = currentTimeMs - lastInterruptTimeMs[1];
  }
  lastInterruptTimeMs[1] = currentTimeMs;
}

// 外部割り込み3 (ポート18) のハンドラ
ISR(INT3_vect) {
  extInterruptCounter[0]++;  // 外部割り込みカウンタを増加
  intCounter1++;
  // 1回転にかかった時間を計測
  unsigned long currentTimeMs = msCounter;
  if (lastInterruptTimeMs[0] > 0) {
    // 前回の割り込みからの経過時間を計算（時間の保存のみ）
    rotationTimeMs[0] = currentTimeMs - lastInterruptTimeMs[0];
  }
  lastInterruptTimeMs[0] = currentTimeMs;
  
  // デバッグLEDをトグル (INT3のみLED連動)
  toggleDebugLED();
}

// RPM計算用の関数（整数型に変更）
int calculateRPM(int idx) {
  if (idx < 0 || idx >= 3) return 0;
  
  if (rotationTimeMs[idx] > 0) {
    // 60000ms / 回転時間[ms] = 回転数/分
    return 60000 / rotationTimeMs[idx];
  } else {
    return 0; // 回転時間が0または未測定の場合は0を返す
  }
}

// ===================== ISR =====================
ISR(TIMER3_COMPA_vect) { handleStep(0); } // M1
ISR(TIMER4_COMPA_vect) { handleStep(1); } // M2
ISR(TIMER5_COMPA_vect) { handleStep(2); } // M3

// 1msごとの割り込み処理
ISR(TIMER1_COMPA_vect) {
  msCounter++; // ミリ秒カウンターをインクリメント
  
  // 1秒カウンターの更新（1000msごと）
  if (msCounter % 1000 == 0) {
    oneSecondCounter++;
    
    // 5秒ごとに回転情報をシリアル出力（デバッグ用）
    if (oneSecondCounter % 5 == 0) 
    {
  //    for (int i = 0; i < 3; i++) {
  //      int rpm = calculateRPM(i);
  //      Serial.print("Sensor");
  //      Serial.print(i+1);
  //      Serial.print(": Rot=");
  //      Serial.print(rotationTimeMs[i]);
  //      Serial.print("ms, RPM=");
  //      Serial.print(rpm);
  //      Serial.print("  ");
  //
      Serial.print(calculateRPM(0));
      Serial.println();
    }
  }

  // 漏液センサ動作チェック（20msごとに実行）
  if (msCounter % 20 == 0) {
    setDebugLED(isLeakDetected(0));
  }
}

// ===================== タイマー設定関数 =====================
// タイマー1を1ms間隔で設定する関数
void setupTimer1ForMillisecond() {
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = 0;
  TCNT1 = 0;
  
  // 1ms間隔の設定 (16MHz / 8 / 2000 = 1kHz = 1ms)
  OCR1A = 1999; // 0から数えるので2000-1
  
  TCCR1B |= (1 << WGM12);  // CTCモード
  TCCR1B |= (1 << CS11);   // 8分周
  TIMSK1 |= (1 << OCIE1A); // 比較一致割り込み有効化
  interrupts();
}

void setupTimer3(unsigned int interval_us) {
  noInterrupts();
  TCCR3A = 0; TCCR3B = 0; TCNT3 = 0;
  OCR3A = (16 * interval_us / 2) - 1;
  TCCR3B |= (1 << WGM32);
  TCCR3B |= (1 << CS30);
  TIMSK3 |= (1 << OCIE3A);
  interrupts();
}

void setupTimer4(unsigned int interval_us) {
  noInterrupts();
  TCCR4A = 0; TCCR4B = 0; TCNT4 = 0;
  OCR4A = (16 * interval_us / 2) - 1;
  TCCR4B |= (1 << WGM42);
  TCCR4B |= (1 << CS40);
  TIMSK4 |= (1 << OCIE4A);
  interrupts();
}

void setupTimer5(unsigned int interval_us) {
  noInterrupts();
  TCCR5A = 0; TCCR5B = 0; TCNT5 = 0;
  OCR5A = (16 * interval_us / 2) - 1;
  TCCR5B |= (1 << WGM52);
  TCCR5B |= (1 << CS50);
  TIMSK5 |= (1 << OCIE5A);
  interrupts();
}

// 外部割り込みの設定
void setupExternalInterrupts() {
  noInterrupts();
  
  // INT1, INT2, INT3 (ポート20, 19, 18) の設定
  for (int i = 0; i < 3; i++) {
    pinMode(extInterruptPins[i], INPUT_PULLUP);
  }
  
  // 立ち下がりエッジで割り込み
  // INT1 (ポート20)
  EICRA |= (1 << ISC11);    // 1
  EICRA &= ~(1 << ISC10);   // 0 -> 10: 立ち下がりエッジで割り込み
  
  // INT2 (ポート19)
  EICRA |= (1 << ISC21);    // 1
  EICRA &= ~(1 << ISC20);   // 0 -> 10: 立ち下がりエッジで割り込み
  
  // INT3 (ポート18)
  EICRA |= (1 << ISC31);    // 1
  EICRA &= ~(1 << ISC30);   // 0 -> 10: 立ち下がりエッジで割り込み
  
  // 割り込み有効化
  EIMSK |= (1 << INT1) | (1 << INT2) | (1 << INT3);
  
  interrupts();
}

// ===================== コマンド処理 =====================
void processCommand(byte* cmd) {
  if (cmd[0] != 0x02 || cmd[10] != 0x03) return;

  byte checksum = 0;
  for (int i = 1; i <= 8; i++) checksum ^= cmd[i];
  if (checksum != cmd[9]) return;

  int pumpNo = cmd[1] - '0';
  if (pumpNo < 1 || pumpNo > 3) return;
  int idx = pumpNo - 1;

  char action = cmd[2];
  char numStr[7];
  memcpy(numStr, &cmd[3], 6);
  numStr[6] = '\0';
  long value = atol(numStr);

  if (action == 'M') {  // モータ開始 (0=無限動作)
    digitalWrite(enaPins[idx], LOW); // 励磁ON
    remainingSteps[idx] = (value > 0) ? value : 0;
    motorEnabled[idx] = true;
    if (useTrapezoid[idx]) {
      // 立ち上がり開始速度に設定
      currentSpeedSps[idx] = minStartSpeedSps;
      if (targetSpeedSps[idx] > 0.0f && targetSpeedSps[idx] < currentSpeedSps[idx]) {
        currentSpeedSps[idx] = targetSpeedSps[idx];
      }
      // 0.2秒で目標速度へ到達するよう加速度を更新
      if (targetSpeedSps[idx] > currentSpeedSps[idx]) {
        float dv = targetSpeedSps[idx] - currentSpeedSps[idx];
        accelerationSps2[idx] = dv / targetRampTimeSec;
        if (accelerationSps2[idx] < 1.0f) accelerationSps2[idx] = 1.0f;
      }
      stepInterval[idx] = spsToIntervalUs(currentSpeedSps[idx]);
      switch(idx) {
        case 0: setupTimer3(stepInterval[0]); break;
        case 1: setupTimer4(stepInterval[1]); break;
        case 2: setupTimer5(stepInterval[2]); break;
      }

      // ステップ数指定時は台形/三角プロファイルを事前計画
      if (remainingSteps[idx] > 0 && targetSpeedSps[idx] > 0.0f) {
        float a = accelerationSps2[idx];
        if (a < 1.0f) a = 1.0f;
        float v0 = currentSpeedSps[idx];
        float vend = minStartSpeedSps; // 終端は最小開始速度まで落とす想定
        float vtar = targetSpeedSps[idx];

        float accelStepsF = 0.0f;
        float decelStepsF = 0.0f;
        if (vtar > v0)  accelStepsF = (vtar*vtar - v0*v0) / (2.0f * a);
        if (vtar > vend) decelStepsF = (vtar*vtar - vend*vend) / (2.0f * a);

        unsigned long accelStepsUL = (unsigned long)(accelStepsF + 0.5f);
        unsigned long decelStepsUL = (unsigned long)(decelStepsF + 0.5f);
        unsigned long total = remainingSteps[idx];

        float peak = vtar;
        unsigned long cruiseStepsUL = 0;
        if (total >= accelStepsUL + decelStepsUL) {
          // 台形
          cruiseStepsUL = total - accelStepsUL - decelStepsUL;
        } else {
          // 三角：到達可能なピーク速度を再計算
          float s = (a * (float)total) + (v0*v0 + vend*vend) * 0.5f;
          if (s < v0*v0) s = v0*v0;
          peak = sqrtf(s);
          // 再算出
          accelStepsF = (peak*peak - v0*v0) / (2.0f * a);
          decelStepsF = (peak*peak - vend*vend) / (2.0f * a);
          accelStepsUL = (unsigned long)(accelStepsF + 0.5f);
          decelStepsUL = total > accelStepsUL ? (total - accelStepsUL) : 0UL; // 残りを減速に割当
          cruiseStepsUL = 0;
        }

        planActive[idx] = true;
        planTotalSteps[idx]  = total;
        planStepsDone[idx]   = 0;
        planAccelSteps[idx]  = accelStepsUL;
        planCruiseSteps[idx] = cruiseStepsUL;
        planDecelSteps[idx]  = decelStepsUL;
        planPeakSpeedSps[idx]= peak;
      } else {
        planActive[idx] = false;
        planStepsDone[idx] = 0;
      }
    } else {
      // 等速モード時も現在のstepIntervalでタイマをセット（開始時の位相不整合を避ける）
      switch(idx) {
        case 0: setupTimer3(stepInterval[0]); break;
        case 1: setupTimer4(stepInterval[1]); break;
        case 2: setupTimer5(stepInterval[2]); break;
      }
      planActive[idx] = false;
      planStepsDone[idx] = 0;
    }
  } else if (action == 'S') {  // 停止
    motorEnabled[idx] = false;
    digitalWrite(enaPins[idx], HIGH);  // 励磁OFF
    remainingSteps[idx] = 0;
    currentSpeedSps[idx] = 0.0f;
    planActive[idx] = false;
    planStepsDone[idx] = 0;
  } else if (action == 'F') {  // 正転
    digitalWrite(dirPins[idx], HIGH);
  } else if (action == 'R') {  // 逆転
    digitalWrite(dirPins[idx], LOW);
  } else if (action == 'V') {  // 速度変更 (rpm)
    if (value > 0) {
      if (useTrapezoid[idx]) {
        targetSpeedSps[idx] = rpmToSps(value);
        // 0.2秒で新しい目標速度へ到達するよう加速度を更新
        float base = (currentSpeedSps[idx] > 1.0f) ? currentSpeedSps[idx] : minStartSpeedSps;
        if (targetSpeedSps[idx] > base) {
          float dv = targetSpeedSps[idx] - base;
          accelerationSps2[idx] = dv / targetRampTimeSec;
          if (accelerationSps2[idx] < 1.0f) accelerationSps2[idx] = 1.0f;
        }
      } else {
        unsigned int newInterval = rpmToIntervalUs(value);
        stepInterval[idx] = newInterval;               // 変数を先に更新
        pendingIntervalUs[idx] = newInterval;          // 実レジスタ更新はISRで連続的に反映
        pendingIntervalUpdate[idx] = true;
        targetSpeedSps[idx] = rpmToSps(value);
      }
    }
  } else if (action == 'E') {  // Enable ON
    digitalWrite(enaPins[idx], LOW);
  } else if (action == 'D') {  // Enable OFF
    digitalWrite(enaPins[idx], HIGH);
  } else if (action == 'A') {  // 台形加減速のON/OFF（0:OFF, それ以外:ON）
    useTrapezoid[idx] = (value != 0);
    // OFFにしたら当該モータのみ等速設定へ即時反映
    if (!useTrapezoid[idx]) {
      if (targetSpeedSps[idx] > 0.0f) {
        currentSpeedSps[idx] = targetSpeedSps[idx];
        unsigned int newInterval = spsToIntervalUs(targetSpeedSps[idx]);
        stepInterval[idx] = newInterval;
        pendingIntervalUs[idx] = newInterval;  // 再初期化せず次エッジでOCR更新
        pendingIntervalUpdate[idx] = true;
      }
      planActive[idx] = false;
      planStepsDone[idx] = 0;
    }
  } else if (action == 'C') {  // 電流データ取得（ダミー応答）
    // STX + ポンプNo + 電流値(符号+5桁整数) + ETX + CS の形式で送信
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = pumpNo + '0';  // ポンプ番号
    
    // ダミーの電流値 "+00000" を設定
    const char* dummyCurrent = "+00000";
    for (int i = 0; i < 6; i++) {
      response[2 + i] = dummyCurrent[i];
    }
    
    // チェックサム計算
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCDに詳細情報を表示
    lcdShowDetailedInfo();
  } else if (action == 'X') {  // 回転情報取得
    // STX + ポンプNo + RPM(6桁整数) + ETX + CS の形式で送信
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = pumpNo + '0';  // ポンプ番号
    
    // RPMを6桁で整形
    int rpm = calculateRPM(pumpNo - 1); // ポンプ番号に対応するセンサーのRPMを計算
    char rpmStr[7];
    sprintf(rpmStr, "%06d", rpm); // 6桁固定で左側を0埋め
    
    // RPMデータをコピー
    for (int i = 0; i < 6; i++) {
      response[2 + i] = rpmStr[i];
    }
    
    // チェックサム計算
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCDに詳細情報を表示
    lcdShowDetailedInfo();
  }
}

// ===================== SETUP =====================
void setup() {
  for (int i = 0; i < 3; i++) {
    pinMode(stepPins[i], OUTPUT);
    pinMode(dirPins[i], OUTPUT);
    pinMode(enaPins[i], OUTPUT);
    digitalWrite(enaPins[i], LOW);
    digitalWrite(dirPins[i], HIGH);

    // ポートとビットマスクを計算
    uint8_t pin = stepPins[i];
    stepPorts[i] = portOutputRegister(digitalPinToPort(pin));
    stepMasks[i] = digitalPinToBitMask(pin);

    // 初期速度 = 200rpm
    stepInterval[i] = rpmToIntervalUs(200);
    targetSpeedSps[i] = rpmToSps(200);
  }

  // 漏液センサピン設定
  for (int i = 0; i < 3; i++) {
    pinMode(leakSensorPins[i], INPUT_PULLUP);
  }

  // デバッグLEDピン設定
  pinMode(debugLedPin, OUTPUT);
  digitalWrite(debugLedPin, LOW); // 初期状態はOFF

  // 外部割り込み時間計測の初期化
  for (int i = 0; i < 3; i++) {
    lastInterruptTimeMs[i] = 0;
    rotationTimeMs[i] = 0;
  }
  
  // 外部割り込みの設定
  setupExternalInterrupts();
  
  // 1msタイマーの設定
  setupTimer1ForMillisecond();

  setupTimer3(stepInterval[0]); // M1
  setupTimer4(stepInterval[1]); // M2
  setupTimer5(stepInterval[2]); // M3

  // LCD初期化
  lcdInit();

  Serial.begin(9600);
}

// ===================== LOOP =====================
void loop() {

  if (Serial.available()) {
    byte b = Serial.read();
    if (commandIndex == 0 && b != 0x02) return;
    commandBuffer[commandIndex++] = b;
    if (commandIndex >= 11) {
      processCommand(commandBuffer);
      commandIndex = 0;
    }
  }
  
  // LCD表示更新
  lcdUpdateDisplay();
}
