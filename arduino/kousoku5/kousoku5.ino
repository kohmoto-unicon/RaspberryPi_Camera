#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/eeprom.h>
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
const unsigned long RPM_TIMEOUT_MS = 3000;                 // 回転数タイムアウト時間（3秒）

// ==== モータピン設定 ====
const int stepPins[3] = {22, 25, 28};  // M1〜M3 STEP (PUL+)
const int dirPins[3]  = {23, 26, 29};  // M1〜M3 DIR  (DIR+)
const int enaPins[3]  = {24, 27, 30};  // M1〜M3 ENA  (ENA+)

// ==== バルブ制御ピン設定 ====
const int valvePins[3] = {40, 41, 42}; // バルブ制御ポート1,2,3

// ==== バルブ常時Openフラグ ====
// 初期値はOFF（false）
volatile bool valveNormallyOpen[3] = {false, false, false};

// ==== 励磁常時ONフラグ ====
// 初期値はOFF（false）
volatile bool excitationAlwaysOn[3] = {false, false, false};

// ==== 基本モータ設定 ====
const int MICRO_STEP_1_2 = 2; // 1/2ステップ
const int MICRO_STEP_1_4 = 4; // 1/4ステップ
const int MICRO_STEP_1_8 = 8; // 1/8ステップ
const int stepsPerRev = 200 * MICRO_STEP_1_2; // 1回転あたりのマイクロステップ数

// ==== グローバル速度設定 ====
volatile long globalSpeedRpm = 200; // 全モータ共通の目標速度（デフォルト200rpm、最大300rpm）

// ==== モーター停止処理用フラグ ====
volatile bool motorStopPending[3] = {false, false, false}; // 停止処理待ちフラグ
volatile bool fixedStepCompleted[3] = {false, false, false}; // 固定ステップ完了フラグ（remainingSteps 1→0遷移検出）

// ==== 台形加減速計算カウンター ====
volatile uint8_t trapezoidCalcCounter[3] = {0, 0, 0}; // 加減速計算の間引きカウンター（4回に1回実行）

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
const float minStartSpeedSps = 650.0f; // 立ち上がり開始速度（初速）[steps/s]
const float targetRampTimeSec = 0.2f;  // 初速から目標速度までの到達時間 [s]

// ==== 停止時の減速制御 ====
volatile bool stopRequested[3] = {false, false, false}; // 停止要求フラグ
volatile unsigned long decelStepsRequired[3] = {0, 0, 0}; // 減速に必要なステップ数
volatile unsigned long decelStartStep[3] = {0, 0, 0}; // 減速開始ステップ位置
volatile bool isDecelerating[3] = {false, false, false}; // 減速中フラグ
volatile unsigned long currentRunSteps[3] = {0, 0, 0}; // 現在の動作での一時的なステップカウンター（Sコマンド用）

// ==== 新仕様: 400ステップサイクルカウンタと停止制御 ====
volatile unsigned int stepCounter[3] = {0, 0, 0}; // 1-400の範囲でカウント（401→1にリセット）
volatile float stopCommandSpeedRpm[3] = {0.0f, 0.0f, 0.0f}; // S受信時の速度(rpm)を保持
volatile unsigned long stepsToStop[3] = {0, 0, 0}; // 停止までのステップ数（800 - stepCounter）
volatile bool maintainConstantSpeed[3] = {false, false, false}; // 一定速度維持フラグ

// ==== 台形加速事前計算配列 ====
#define MAX_TRAPEZOID_STEPS 600   // 最大ステップ数（200rpm、0.2秒立ち上げ用）
volatile unsigned int precomputedIntervals[3][MAX_TRAPEZOID_STEPS]; // 事前計算されたインターバル配列
volatile unsigned int precomputedStepCount[3] = {0, 0, 0}; // 各モータの事前計算ステップ数
volatile unsigned int precomputedIndex[3] = {0, 0, 0}; // 現在の配列インデックス
volatile bool usePrecomputed[3] = {false, false, false}; // 事前計算配列使用フラグ
volatile bool precomputedInitialized = false; // 起動時初期化フラグ

// ==== STEPピン用ポートポインタとマスク ====
volatile uint8_t *stepPorts[3];
uint8_t stepMasks[3];

// ==== センサピン割り当て ====
// 漏液センサ: デジタル34,35,36（Active LOW想定）。INPUT_PULLUPで使用。
const int leakSensorPins[3]    = {34, 35, 36};

// 漏液監視用カウンタ/フラグ
volatile uint8_t leakConsecutiveOnCount = 0; // 連続ON回数（100ms刻み）
volatile bool leakStopRequested = false;     // 停止要求フラグ（loopで処理）
volatile bool leakDetected = false;          // 漏液検知状態フラグ
volatile unsigned long leakDetectionTime = 0; // 漏液検知時刻
volatile uint8_t leakConsecutiveOffCount = 0; // 連続OFF回数（100ms刻み）
const unsigned long LEAK_RECOVERY_TIME_MS = 5000; // 自動復帰時間（5秒）

// ==== ポンプ状態管理 ====
// ポンプの状態を定義
enum PumpState {
  PUMP_STOPPED = 0,    // 完全停止（励磁OFF）
  PUMP_STANDBY = 1,    // 待機中（励磁ON、動作停止）
  PUMP_RUNNING = 2     // 動作中（励磁ON、動作中）
};

// 3台のポンプの状態を格納する配列
volatile PumpState pumpStates[3] = {PUMP_STOPPED, PUMP_STOPPED, PUMP_STOPPED};

// ==== EEPROMステップ数管理 ====
// 各モーターの累積ステップ数を保存する変数
volatile unsigned long totalSteps[3] = {0, 0, 0};
// EEPROMアドレス定義（各モーター用に4バイトずつ確保）
const int EEPROM_ADDR_MOTOR1 = 0;
const int EEPROM_ADDR_MOTOR2 = 4;
const int EEPROM_ADDR_MOTOR3 = 8;
// 400ステップ = 1回転
const unsigned long STEPS_PER_REVOLUTION = 400;

// ==== Valve制御遅延管理 ====
// Valve制御の遅延タイプ
enum ValveDelayType {
  VALVE_DELAY_NONE = 0,        // 遅延なし
  VALVE_DELAY_OPEN_BEFORE = 1, // モーター開始前のValve開放遅延
  VALVE_DELAY_CLOSE_AFTER = 2  // モーター停止後のValve閉鎖遅延
};

// Valve制御遅延管理構造体
struct ValveDelayManager {
  volatile bool active;                    // 遅延処理がアクティブか
  volatile ValveDelayType delayType;      // 遅延タイプ
  volatile int pumpIndex;                 // 対象ポンプインデックス（0-2）
  volatile unsigned long startTime;       // 遅延開始時刻
  volatile unsigned long delayDuration;   // 遅延時間（ミリ秒）
  volatile bool valveActionPending;       // Valve操作が待機中か
  volatile bool motorActionPending;       // モーター操作が待機中か
  volatile bool valveState;               // 実行予定のValve状態（true=開く、false=閉じる）
  volatile bool motorEnable;              // 実行予定のモーター状態（true=開始、false=停止）
  volatile unsigned long remainingSteps;  // 実行予定の残ステップ数
};

// 3台のポンプ用のValve遅延管理配列
volatile ValveDelayManager valveDelayManagers[3] = {
  {false, VALVE_DELAY_NONE, 0, 0, 0, false, false, false, false, 0},
  {false, VALVE_DELAY_NONE, 0, 0, 0, false, false, false, false, 0},
  {false, VALVE_DELAY_NONE, 0, 0, 0, false, false, false, false, 0}
};

// Valve制御遅延時間定数（ミリ秒）
const unsigned long VALVE_DELAY_MS = 500; // 0.5秒

