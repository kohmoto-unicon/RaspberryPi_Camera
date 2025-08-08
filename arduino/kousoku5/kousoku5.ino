#include <avr/io.h>
#include <avr/interrupt.h>
#include <math.h>

// ==== モータピン設定 ====
const int stepPins[3] = {22, 25, 28};  // M1〜M3 STEP (PUL+)
const int dirPins[3]  = {23, 26, 29};  // M1〜M3 DIR  (DIR+)
const int enaPins[3]  = {24, 27, 30};  // M1〜M3 ENA  (ENA+)

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
// 漏液センサ: デジタル16,17,18（Active LOW想定）。INPUT_PULLUPで使用。
const int leakSensorPins[3]    = {16, 17, 18};
// 電流センサ（脱調チェック用）: A0, A1, A2
const int currentSensorPins[3] = {A0, A1, A2};

// ==== コマンドバッファ ====
byte commandBuffer[11];
int commandIndex = 0;

// ==== マイクロステップ設定 ====
const int stepsPerRev = 200 * 2; // 1回転あたりのマイクロステップ数 (1/2)

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

inline int readCurrentRaw(int idx) {
  // 0..1023 (5V基準) の生ADC値
  return analogRead(currentSensorPins[idx]);
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

// ===================== ISR =====================
ISR(TIMER3_COMPA_vect) { handleStep(0); } // M1
ISR(TIMER4_COMPA_vect) { handleStep(1); } // M2
ISR(TIMER5_COMPA_vect) { handleStep(2); } // M3

// ===================== タイマー設定関数 =====================
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

  // センサピン設定
  for (int i = 0; i < 3; i++) {
    pinMode(leakSensorPins[i], INPUT_PULLUP);
  }
  // ADC設定はデフォルトのまま（A0〜A2を使用）。必要であれば分解能/基準電圧を変更可。

  setupTimer3(stepInterval[0]); // M1
  setupTimer4(stepInterval[1]); // M2
  setupTimer5(stepInterval[2]); // M3

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
}