// ===================== Valve遅延管理関数 =====================
// Valve遅延管理を開始する関数
void startValveDelay(int pumpIdx, ValveDelayType delayType, bool valveState, bool motorEnable, unsigned long steps = 0) {
  if (pumpIdx < 0 || pumpIdx >= 3) return;
  
  noInterrupts();
  valveDelayManagers[pumpIdx].active = true;
  valveDelayManagers[pumpIdx].delayType = delayType;
  valveDelayManagers[pumpIdx].pumpIndex = pumpIdx;
  valveDelayManagers[pumpIdx].startTime = msCounter;
  valveDelayManagers[pumpIdx].delayDuration = VALVE_DELAY_MS;
  valveDelayManagers[pumpIdx].valveActionPending = true;
  valveDelayManagers[pumpIdx].motorActionPending = true;
  valveDelayManagers[pumpIdx].valveState = valveState;
  valveDelayManagers[pumpIdx].motorEnable = motorEnable;
  valveDelayManagers[pumpIdx].remainingSteps = steps;
  interrupts();
}

// Valve遅延管理を停止する関数
void stopValveDelay(int pumpIdx) {
  if (pumpIdx < 0 || pumpIdx >= 3) return;
  
  noInterrupts();
  valveDelayManagers[pumpIdx].active = false;
  valveDelayManagers[pumpIdx].delayType = VALVE_DELAY_NONE;
  valveDelayManagers[pumpIdx].valveActionPending = false;
  valveDelayManagers[pumpIdx].motorActionPending = false;
  interrupts();
}

// Valve遅延処理を実行する関数（1msタイマーから呼び出される）
void processValveDelays() {
  for (int i = 0; i < 3; i++) {
    if (!valveDelayManagers[i].active) continue;
    
    unsigned long elapsed = msCounter - valveDelayManagers[i].startTime;
    
    if (valveDelayManagers[i].delayType == VALVE_DELAY_OPEN_BEFORE) {
      // モーター開始前のValve開放遅延
      if (valveDelayManagers[i].valveActionPending) {
        // Valve操作を即座に実行
        if (valveDelayManagers[i].valveState) {
          openValve(i + 1); // ポンプ番号は1-3
        } else {
          // バルブ常時OpenフラグがONの場合、バルブを閉じない
          if (!valveNormallyOpen[i]) {
            closeValve(i + 1);
          }
        }
        valveDelayManagers[i].valveActionPending = false;
        // 遅延タイマーをリセット（Valve操作後から0.5秒後にモーター開始）
        valveDelayManagers[i].startTime = msCounter;
      } else if (elapsed >= valveDelayManagers[i].delayDuration && valveDelayManagers[i].motorActionPending) {
        // 0.5秒遅延後にモーター操作を実行
        if (valveDelayManagers[i].motorEnable) {
          // モーター開始処理
          digitalWrite(enaPins[i], LOW); // 励磁ON
          remainingSteps[i] = valveDelayManagers[i].remainingSteps;
          motorEnabled[i] = true;
            // 動作開始時に減速開始タイミングを計算（固定回転用）
            if (planActive[i]) {
              decelStartStep[i] = currentRunSteps[i] + planAccelSteps[i] + planCruiseSteps[i];
            }
            // 起動時に目標速度・初速・加速度を再計算（停止後の低速化防止）
            if (useTrapezoid[i]) {
              // 目標速度は globalSpeedRpm を基準に再設定
              targetSpeedSps[i] = rpmToSps(globalSpeedRpm);
              if (targetSpeedSps[i] <= minStartSpeedSps) {
                currentSpeedSps[i] = targetSpeedSps[i];
              } else {
                currentSpeedSps[i] = minStartSpeedSps;
              }
              if (targetSpeedSps[i] > currentSpeedSps[i]) {
                float dv = targetSpeedSps[i] - currentSpeedSps[i];
                accelerationSps2[i] = dv / targetRampTimeSec;
                if (accelerationSps2[i] < 1.0f) accelerationSps2[i] = 1.0f;
              }
            }
          updatePumpState(i);
          
          // 台形加減速設定
          if (useTrapezoid[i]) {
            // 加減速計算カウンターをリセット
            trapezoidCalcCounter[i] = 0;
            
            // 【新仕様】初期速度設定
            // 目標速度が設定されていない場合はglobalSpeedRpmを使用
            if (targetSpeedSps[i] < 1.0f) {
              targetSpeedSps[i] = rpmToSps(globalSpeedRpm);
            }
            
            // 目標速度が650steps/s（minStartSpeedSps）以下の場合は加速不要、最初から目標速度で開始
            if (targetSpeedSps[i] <= minStartSpeedSps) {
              currentSpeedSps[i] = targetSpeedSps[i];
            } else {
              // 目標速度が650steps/sより高い場合は、650steps/s（minStartSpeedSps）から開始
              currentSpeedSps[i] = minStartSpeedSps; // 650steps/s
            }
            
            // 加速度の計算（目標速度への到達時間を考慮）- 互換性のため残す
            if (targetSpeedSps[i] > currentSpeedSps[i]) {
              float dv = targetSpeedSps[i] - currentSpeedSps[i];
              accelerationSps2[i] = dv / targetRampTimeSec;
              if (accelerationSps2[i] < 1.0f) accelerationSps2[i] = 1.0f;
            }
            
            // 事前計算配列は使用しない（新仕様では1ステップ4rpm加速を使用）
            usePrecomputed[i] = false;
            precomputedIndex[i] = 0;
            
            stepInterval[i] = spsToIntervalUs(currentSpeedSps[i]);
            switch(i) {
              case 0: setupTimer3(stepInterval[0]); break;
              case 1: setupTimer4(stepInterval[1]); break;
              case 2: setupTimer5(stepInterval[2]); break;
            }
          } else {
            switch(i) {
              case 0: setupTimer3(stepInterval[0]); break;
              case 1: setupTimer4(stepInterval[1]); break;
              case 2: setupTimer5(stepInterval[2]); break;
            }
          }
        }
        valveDelayManagers[i].motorActionPending = false;
        // 遅延処理完了
        stopValveDelay(i);
      }
    } else if (valveDelayManagers[i].delayType == VALVE_DELAY_CLOSE_AFTER) {
      // モーター停止後のValve閉鎖遅延
      if (elapsed >= valveDelayManagers[i].delayDuration && valveDelayManagers[i].valveActionPending) {
        // 0.5秒遅延後にValve操作を実行
        if (valveDelayManagers[i].valveState) {
          openValve(i + 1); // ポンプ番号は1-3
        } else {
          // バルブ常時OpenフラグがONの場合、バルブを閉じない
          if (!valveNormallyOpen[i]) {
            closeValve(i + 1);
          }
        }
        valveDelayManagers[i].valveActionPending = false;

        // Valve操作後にモーターの遅延アクションが登録されている場合は実行する
        if (valveDelayManagers[i].motorActionPending) {
          if (valveDelayManagers[i].motorEnable) {
            // モーターを開始する（通常はOPEN_BEFOREで使うが互換性のため）
            digitalWrite(enaPins[i], LOW); // 励磁ON
            remainingSteps[i] = valveDelayManagers[i].remainingSteps;
            motorEnabled[i] = true;
            updatePumpState(i);
          } else {
            // モーターを停止（励磁OFF）する。ただし励磁常時ONフラグがONの場合はOFFしない
            if (!excitationAlwaysOn[i]) {
              digitalWrite(enaPins[i], HIGH); // 励磁OFF（遅延実行）
            }
            // 明示的に motorEnabled を false にして状態を整える
            motorEnabled[i] = false;
            remainingSteps[i] = 0;
            updatePumpState(i);
          }
          valveDelayManagers[i].motorActionPending = false;
        }

        // 遅延処理完了
        stopValveDelay(i);
      }
    }
  }
}

// ===================== EEPROMステップ数管理関数 =====================
// EEPROMから指定モーターの累積ステップ数を読み込む
void loadStepsFromEEPROM(int motorIdx) {
  if (motorIdx < 0 || motorIdx >= 3) return;
  
  unsigned long steps;
  int eepromAddr;
  
  switch (motorIdx) {
    case 0: eepromAddr = EEPROM_ADDR_MOTOR1; break;
    case 1: eepromAddr = EEPROM_ADDR_MOTOR2; break;
    case 2: eepromAddr = EEPROM_ADDR_MOTOR3; break;
    default: return;
  }
  
  eeprom_read_block(&steps, (void*)eepromAddr, sizeof(unsigned long));
  totalSteps[motorIdx] = steps;
}

// EEPROMに指定モーターの累積ステップ数を書き込む
void saveStepsToEEPROM(int motorIdx) {
  if (motorIdx < 0 || motorIdx >= 3) return;
  
  int eepromAddr;
  
  switch (motorIdx) {
    case 0: eepromAddr = EEPROM_ADDR_MOTOR1; break;
    case 1: eepromAddr = EEPROM_ADDR_MOTOR2; break;
    case 2: eepromAddr = EEPROM_ADDR_MOTOR3; break;
    default: return;
  }
  
  eeprom_write_block(&totalSteps[motorIdx], (void*)eepromAddr, sizeof(unsigned long));
}


// 累積ステップ数を回転数に変換（16進数で最大化）
unsigned long stepsToRevolutionsHex(int motorIdx) {
  if (motorIdx < 0 || motorIdx >= 3) return 0;
  
  noInterrupts();
  unsigned long steps = totalSteps[motorIdx];
  interrupts();
  
  return steps / STEPS_PER_REVOLUTION;
}

// ===================== ポンプ状態管理関数 =====================
// ポンプの状態を更新する関数（digitalReadを使わない最適化版）
void updatePumpState(int idx) {
  if (idx < 0 || idx >= 3) return;
  
  bool motorOn = motorEnabled[idx];
  // ENAピンの状態を直接読む代わりに、励磁常時ONフラグとモーター状態から判定
  // 励磁がONの条件：励磁常時ONフラグがON、またはモーターが動作中
  bool enableOn = excitationAlwaysOn[idx] || motorOn;
  
  if (motorOn && enableOn) {
    pumpStates[idx] = PUMP_RUNNING;
  } else if (!motorOn && enableOn) {
    pumpStates[idx] = PUMP_STANDBY;
  } else {
    pumpStates[idx] = PUMP_STOPPED;
  }
}

// ポンプ状態を文字列で取得する関数
const char* getPumpStateString(int idx) {
  if (idx < 0 || idx >= 3) return "INVALID";
  
  switch (pumpStates[idx]) {
    case PUMP_STOPPED: return "STOPPED";
    case PUMP_STANDBY: return "STANDBY";
    case PUMP_RUNNING: return "RUNNING";
    default: return "UNKNOWN";
  }
}

// ===================== 全ポンプ停止関数 =====================
// 3台すべてのポンプを安全に停止（励磁OFF、残ステップ/速度/計画をクリア）
void stopAllPumps() {
  noInterrupts();
  for (int i = 0; i < 3; i++) {
    motorEnabled[i] = false;
    remainingSteps[i] = 0;
    currentSpeedSps[i] = 0.0f;
    planActive[i] = false;
    planStepsDone[i] = 0;
    // ペンディング更新はクリアしておく
    pendingIntervalUpdate[i] = false;
    pendingIntervalUs[i] = 0;
    // STEPピンをLOWに戻す（安全側）
    *stepPorts[i] &= ~stepMasks[i];
  }
  interrupts();
  
  // 励磁とポンプ状態の更新（割り込み外で実行）
  for (int i = 0; i < 3; i++) {
    // 励磁常時ONフラグがOFFの場合のみ励磁をOFFにする
    if (!excitationAlwaysOn[i]) {
      digitalWrite(enaPins[i], HIGH);  // 励磁OFF
    }
    updatePumpState(i);
  }
  
  // 全ポンプ停止時にEEPROMに累積ステップ数を保存
  for (int i = 0; i < 3; i++) {
    saveStepsToEEPROM(i);
  }
  
  // 全ポンプ停止後にバルブを閉じる（ただし、バルブ常時OpenフラグがONのものは除く）
  for (int i = 0; i < 3; i++) {
    if (!valveNormallyOpen[i]) {
      digitalWrite(valvePins[i], LOW);
    }
  }
}

// ===================== バルブ制御関数 =====================
// バルブを開く（ポートON）
void openValve(int valveNumber) {
  if (valveNumber >= 1 && valveNumber <= 3) {
    int idx = valveNumber - 1; // 配列インデックス（0-2）
    digitalWrite(valvePins[idx], HIGH);
    //Serial.print("バルブ");
    //Serial.print(valveNumber);
    //Serial.println("を開きました（ON）");
  } else {
    //Serial.print("無効なバルブ番号: ");
    //Serial.println(valveNumber);
  }
}

// バルブを閉じる（ポートOFF）
void closeValve(int valveNumber) {
  if (valveNumber >= 1 && valveNumber <= 3) {
    int idx = valveNumber - 1; // 配列インデックス（0-2）
    digitalWrite(valvePins[idx], LOW);
    //Serial.print("バルブ");
    //Serial.print(valveNumber);
    //Serial.println("を閉じました（OFF）");
  } else {
    //Serial.print("無効なバルブ番号: ");
    //Serial.println(valveNumber);
  }
}

// 全バルブを閉じる
void closeAllValves() {
  for (int i = 0; i < 3; i++) {
    // バルブ常時OpenフラグがONの場合、バルブを閉じない
    if (!valveNormallyOpen[i]) {
      digitalWrite(valvePins[i], LOW);
    }
  }
  //Serial.println("全バルブを閉じました（OFF）");
}

// バルブの状態を取得
bool getValveState(int valveNumber) {
  if (valveNumber >= 1 && valveNumber <= 3) {
    int idx = valveNumber - 1; // 配列インデックス（0-2）
    return digitalRead(valvePins[idx]) == HIGH;
  }
  return false;
}

// ===================== シリアル送信表示ヘルパー関数 =====================
// 送信データをLCDに表示する関数
void displaySerialSend(const char* description, const byte* data, int length) {
  lcdSetCursor(0, 1);
  lcdPrint("SEND:");
  
  // データが短い場合は16進数で表示
  if (length <= 4) {
    for (int i = 0; i < length; i++) {
      if (i > 0) lcdPrint(" ");
      char hexStr[3];
      sprintf(hexStr, "%02X", data[i]);
      lcdPrint(hexStr);
    }
  } else {
    // 長いデータの場合は説明文を表示
//    lcdPrint(description);
    lcdPrint((const char*)data);
  }
}

// ===================== 漏液検出コマンド送信関数 =====================
// 漏液発生をシリアル通信で通知する関数（10バイト形式）
void sendLeakDetectionCommand() {
  // 漏液検出コマンド: STX + ポンプNo + 'Z' + データ(6桁) + CS + ETX
  byte leakCommand[10];
  leakCommand[0] = 0x02;  // STX
  leakCommand[1] = '0';   // ポンプ番号（漏液は全ポンプ対象なので0）
  leakCommand[2] = 'Z';   // アクション
  leakCommand[3] = '0';   // データ1
  leakCommand[4] = '0';   // データ2
  leakCommand[5] = '0';   // データ3
  leakCommand[6] = '0';   // データ4
  leakCommand[7] = '0';   // データ5
  leakCommand[8] = '0';   // データ6（一時的に0を設定）
  
  // チェックサム計算（1-7バイト目、8バイト目はチェックサム）
  byte checksum = 0;
  for (int i = 1; i <= 7; i++) {
    checksum ^= leakCommand[i];
  }
  leakCommand[8] = checksum;  // チェックサムを8バイト目に設定
  
  leakCommand[9] = 0x03;  // ETX
  
  Serial.write(leakCommand, 10);
  
  // LCD下段に送信データを表示
  displaySerialSend("LEAK", leakCommand, 10);
}

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
  
  //lcdPrint("TEST");
  /*
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
  */
}

// 詳細情報表示（コマンド受信時などに使用）
void lcdShowDetailedInfo() {
  // 1行目：ポンプ状態
  lcdSetCursor(0, 0);
  sprintf(lcdLine1, "P1:%s P2:%s P3:%s",
    getPumpStateString(0),
    getPumpStateString(1),
    getPumpStateString(2));
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
  return digitalRead(leakSensorPins[idx]) == HIGH;
}

// ===================== ステップトグル関数 =====================
// 最適化されたステップ処理（軽量化版）
inline void handleStep(int idx) {
  if (!motorEnabled[idx]) return;
  stepHigh[idx] = !stepHigh[idx];

  if (stepHigh[idx]) {
    *stepPorts[idx] |= stepMasks[idx]; // HIGH
    if (remainingSteps[idx] > 0) {
      remainingSteps[idx]--;
      
      // remainingStepsが1→0になった瞬間（固定ステップ完了）を検出
      if (remainingSteps[idx] == 0) {
        // 次のLOWエッジで停止するためのフラグを設定
        // （無限動作の場合は最初からremainingSteps==0なのでここは通らない）
        fixedStepCompleted[idx] = true;
      }
      
      // 固定回転時：残りステップがわずかになったら減速開始をトリガー
      if (useTrapezoid[idx] && remainingSteps[idx] > 0 && !stopRequested[idx] && !isDecelerating[idx]) {
        // 減速に必要なステップ数を計算（毎ステップ4steps/s減速）
        float currentSpeed = currentSpeedSps[idx];
        if (currentSpeed < minStartSpeedSps) currentSpeed = minStartSpeedSps;
        float decelStepsF = (currentSpeed - minStartSpeedSps) / 4.0f;
        unsigned long decelSteps = (unsigned long)(decelStepsF + 0.5f);
        if (decelSteps < 1) decelSteps = 1;
        
        // 残りステップが減速に必要なステップ数以下になったら減速開始
        if (remainingSteps[idx] <= decelSteps) {
          isDecelerating[idx] = true;
        }
      }
      
      // 残りステップが0になっても、次のLOWエッジまでは動作を継続
      // （motorEnabledはLOWエッジで停止させる）
    }

    // --- 【新仕様】台形加速・減速処理（HIGH時のみ実行） ---
    if (useTrapezoid[idx] && motorEnabled[idx]) {
      // 目標速度を取得（Vコマンドで設定された個別速度、または未設定ならglobalSpeedRpm）
      float targetSpeed = (targetSpeedSps[idx] > 0.0f) ? targetSpeedSps[idx] : rpmToSps(globalSpeedRpm);
      
      // 停止要求がある場合の処理
      if (stopRequested[idx]) {
        // 一定速度維持モードの場合
        if (maintainConstantSpeed[idx]) {
          // 減速開始位置に到達したかチェック
          if (!isDecelerating[idx] && currentRunSteps[idx] >= decelStartStep[idx]) {
            // 減速開始
            isDecelerating[idx] = true;
            maintainConstantSpeed[idx] = false; // 一定速度維持モード終了
          } else {
            // まだ減速開始位置に到達していない場合、現在速度を維持
            // targetSpeedSpsは既にstopCommandSpeedRpmに固定されている
            currentSpeedSps[idx] = targetSpeedSps[idx];
          }
        }
        
        // 減速中の場合：1ステップごとに4 steps/s（steps per second）減速
        if (isDecelerating[idx]) {
          // 現在速度をsteps/sベースで減少させる
          currentSpeedSps[idx] -= 4.0f; // 4 steps/s per step
          if (currentSpeedSps[idx] < minStartSpeedSps) {
            currentSpeedSps[idx] = minStartSpeedSps; // 最小速度650 steps/sで維持
          }
        }
      } else {
        // 固定回転の事前計画がある場合は planActive に従う
        if (planActive[idx]) {
          unsigned long s = planStepsDone[idx];
          unsigned long accelEnd = planAccelSteps[idx];
          unsigned long cruiseEnd = planAccelSteps[idx] + planCruiseSteps[idx];

          // 加速フェーズ
          if (s < accelEnd) {
            // 1ステップごとに4 steps/s加速
            if (currentSpeedSps[idx] < planPeakSpeedSps[idx]) {
              currentSpeedSps[idx] += 4.0f;
              if (currentSpeedSps[idx] > planPeakSpeedSps[idx]) currentSpeedSps[idx] = planPeakSpeedSps[idx];
            }
          }
          // 等速フェーズ
          else if (s < cruiseEnd) {
            currentSpeedSps[idx] = planPeakSpeedSps[idx];
          }
          // 減速フェーズ
          else {
            if (currentSpeedSps[idx] > minStartSpeedSps) {
              currentSpeedSps[idx] -= 4.0f; // 1ステップごとに4 steps/s減速
              if (currentSpeedSps[idx] < minStartSpeedSps) currentSpeedSps[idx] = minStartSpeedSps;
            }
          }
        } else {
          // 【新仕様】通常の加速処理（停止要求がない場合）
          // 目標速度が650steps/s（minStartSpeedSps）以下の場合は加速不要
          if (targetSpeed <= minStartSpeedSps) {
            // 最初から定速（目標速度で動作）
            currentSpeedSps[idx] = targetSpeed;
          } else {
            // 650steps/sから開始して、1ステップごとに4 steps/sずつ加速
            if (currentSpeedSps[idx] < targetSpeed) {
              currentSpeedSps[idx] += 4.0f; // 増分は steps/s
              if (currentSpeedSps[idx] > targetSpeed) currentSpeedSps[idx] = targetSpeed;
            } else {
              currentSpeedSps[idx] = targetSpeed;
            }
          }
        }
      }
      
      // 速度からマイクロ秒単位のステップ間隔に変換
      unsigned int interval = spsToIntervalUs(currentSpeedSps[idx]);
      
      if (interval > 0) {
        pendingIntervalUs[idx] = interval;
        pendingIntervalUpdate[idx] = true;
      }
    }
  } else {
    *stepPorts[idx] &= ~stepMasks[idx]; // LOW
    
    // LOWエッジで累積ステップ数とプラン進捗を更新（1ステップ完了）
    totalSteps[idx]++;  // 永続的な累積ステップ数（回転数表示用）
    currentRunSteps[idx]++;  // 現在の動作での一時カウンター（Sコマンド用）
    
    // 新仕様: 400ステップサイクルカウンタの更新（1〜400の範囲、401→1）
    stepCounter[idx]++;
    if (stepCounter[idx] > 400) {
      stepCounter[idx] = 1;
    }
    
    if (planActive[idx]) { 
      planStepsDone[idx]++; 
    }
    
    // LOWエッジで停止判定を行う（最後のパルスを確実に完了させる）
    if (motorEnabled[idx]) {
      // 停止条件の判定
      bool shouldStop = false;
      
      // 条件1: 固定ステップ数動作の完了（fixedStepCompletedフラグで判定）
      //       remainingStepsが1→0に遷移した時にHIGHエッジでフラグが立つ
      if (fixedStepCompleted[idx]) {
        shouldStop = true;
        fixedStepCompleted[idx] = false; // フラグをクリア
      }
      // 条件2: Sコマンド停止要求がある【新仕様】
      else if (stopRequested[idx]) {
        // 新仕様：stepCounterが800に到達したら停止（400の倍数で確実に停止）
        // stepCounterは1-400の範囲で、800ステップ後は stepCounter が元の値に戻る
        // stepsToStop がカウントダウンされて0になるタイミングで停止
        
        // 停止までの残ステップをカウントダウン
        if (stepsToStop[idx] > 0) {
          stepsToStop[idx]--;
        }
        
        // 停止までのステップ数が0になったら停止
        if (stepsToStop[idx] == 0) {
          shouldStop = true;
        }
      }
      
      if (shouldStop) {
        // モーター停止
        motorEnabled[idx] = false;
        planActive[idx] = false;
        motorStopPending[idx] = true; // loop()で後処理を実行
        // 減速フラグもリセット
        stopRequested[idx] = false;
        isDecelerating[idx] = false;
        maintainConstantSpeed[idx] = false; // 【新仕様】一定速度維持フラグもリセット
      }
    }
    
    // 事前に要求されたインターバル更新を反映（LOW時のみ実行・他モータとの干渉を防止・アトミック化）
    if (pendingIntervalUpdate[idx]) {
      uint8_t sreg = SREG;
      cli();  // 割り込み禁止
      
      if (pendingIntervalUs[idx] > 0) {
        stepInterval[idx] = pendingIntervalUs[idx];
        pendingIntervalUpdate[idx] = false;
      }
      
      SREG = sreg;  // 割り込みレジスタを復元
      
      if (stepInterval[idx] > 0) {
        updateTimerOCR(idx);  // 割り込み禁止で保護された安全な更新
      }
    }
  }
}

// OCRレジスタ更新を最適化した関数（割り込み中断で他モータの干渉を防止）
inline void updateTimerOCR(int idx) {
  uint8_t sreg = SREG; // 割り込みレジスタを保存
  cli();               // 割り込み禁止
  
  uint16_t ocrValue = (uint16_t)((16UL * stepInterval[idx] / 2UL) - 1UL);
  switch (idx) {
    case 0: OCR3A = ocrValue; break;
    case 1: OCR4A = ocrValue; break;
    case 2: OCR5A = ocrValue; break;
  }
  
  SREG = sreg; // 割り込みレジスタを復元
}

// ===================== 台形加速初期化 =====================
// シンプルな台形加速用の初期化
// 毎ステップ4steps/sずつ速度を増やす方式
void initializeTrapezoidArrays() {
  // 配列方式は使わず、毎ステップの速度計算で対応するためここでは何もしない
  // 実際の加速は handleStep() 内で currentSpeedSps を更新することで実現
  precomputedInitialized = true;
}

// 台形加速の有効化（起動時配列を使用）
void enableTrapezoidForMotor(int idx, unsigned long totalSteps) {
  if (idx < 0 || idx >= 3) return;
  if (totalSteps == 0 || totalSteps > MAX_TRAPEZOID_STEPS) {
    usePrecomputed[idx] = false;
    return;
  }
  
  // 事前計算配列が初期化されているかチェック
  if (!precomputedInitialized) {
    usePrecomputed[idx] = false;
    return;
  }
  
  // 起動時配列を使用
  usePrecomputed[idx] = true;
  precomputedIndex[idx] = 0;
  
  // 計画情報を更新（planActiveが既に設定されている場合は上書きしない）
  if (!planActive[idx]) {
    planActive[idx] = true;
    planTotalSteps[idx] = totalSteps;
    planStepsDone[idx] = 0;
  }
}

// 事前計算配列をリセットする関数
void resetPrecomputedArray(int idx) {
  if (idx < 0 || idx >= 3) return;
  
  usePrecomputed[idx] = false;
  precomputedStepCount[idx] = 0;
  precomputedIndex[idx] = 0;
}

// 台形加減速処理を分離（制御精度を保持した軽量化版）
inline void updateTrapezoidSpeed(int idx) {
  // 初回動作時の整合性チェック（早期リターンで処理軽減）
  if (currentSpeedSps[idx] < 1.0f) {
    currentSpeedSps[idx] = minStartSpeedSps;
  }
  
  // 目標速度が設定されていない場合の安全対策
  if (targetSpeedSps[idx] < 1.0f) {
    targetSpeedSps[idx] = rpmToSps(globalSpeedRpm);
  }

  // 浮動小数点演算を使用（制御精度を保持）
  float accel = accelerationSps2[idx];
  if (accel < 1.0f) accel = 1.0f;

  // 半周期の時間 [s] - キャッシュして計算回数を削減
  float dt = (float)stepInterval[idx] * 0.0000005f; // 1/2000000.0f を事前計算

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

  // 次周期用のインターバルを更新（変更があった場合のみ・アトミック化）
  unsigned int newInterval = spsToIntervalUs(currentSpeedSps[idx]);
  if (newInterval > 0 && newInterval != stepInterval[idx]) {
    // アトミック化：割り込み禁止で変数を更新
    uint8_t sreg = SREG;
    cli();  // 割り込み禁止
    
    pendingIntervalUs[idx] = newInterval;
    pendingIntervalUpdate[idx] = true;
    
    SREG = sreg;  // 割り込みレジスタを復元
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
  
}

// RPM計算用の関数（整数型に変更）
int calculateRPM(int idx) {
  if (idx < 0 || idx >= 3) return 0;
  
  // 現在の時間を取得
  unsigned long currentTime = millis();
  
  // 最後の割り込みから3秒以上経過している場合は0を返す
  if (lastInterruptTimeMs[idx] > 0 && (currentTime - lastInterruptTimeMs[idx]) > RPM_TIMEOUT_MS) {
    return 0;
  }
  
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
  //      Serial.print(calculateRPM(0));
  //      Serial.println();
    }
  }

  // Valve遅延処理（毎ミリ秒実行）
  processValveDelays();

  // 漏液センサ動作チェック（100msごとに実行）
  if (msCounter % 100 == 0) {
    bool leakOn = isLeakDetected(0);
    setDebugLED(leakOn);
    
    if (!leakDetected) {
      // 漏液検知状態でない場合のみ、新しい漏液を検知
      if (leakOn) {
        if (leakConsecutiveOnCount < 255) leakConsecutiveOnCount++;
        if (leakConsecutiveOnCount >= 5) {
          leakStopRequested = true; // 500ms間連続でON → 停止要求
        }
      } else {
        leakConsecutiveOnCount = 0;
      }
    } else {
      // 漏液検知状態の場合は、復帰条件をチェック
      if (leakOn) {
        leakConsecutiveOffCount = 0; // 漏液が続いている場合はリセット
      } else {
        if (leakConsecutiveOffCount < 255) leakConsecutiveOffCount++;
      }
    }
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

  // 緊急停止（全ポンプ停止）はポンプ番号検証より先に処理
  char action = cmd[2];
  if (action == 'Z') {  // 緊急停止
    stopAllPumps();
    lcdClear();
    lcdPrint("Emergency Stop");
    return;
  }

  int pumpNo = cmd[1] - '0';
  if (pumpNo < 1 || pumpNo > 3) return;
  int idx = pumpNo - 1;

  char numStr[7];
  memcpy(numStr, &cmd[3], 6);
  numStr[6] = '\0';
  long value = atol(numStr);

  if (action == 'M') {  // モータ開始 (0=無限動作)
    // モーターが既に動作中、停止処理待ち、またはバルブ遅延管理でモーター開始待ちの場合はMコマンドを無視
    if (motorEnabled[idx] || motorStopPending[idx] || valveDelayManagers[idx].active) {
      // LCD表示
      lcdClear();
      lcdPrint("Already Running");
      return;
    }
    
    // 前回の動作からのフラグをリセット
    stopRequested[idx] = false;
    isDecelerating[idx] = false;
    fixedStepCompleted[idx] = false;  // 固定ステップ完了フラグもリセット
    currentRunSteps[idx] = 0;  // 現在の動作での一時カウンターをリセット
    
    // 【新仕様】400ステップサイクルカウンタを0にリセット（動作開始時）
    stepCounter[idx] = 0;
    maintainConstantSpeed[idx] = false; // 一定速度維持フラグもリセット
    stepsToStop[idx] = 0; // 停止までのステップ数もリセット
    
    // 注意：totalStepsは累積ステップ数なのでリセットしない（EEPROMに保存される永続値）
    
    // 台形加減速の事前計画を設定（遅延処理とモーター即座開始の両方で使用）
    if (useTrapezoid[idx]) {
      // ステップ数指定時は台形/三角プロファイルを事前計画
      if (value > 0 && targetSpeedSps[idx] > 0.0f) {
        float a = accelerationSps2[idx];
        if (a < 1.0f) a = 1.0f;
        float v0 = minStartSpeedSps;
        float vend = minStartSpeedSps; // 終端は最小開始速度まで落とす想定
        float vtar = targetSpeedSps[idx];

        float accelStepsF = 0.0f;
        float decelStepsF = 0.0f;
        if (vtar > v0)  accelStepsF = (vtar*vtar - v0*v0) / (2.0f * a);
        if (vtar > vend) decelStepsF = (vtar*vtar - vend*vend) / (2.0f * a);

        unsigned long accelStepsUL = (unsigned long)(accelStepsF + 0.5f);
        unsigned long decelStepsUL = (unsigned long)(decelStepsF + 0.5f);
        unsigned long total = value * 2; // 受信したステップ数の2倍で動作

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
      planActive[idx] = false;
      planStepsDone[idx] = 0;
    }
    
    // バルブ常時OpenフラグがONの場合、すでにバルブは開いているので遅延管理は不要
    if (valveNormallyOpen[idx]) {
      // モーターを即座に開始
      digitalWrite(enaPins[idx], LOW); // 励磁ON
      remainingSteps[idx] = (value > 0) ? value * 2 : 0; // 受信したステップ数の2倍で動作
      motorEnabled[idx] = true;
      // 動作開始時に減速開始タイミングを計算（固定回転用）
      if (planActive[idx]) {
        decelStartStep[idx] = currentRunSteps[idx] + planAccelSteps[idx] + planCruiseSteps[idx];
      }
      updatePumpState(idx);
      
      // 台形加減速設定
      if (useTrapezoid[idx]) {
        // 起動時に必ず目標速度・初速・加速度を再計算して上書き（停止後再開時の低速化対策）
        trapezoidCalcCounter[idx] = 0;
        // 目標速度はグローバル速度を基準に再計算（ローカルVコマンドの上書きを避けたい場合は別途フラグ化可能）
        targetSpeedSps[idx] = rpmToSps(globalSpeedRpm);

        // 開始速度の決定
        if (targetSpeedSps[idx] <= minStartSpeedSps) {
          currentSpeedSps[idx] = targetSpeedSps[idx];
        } else {
          currentSpeedSps[idx] = minStartSpeedSps; // 650 steps/s
        }

        // 加速度の再計算（0.2秒で到達する設計）
        if (targetSpeedSps[idx] > currentSpeedSps[idx]) {
          float dv = targetSpeedSps[idx] - currentSpeedSps[idx];
          accelerationSps2[idx] = dv / targetRampTimeSec;
          if (accelerationSps2[idx] < 1.0f) accelerationSps2[idx] = 1.0f;
        }
        
        // 事前計算配列は使用しない（新仕様では1ステップ4rpm加速を使用）
        usePrecomputed[idx] = false;
        precomputedIndex[idx] = 0;
        
        stepInterval[idx] = spsToIntervalUs(currentSpeedSps[idx]);
        switch(idx) {
          case 0: setupTimer3(stepInterval[0]); break;
          case 1: setupTimer4(stepInterval[1]); break;
          case 2: setupTimer5(stepInterval[2]); break;
        }
      } else {
        switch(idx) {
          case 0: setupTimer3(stepInterval[0]); break;
          case 1: setupTimer4(stepInterval[1]); break;
          case 2: setupTimer5(stepInterval[2]); break;
        }
      }
    } else {
      // 非同期Valve遅延管理を開始（Valve開放 → 0.5秒後 → モーター開始）
      startValveDelay(idx, VALVE_DELAY_OPEN_BEFORE, true, true, (value > 0) ? value * 2 : 0);
    }
    
    // LCD表示（開始速度と目標速度を表示）
    lcdClear();
    if (useTrapezoid[idx]) {
      // 台形加速モードの場合：開始速度と目標速度を表示
      // 目標速度を取得
      float targetSps = (targetSpeedSps[idx] > 0.0f) ? targetSpeedSps[idx] : rpmToSps(globalSpeedRpm);
      
      // 開始速度を計算（Mコマンド処理と同じロジック）
      float startSps;
      if (targetSps <= minStartSpeedSps) {
        startSps = targetSps;  // 目標速度が650steps/s以下なら目標速度で開始
      } else {
        startSps = minStartSpeedSps;  // 650steps/sから開始
      }
      
      int startRpm = (int)((startSps * 60.0f) / (float)stepsPerRev + 0.5f);
      int targetRpm = (int)((targetSps * 60.0f) / (float)stepsPerRev + 0.5f);
      
      char line1[17];
      sprintf(line1, "M%d Start", idx + 1);
      lcdPrint(line1);
      lcdSetCursor(0, 1);
      char line2[17];
      sprintf(line2, "S:%d T:%d", startRpm, targetRpm);
      lcdPrint(line2);
    } else {
      // 通常モードの場合
      lcdPrint("Start");
    }
  } else if (action == 'S') {  // 停止
    // 【新仕様】停止コマンド受信時の減速処理
    // 1. stepCounter(1-400)と現在速度(rpm)を読み取る
    // 2. "減速に必要なステップ数" = (現在速度rpm - 650) / 4 + 1 (整数演算)
    // 3. "停止までのステップ数" = 800 - stepCounter
    // 4. "停止までのステップ数" - "減速に必要なステップ数" の間は現在速度で一定速度動作（加速を打ち切り）
    // 5. 両者が等しくなったら減速開始、1ステップごとに4rpm減速
    
    // モーターが動作中の場合
    if (motorEnabled[idx]) {
      noInterrupts();
      unsigned int currentStepCount = stepCounter[idx];  // 1-400の範囲のカウンタ
      float currentSpeedSps_local = currentSpeedSps[idx]; // 現在速度 steps/s
      interrupts();
      
  // 現在速度は steps/s ベースで取得済み（currentSpeedSps_local）
  // 必要に応じてrpm換算も取得するが、減速計算は steps/s ベースで行う
  long currentSpeedRpm = (long)((currentSpeedSps_local * 60.0f) / (float)stepsPerRev + 0.5f);
      
      // "停止までのステップ数" = 800 - stepCounter
      long stepsToStopVal = 800 - currentStepCount;
      if (stepsToStopVal < 0) stepsToStopVal = 0; // 安全対策
      
  // 【減速不要処理】現在速度が650 steps/s 以下または非常に近い場合
  if (currentSpeedSps_local <= (minStartSpeedSps + 5.0f)) {  // 650 steps/s + 安全マージン
        // 減速不要：現在速度のまま停止位置まで進んで停止
        stopRequested[idx] = true;
        decelStepsRequired[idx] = 0; // 減速ステップ数は0
        stepsToStop[idx] = (unsigned long)stepsToStopVal;
        stopCommandSpeedRpm[idx] = (float)currentSpeedRpm;
        
        // 減速開始位置 = 停止位置（減速せずに停止）
        noInterrupts();
        unsigned long currentRun = currentRunSteps[idx];
        interrupts();
        decelStartStep[idx] = currentRun + (unsigned long)stepsToStopVal;
        
        // 一定速度維持モード（現在速度で停止位置まで）
        maintainConstantSpeed[idx] = true;
        targetSpeedSps[idx] = currentSpeedSps_local;
        isDecelerating[idx] = false; // 減速しない
      } else {
  // 【通常の減速処理】現在速度が650 steps/sより高い場合
  // "減速に必要なステップ数" = ceil((現在速度_steps/s - 650_steps/s) / 4_steps/s_per_step)
  float diff = currentSpeedSps_local - minStartSpeedSps;
  long decelSteps = (long)ceilf(diff / 4.0f);
  if (decelSteps < 1) decelSteps = 1;
        
        // 停止要求フラグと減速パラメータを設定
        stopRequested[idx] = true;
        decelStepsRequired[idx] = (unsigned long)decelSteps;
        stepsToStop[idx] = (unsigned long)stepsToStopVal;
        stopCommandSpeedRpm[idx] = (float)currentSpeedRpm;
        
        // 減速開始位置を計算：現在の currentRunSteps + (停止までのステップ数 - 減速に必要なステップ数)
        long stepsUntilDecel = stepsToStopVal - decelSteps;
        if (stepsUntilDecel < 0) stepsUntilDecel = 0;
        
        noInterrupts();
        unsigned long currentRun = currentRunSteps[idx];
        interrupts();
        
        decelStartStep[idx] = currentRun + (unsigned long)stepsUntilDecel;
        
        // 加速を打ち切り、現在速度で一定速度維持モードに移行
        maintainConstantSpeed[idx] = true;
        targetSpeedSps[idx] = currentSpeedSps_local; // 目標速度を現在速度に固定
        
        // 減速はまだ開始しない（handleStep内で decelStartStep に到達したら開始）
        isDecelerating[idx] = false;
      }
      
      // LCD表示
      lcdClear();
      lcdPrint("Stop");
    } else {
      // モーターが動作していない場合
      lcdClear();
      lcdPrint("Already Stopped");
    }
  } else if (action == 'F') {  // 正転
    digitalWrite(dirPins[idx], LOW);
    // LCD表示
    lcdClear();
    lcdPrint("Receive Forward");
  } else if (action == 'R') {  // 逆転
    digitalWrite(dirPins[idx], HIGH);
    // LCD表示
    lcdClear();
    lcdPrint("Receive Reverse");
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
      // LCD表示
      lcdClear();
      lcdPrint("Receive Speed");
    }
  } else if (action == 'E') {  // Enable ON
    digitalWrite(enaPins[idx], LOW);
    updatePumpState(idx); // ポンプ状態を更新
    // LCD表示
    lcdClear();
    lcdPrint("Receive EnableON");
  } else if (action == 'D') {  // Enable OFF
    // 励磁常時ONフラグがOFFの場合のみ励磁をOFFにする
    if (!excitationAlwaysOn[idx]) {
      digitalWrite(enaPins[idx], HIGH);
    }
    updatePumpState(idx); // ポンプ状態を更新
    
    // バルブ常時OpenフラグがONの場合、バルブを閉じない
    if (!valveNormallyOpen[idx]) {
      // 非同期Valve遅延管理を開始（Enable OFF → 0.5秒後 → Valve閉鎖）
      startValveDelay(idx, VALVE_DELAY_CLOSE_AFTER, false, false, 0);
    }
    
    // LCD表示
    lcdClear();
    lcdPrint("ReceiveEnableOFF");
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
      usePrecomputed[idx] = false; // 事前計算配列を無効化
    } else {
      // 台形加速ON時：事前計算配列は使用せず、動的な事前計画のみを使用
      // （Mコマンドで事前計画が設定される）
      usePrecomputed[idx] = false;
    }
    // LCD表示
    lcdClear();
    lcdPrint("ReceiveTrapezoid");
  } else if (action == 'B') {  // バルブ常時Open設定（000000:OFF, 000001:ON）
    if (value == 1) {
      // バルブ常時OpenフラグをONに設定し、ただちにバルブをOPENする
      valveNormallyOpen[idx] = true;
      openValve(pumpNo);
      // LCD表示
      lcdClear();
      lcdPrint("Valve Normally Open ON");
    } else if (value == 0) {
      // バルブ常時OpenフラグをOFFに設定
      valveNormallyOpen[idx] = false;
      // モーターが停止中の場合、バルブを閉じる
      if (!motorEnabled[idx]) {
        closeValve(pumpNo);
      }
      // LCD表示
      lcdClear();
      lcdPrint("Valve Normally Open OFF");
    }
  } else if (action == 'L') {  // 励磁常時ON設定（000000:OFF, 000001:ON）
    if (value == 1) {
      // 励磁常時ONフラグをONに設定し、ただちに励磁をONする
      excitationAlwaysOn[idx] = true;
      digitalWrite(enaPins[idx], LOW);  // 励磁ON
      updatePumpState(idx);
      // LCD表示
      lcdClear();
      lcdPrint("Excitation Always ON");
    } else if (value == 0) {
      // 励磁常時ONフラグをOFFに設定
      excitationAlwaysOn[idx] = false;
      // モーターが停止中の場合、励磁をOFFにする
      if (!motorEnabled[idx]) {
        digitalWrite(enaPins[idx], HIGH);  // 励磁OFF
        updatePumpState(idx);
      }
      // LCD表示
      lcdClear();
      lcdPrint("Excitation Always OFF");
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
    
    // チェックサム計算（1-7バイト目: ポンプ番号1バイト + 電流値6バイト）
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCD表示
    lcdClear();
    lcdPrint("Receive Current ");
    displaySerialSend("CURRENT", response, 10);
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
    
    // チェックサム計算（1-7バイト目: ポンプ番号1バイト + RPM6バイト）
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    response[10] = 0x00;  // null
    // 応答を送信
    Serial.write(response, 10);
    
    // LCD表示
    lcdClear();
    lcdPrint("Receive Rotate X");
    lcdSetCursor(0, 1);
    lcdPrint("SEND: RPM=");
    lcdPrint(rpm);
  } else if (action == 'o') {  // バルブ開く
    openValve(pumpNo);
    // LCD表示
    lcdClear();
    lcdPrint("Valve Open");
  } else if (action == 'q') {  // バルブ閉じる
    closeValve(pumpNo);
    // LCD表示
    lcdClear();
    lcdPrint("Valve Close");
  } else if (action == 'Q') {  // 全バルブ閉じる
    closeAllValves();
    // LCD表示
    lcdClear();
    lcdPrint("All Valves Close");
  } else if (action == 'G') {  // バルブ状態取得
    bool valveState = getValveState(pumpNo);
    // STX + ポンプNo + 状態(1桁: 0=Close, 1=Open) + データ(5桁) + CS + ETX の形式で送信
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = pumpNo + '0';  // ポンプ番号
    response[2] = valveState ? '1' : '0';  // バルブ状態
    response[3] = '0';  // データ1
    response[4] = '0';  // データ2
    response[5] = '0';  // データ3
    response[6] = '0';  // データ4
    response[7] = '0';  // データ5
    
    // チェックサム計算（1-7バイト目）
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCD表示
    lcdClear();
    lcdPrint("Valve Status");
    displaySerialSend("VALVE", response, 10);
  } else if (action == 'W') {  // グローバル速度設定（全モータ共通、停止中のみ）
    // すべてのモータが停止中かチェック
    bool anyMotorRunning = false;
    for (int i = 0; i < 3; i++) {
      if (motorEnabled[i] || motorStopPending[i] || valveDelayManagers[i].active) {
        anyMotorRunning = true;
        break;
      }
    }
    
    if (anyMotorRunning) {
      // どれかのモータが動作中または停止処理中の場合はGコマンドを無視
      lcdClear();
      lcdPrint("Motor Running");
      lcdSetCursor(0, 1);
      lcdPrint("G cmd ignored");
    } else if (value > 0) {
      // 最大速度300rpmでリミット
      long newSpeed = value;
      if (newSpeed > 300) {
        newSpeed = 300;
      }
      
      // グローバル速度を更新
      globalSpeedRpm = newSpeed;
      
      // グローバル速度が変更されたため、加速配列を再初期化
      precomputedInitialized = false;
      initializeTrapezoidArrays();
      
      // 全モータの目標速度を更新
      for (int i = 0; i < 3; i++) {
        if (useTrapezoid[i]) {
          targetSpeedSps[i] = rpmToSps(globalSpeedRpm);
          // 加速度も更新
          float base = (currentSpeedSps[i] > 1.0f) ? currentSpeedSps[i] : minStartSpeedSps;
          if (targetSpeedSps[i] > base) {
            float dv = targetSpeedSps[i] - base;
            accelerationSps2[i] = dv / targetRampTimeSec;
            if (accelerationSps2[i] < 1.0f) accelerationSps2[i] = 1.0f;
          }
        } else {
          unsigned int newInterval = rpmToIntervalUs(globalSpeedRpm);
          stepInterval[i] = newInterval;
          targetSpeedSps[i] = rpmToSps(globalSpeedRpm);
        }
      }
      
      // LCD表示
      lcdClear();
      lcdPrint("Global Speed");
      lcdSetCursor(0, 1);
      char speedStr[17];
      sprintf(speedStr, "Set: %ld RPM", globalSpeedRpm);
      lcdPrint(speedStr);
    }
  } else if (action == 'T') {  // 累積回転数取得（16進数）
    // STX + ポンプNo + 回転数(6桁16進数) + CS + ETX の形式で送信
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = pumpNo + '0';  // ポンプ番号
    
    // 累積ステップ数を回転数に変換（16進数で最大化）
    unsigned long revolutions = stepsToRevolutionsHex(pumpNo - 1);
    
    // 6桁16進数で整形（FFFFFFまで表現可能 = 16,777,215回転）
    char hexStr[7];
    sprintf(hexStr, "%06lX", revolutions); // 6桁固定で左側を0埋め、大文字16進数
    
    // 回転数データをコピー
    for (int i = 0; i < 6; i++) {
      response[2 + i] = hexStr[i];
    }
    
    // チェックサム計算（1-7バイト目: ポンプ番号1バイト + 回転数6バイト）
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCD表示
    lcdClear();
    lcdPrint("Total Revolutions");
    lcdSetCursor(0, 1);
    lcdPrint("HEX: ");
    lcdPrint(hexStr);
    displaySerialSend("TOTAL", response, 10);
  } else if (action == 'J') {  // 制御状態取得（全ポンプ）
    // 全ポンプの状態を返すため、ポンプ番号は無視
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = '1';   // ポンプ番号（形式上必要だが、無視される）
    
    // バルブ常時Open状態をビットフィールドで表現
    // bit 0 (LSB): ポンプ1, bit 1: ポンプ2, bit 2: ポンプ3
    byte valveBits = 0;
    for (int i = 0; i < 3; i++) {
      if (valveNormallyOpen[i]) {
        valveBits |= (1 << i);
      }
    }
    response[2] = '0' + valveBits;
    
    // 励磁常時ON状態をビットフィールドで表現
    byte excitationBits = 0;
    for (int i = 0; i < 3; i++) {
      if (excitationAlwaysOn[i]) {
        excitationBits |= (1 << i);
      }
    }
    response[3] = '0' + excitationBits;
    
    // 台形加速状態をビットフィールドで表現
    byte trapezoidBits = 0;
    for (int i = 0; i < 3; i++) {
      if (useTrapezoid[i]) {
        trapezoidBits |= (1 << i);
      }
    }
    response[4] = '0' + trapezoidBits;
    
    // 未使用部分
    response[5] = '0';
    response[6] = '0';
    response[7] = '0';
    
    // チェックサム計算（1-7バイト目）
    byte checksum = 0;
    for (int i = 1; i <= 7; i++) {
      checksum ^= response[i];
    }
    response[8] = checksum;
    
    response[9] = 0x03;  // ETX
    
    // 応答を送信
    Serial.write(response, 10);
    
    // LCD表示
    lcdClear();
    lcdPrint("Control Status");
    displaySerialSend("STATUS", response, 10);
  }
}

// ===================== SETUP =====================
void setup() {
  for (int i = 0; i < 3; i++) {
    pinMode(stepPins[i], OUTPUT);
    pinMode(dirPins[i], OUTPUT);
    pinMode(enaPins[i], OUTPUT);
    digitalWrite(enaPins[i], HIGH);  // 励磁OFF（初期状態）
    digitalWrite(dirPins[i], LOW);

    // ポートとビットマスクを計算
    uint8_t pin = stepPins[i];
    stepPorts[i] = portOutputRegister(digitalPinToPort(pin));
    stepMasks[i] = digitalPinToBitMask(pin);

    // 初期速度 = globalSpeedRpm（デフォルト200rpm）
    stepInterval[i] = rpmToIntervalUs(globalSpeedRpm);
    targetSpeedSps[i] = rpmToSps(globalSpeedRpm);
  }

  // 漏液センサピン設定
  for (int i = 0; i < 3; i++) {
    pinMode(leakSensorPins[i], INPUT_PULLUP);
  }

  // バルブ制御ピン設定
  for (int i = 0; i < 3; i++) {
    pinMode(valvePins[i], OUTPUT);
    // バルブ常時OpenフラグがONの場合、バルブをOPENする
    if (valveNormallyOpen[i]) {
      digitalWrite(valvePins[i], HIGH); // Open（ON）
    } else {
      digitalWrite(valvePins[i], LOW); // Close（OFF）
    }
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
  
  // 台形加速配列の初期化（起動時に1回だけ）
  initializeTrapezoidArrays();
  
  // EEPROMから累積ステップ数を読み込み
  for (int i = 0; i < 3; i++) {
    loadStepsFromEEPROM(i);
  }
  
  // 初期ポンプ状態を設定
  for (int i = 0; i < 3; i++) {
    updatePumpState(i);
  }

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
/*  
  //Test Valve - 1秒おきにバルブ1を開閉
  static unsigned long lastValveToggle = 0;
  if (millis() - lastValveToggle >= 1000) {
    lastValveToggle = millis();
    if (getValveState(1)){
      closeValve(1);
    } else {
      openValve(1);
    }
  }
*/
  // LCD表示更新
  lcdUpdateDisplay();

  // 漏液による全停止要求を処理（メインループ側で安全に停止）
  if (leakStopRequested) {
    leakStopRequested = false;
    leakDetected = true;
    leakDetectionTime = millis();
    stopAllPumps();
    // 必要ならLCDやシリアル通知を追加可能
    lcdClear();
    lcdPrint("LEAK STOP");
    
    // 漏液発生コマンドをシリアル送信
    sendLeakDetectionCommand();
  }
  
  // 漏液検知状態の自動復帰処理
  if (leakDetected) {
    unsigned long currentTime = millis();
    
    // 5秒経過したかチェック
    if (currentTime - leakDetectionTime >= LEAK_RECOVERY_TIME_MS) {
      // 5秒間連続して漏液していない場合、自動復帰
      if (leakConsecutiveOffCount >= 50) { // 5秒 = 50回 × 100ms
        leakDetected = false;
        leakConsecutiveOffCount = 0;
        lcdClear();
        lcdPrint("LEAK RECOVERED");
        lcdSetCursor(0, 1);
        lcdPrint("System Ready");
      }
    }
  }
  
  // モーター停止処理（割り込み外で実行）
  for (int i = 0; i < 3; i++) {
    if (motorStopPending[i]) {
      motorStopPending[i] = false;
      // 停止時にEEPROMに累積ステップ数を保存
      saveStepsToEEPROM(i);

      // 励磁OFFはすぐに行わず、0.5秒後に行う（バルブ閉鎖と同様の遅延処理を流用）
      // valveState: バルブは常時Openの場合は閉じない（falseだと閉じる）
      bool valveShouldClose = !valveNormallyOpen[i];

      // motorEnable=false: 0.5秒後にモーター停止（励磁OFF）を実行
      startValveDelay(i, VALVE_DELAY_CLOSE_AFTER, valveShouldClose, false, 0);

      // ポンプ状態は遅延処理後に updatePumpState が行われるが、ここでも一時的に更新
      updatePumpState(i);
    }
  }
}
