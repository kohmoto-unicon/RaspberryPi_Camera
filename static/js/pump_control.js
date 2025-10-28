// コマンドバイトを16進数とASCII文字の混合形式でフォーマット
function formatCommandBytes(bytes, pump) {
  // ポンプ番号に応じてポート名を決定
  let portName;
  if (1 <= pump && pump <= 3) {
    portName = 'ACM0';
  } else if (4 <= pump && pump <= 6) {
    portName = 'ACM1';
  } else {
    portName = 'UNKNOWN';
  }
  
  let result = [portName + '→'];
  for (let i = 0; i < bytes.length; i++) {
    if (i === 0) {
      // STX (0x02)
      result.push('STX');
    } else if (i === 10) {
      // ETX (0x03)
      result.push('ETX');
    } else if (i === 9) {
      // チェックサムは16進数で表示
      result.push('0x' + bytes[i].toString(16).padStart(2, '0').toUpperCase());
    } else {
      // その他はASCII文字で表示（シングルクォートなし）
      if (bytes[i] >= 32 && bytes[i] <= 126) {
        result.push(String.fromCharCode(bytes[i]));
      } else {
        result.push('0x' + bytes[i].toString(16).padStart(2, '0').toUpperCase());
      }
    }
  }
  return result.join(' ');
}

// スイッチの状態をローカルストレージに保存
function saveSwitchState(pump, switchType, state) {
  const key = `pump_${pump}_${switchType}`;
  localStorage.setItem(key, state.toString());
  console.log(`スイッチ状態を保存: ${key} = ${state}`);
}

// スイッチの状態をローカルストレージから取得
function getSwitchState(pump, switchType, defaultValue = false) {
  const key = `pump_${pump}_${switchType}`;
  const saved = localStorage.getItem(key);
  const state = saved !== null ? saved === 'true' : defaultValue;
  console.log(`スイッチ状態を取得: ${key} = ${state}`);
  return state;
}

// 弁制御
function toggleValve(pump, isOpen){
  const val = isOpen ? '1' : '0';
  document.getElementById('valveLabel' + pump).innerText = isOpen ? 'ON' : 'OFF';
  
  // 状態をローカルストレージに保存
  saveSwitchState(pump, 'valve', isOpen);
  
  sendPumpCommand(pump, 'B', val);
}

// 励磁常時ON制御
function toggleExcitation(pump, isOn){
  const val = isOn ? '000001' : '000000';
  document.getElementById('excitationLabel' + pump).innerText = isOn ? 'ON' : 'OFF';
  
  // 状態をローカルストレージに保存
  saveSwitchState(pump, 'excitation', isOn);
  
  sendPumpCommand(pump, 'L', val);
}

// 方向切替
function toggleDirection(pump, isReverse){
  const dir = isReverse ? 'R' : 'F';
  document.getElementById('dirLabel' + pump).innerText = isReverse ? '逆転' : '正転';
  
  // 状態をローカルストレージに保存
  saveSwitchState(pump, 'direction', isReverse);
  
  sendPumpCommand(pump, dir);
}

// 台形加速切替
function toggleAccel(pump, isOn){
  const val = isOn ? '1' : '0';
  document.getElementById('accelLabel' + pump).innerText = isOn ? 'ON' : 'OFF';
  
  // 状態をローカルストレージに保存
  saveSwitchState(pump, 'acceleration', isOn);
  
  sendPumpCommand(pump, 'A', val);
}

// ステップ送信
function sendSteps(pump){
  const stepsElement = document.getElementById('steps' + pump);
  let steps;
  
  // Choices.jsが初期化されている場合
  if (stepsElement.choices) {
    const choiceValue = stepsElement.choices.getValue();
    steps = choiceValue ? choiceValue.value : '';
  } else {
    // 通常のselect要素の場合
    steps = stepsElement.value;
  }
  
  // 未選択または空の場合を先にチェック
  if (!steps || steps === '' || steps === null || steps === undefined) {
    console.log(`ポンプ${pump}: ステップ数未選択のため000000を送信します。`);
    steps = '000000';
    sendPumpCommand(pump, 'M', steps);
    return;
  }
  
  // 値の検証：数字として有効かチェック
  const stepsNum = parseInt(steps, 10);
  if (isNaN(stepsNum) || stepsNum < 0) {
    // 無効な値の場合は000000として送信
    console.log(`ポンプ${pump}: 無効な値 "${steps}" を検出。000000を送信します。`);
    steps = '000000';
  } else {
    // 有効な値の場合はそのまま使用
    steps = stepsNum.toString();
  }
  
  sendPumpCommand(pump, 'M', steps);
}

// 停止
function sendStop(pump){
  sendPumpCommand(pump, 'S');
}

// グローバル速度設定（全モータ共通）
async function setGlobalRPM(pump){
  const rpmElement = document.getElementById('rpmSetting' + pump);
  let rpm;
  
  // Choices.jsが初期化されている場合
  if (rpmElement.choices) {
    const choiceValue = rpmElement.choices.getValue();
    rpm = choiceValue ? choiceValue.value : '';
  } else {
    // 通常のselect要素の場合
    rpm = rpmElement.value;
  }
  
  // 未選択または空の場合
  if (!rpm || rpm === '' || rpm === null || rpm === undefined) {
    console.log('RPMを選択してください');
    isRpmSettingInProgress = false;
    return;
  }
  
  // 値の検証：数字として有効かチェック
  const rpmNum = parseInt(rpm, 10);
  if (isNaN(rpmNum) || rpmNum < 50 || rpmNum > 300) {
    console.log('有効なRPM値を選択してください（50～300）');
    isRpmSettingInProgress = false;
    return;
  }
  
  try {
    // 'W'コマンドで送信（全モータ共通速度設定）
    console.log(`グローバル速度設定: ${rpmNum} RPM`);
    await sendPumpCommand(pump, 'W', rpmNum.toString());
    
    // 設定成功後、同じグループの他のポンプのRPM選択も同じ値に同期
    // （ポンプ1～3は互いに同期、ポンプ4～6も互いに同期）
    syncRPMSettings(pump, rpm);
  } finally {
    // 処理完了後、フラグをリセット（500ms待機してから、通信安定化を待つ）
    setTimeout(() => {
      isRpmSettingInProgress = false;
      console.log('RPM設定処理完了、通信再開を許可しました');
    }, 500);
  }
}

// RPMセレクト操作開始時（マウスダウン時）にフラグを立てる
function startRpmSetting() {
  isRpmSettingInProgress = true;
  console.log('RPM操作開始、漏液チェックをスキップします');
}

// RPM設定を他のポンプと同期する関数
function syncRPMSettings(sourcePump, rpmValue) {
  console.log(`RPM設定を同期中: ポンプ${sourcePump}から他のポンプへ ${rpmValue} RPM`);
  
  // ポンプ1～3と4～6をそれぞれ同期
  let startPump, endPump;
  if (sourcePump >= 1 && sourcePump <= 3) {
    startPump = 1;
    endPump = 3;
  } else if (sourcePump >= 4 && sourcePump <= 6) {
    startPump = 4;
    endPump = 6;
  } else {
    return; // 範囲外の場合は何もしない
  }
  
  for (let targetPump = startPump; targetPump <= endPump; targetPump++) {
    if (targetPump === sourcePump) {
      continue; // 送信元ポンプはスキップ
    }
    
    const targetElement = document.getElementById('rpmSetting' + targetPump);
    if (targetElement && targetElement.choices) {
      // Choices.jsのsetChoiceByValueメソッドで値を設定
      targetElement.choices.setChoiceByValue(rpmValue);
      console.log(`ポンプ${targetPump}のRPM設定を ${rpmValue} RPM に同期しました`);
    }
  }
}

// RPM取得
async function getRPM(pump){
  console.log(`[DEBUG] getRPM呼び出し: ポンプ${pump}, isAutoSending=${isAutoSending}`);
  
  if (isAutoSending) {
    console.log('自動送信中のため、手動RPM取得をスキップします');
    alert('自動送信中です。しばらくお待ちください。');
    return;
  }
  
  try {
    console.log(`[DEBUG] getRPM呼び出し: ポンプ${pump}`);
    const response = await fetch(`/api/get_rpm?pump=${pump}`);
    const data = await response.json();
    
    console.log(`[DEBUG] getRPM レスポンス:`, data);
    
    const rpmDisplay = document.getElementById('rpmValue' + pump);
    console.log(`[DEBUG] getRPM 見つかった要素:`, rpmDisplay);
    
    // 送信コマンドの内容を表示
    if (data.command_bytes && data.command_bytes.length > 0) {
      const commandDisplay = document.getElementById('commandDisplay' + pump);
      if (commandDisplay) {
        const commandBytes = new Uint8Array(data.command_bytes);
        commandDisplay.value = formatCommandBytes(commandBytes, pump);
      }
    }
    
    if (data.success) {
      updateRpmDisplay(pump, data.rpm);
      console.log(data.message);
    } else {
      updateRpmDisplay(pump, 0);
      console.error('回転速度取得失敗:', data.message);
    }
  } catch (error) {
    console.error('通信エラー:', error);
    updateRpmDisplay(pump, 0);
  }
}

// ポンプコマンド送信
// 返り値: サーバーからのパース済みJSONオブジェクト（失敗時はundefined）
async function sendPumpCommand(pump, action, value = "000000", microstepState = "0") {
  console.log(`[DEBUG] sendPumpCommand呼び出し: ポンプ${pump}, アクション${action}, isAutoSending=${isAutoSending}`);

  if (isAutoSending) {
    console.log('自動送信中のため、ポンプコマンド送信をスキップします');
    alert('自動送信中です。しばらくお待ちください。');
    return undefined;
  }

  try {
    const response = await fetch(`/api/pump_control?pump=${pump}&action=${action}&value=${value}&microstep=${microstepState}`);
    const data = await response.json();

    // 送信コマンドの内容を表示
    if (data && data.command_bytes && data.command_bytes.length > 0) {
      const commandDisplay = document.getElementById('commandDisplay' + pump);
      if (commandDisplay) {
        const commandBytes = new Uint8Array(data.command_bytes);
        commandDisplay.value = formatCommandBytes(commandBytes, pump);
      }
    }

    if (data && data.success) {
      console.log(data.message);
    } else if (data) {
      console.error('送信失敗:', data.message);
    }

    return data;
  } catch (error) {
    console.error('通信エラー:', error);
    return undefined;
  }
}

// システム状態確認
async function checkStatus() {
  try {
    console.log('[checkStatus] 状態確認開始...');
    const response = await fetch('/api/status');
    const data = await response.json();
    
    console.log('[checkStatus] APIレスポンス:', data);
    
    const statusIndicator1 = document.getElementById('serialStatus1');
    const statusText1 = document.getElementById('statusText1');
    const statusIndicator2 = document.getElementById('serialStatus2');
    const statusText2 = document.getElementById('statusText2');
    
    // ACM0（ポンプ1-3）の状態
    if (data.hysera_port1_status) {
      statusIndicator1.style.background = '#28a745';
      statusText1.textContent = 'ACM0（ポンプ1-3）: オンライン';
      console.log('[checkStatus] ACM0: オンライン');
    } else {
      statusIndicator1.style.background = '#dc3545';
      statusText1.textContent = 'ACM0（ポンプ1-3）: オフライン';
      console.log('[checkStatus] ACM0: オフライン');
    }
    
    // ACM1（ポンプ4-6）の状態
    if (data.hysera_port2_status) {
      statusIndicator2.style.background = '#28a745';
      statusText2.textContent = 'ACM1（ポンプ4-6）: オンライン';
      console.log('[checkStatus] ACM1: オンライン');
    } else {
      statusIndicator2.style.background = '#dc3545';
      statusText2.textContent = 'ACM1（ポンプ4-6）: オフライン';
      console.log('[checkStatus] ACM1: オフライン');
    }
    
    console.log('[checkStatus] 状態確認完了');
    
  } catch (error) {
    console.error('状態確認エラー:', error);
    // エラー時にステータス表示を更新
    const statusIndicator1 = document.getElementById('serialStatus1');
    const statusText1 = document.getElementById('statusText1');
    const statusIndicator2 = document.getElementById('serialStatus2');
    const statusText2 = document.getElementById('statusText2');
    
    if (statusIndicator1) statusIndicator1.style.background = '#ffc107';
    if (statusText1) statusText1.textContent = 'ACM0（ポンプ1-3）: エラー';
    if (statusIndicator2) statusIndicator2.style.background = '#ffc107';
    if (statusText2) statusText2.textContent = 'ACM1（ポンプ4-6）: エラー';
  }
}

// 漏液検出アラートの表示/非表示
function updateLeakAlert() {
  const leakAlert = document.getElementById('leakAlert');
  if (leakAlert) {
    console.log('漏液アラート更新:', window.leakDetected);
    if (window.leakDetected) {
      leakAlert.classList.add('show');
      console.log('漏液アラートを表示しました');
    } else {
      leakAlert.classList.remove('show');
      console.log('漏液アラートを非表示にしました');
    }
  } else {
    console.error('漏液アラート要素が見つかりません');
  }
}

// リセット処理中フラグ
let isResettingLeak = false;

// 漏液検出状態をリセット
async function resetLeakAlert() {
  try {
    console.log('漏液検出状態をリセット中...');
    
    // リセット処理中フラグを設定
    isResettingLeak = true;
    
    // まずフロントエンド側で即座にリセット
    window.leakDetected = false;
    updateLeakAlert();
    console.log('フロントエンド側で漏液アラートを非表示にしました');
    
    // サーバー側もリセット
    const response = await fetch('/api/reset_leak', {
      method: 'POST'
    });
    const data = await response.json();
    
    if (data.success) {
      console.log('サーバー側の漏液検出状態をリセットしました:', data.message);
      // サーバー側の状態を確認して同期
      window.leakDetected = data.leak_detected;
      updateLeakAlert();
      console.log('サーバー側の状態と同期しました:', data.leak_detected);
    } else {
      console.error('サーバー側のリセットに失敗:', data.message);
      // サーバー側のリセットに失敗した場合は、サーバー側の状態を再確認
      await checkLeakStatus();
    }
  } catch (error) {
    console.error('通信エラー:', error);
    // 通信エラーの場合も、サーバー側の状態を再確認
    await checkLeakStatus();
  } finally {
    // リセット処理完了後、少し待ってからフラグをリセット
    setTimeout(() => {
      isResettingLeak = false;
      console.log('リセット処理完了フラグをリセットしました');
    }, 3000); // 3秒後にフラグをリセット（少し長めに設定）
  }
}

// 漏液検出状態をチェック
// 自動送信状態を管理するフラグ
let isAutoSending = false;
let autoSendingTimeout = null;

// 漏液チェック（状態確認）のON/OFF管理
let leakCheckEnabled = false;
let autoLeakCheckInterval = null;

// RPM設定中フラグ（通信衝突を避けるため）
let isRpmSettingInProgress = false;

// 自動送信状態の表示を更新
function updateAutoSendingStatus() {
  const statusElement = document.getElementById('autoSendingStatus');
  if (statusElement) {
    if (isAutoSending) {
      statusElement.textContent = '自動送信中...';
      statusElement.style.color = 'orange';
    } else {
      statusElement.textContent = '待機中';
      statusElement.style.color = 'green';
    }
  }
}

// 漏液チェックのON/OFF切り替え
function toggleLeakCheck(isEnabled) {
  leakCheckEnabled = isEnabled;
  const label = document.getElementById('leakCheckLabel');
  
  if (label) {
    label.textContent = isEnabled ? 'ON' : 'OFF';
  }
  
  if (isEnabled) {
    console.log('漏液チェックを有効化します');
    // インターバルを再開（Zコマンドで定期的に状態確認）
    if (autoLeakCheckInterval === null) {
      autoLeakCheckInterval = setInterval(checkLeakStatus, 5000);
      console.log('漏液状態確認を再開しました (5秒間隔)');
    }
  } else {
    console.log('漏液チェックを無効化します');
    // インターバルを停止
    if (autoLeakCheckInterval !== null) {
      clearInterval(autoLeakCheckInterval);
      autoLeakCheckInterval = null;
      console.log('漏液状態確認を停止しました');
    }
  }
  
  // 状態をローカルストレージに保存
  localStorage.setItem('leak_check_enabled', isEnabled.toString());
  console.log(`漏液チェック状態を保存: ${isEnabled}`);
}

// 自動送信状態を手動でリセット（デバッグ用）
function resetAutoSendingStatus() {
  console.log('[DEBUG] 自動送信状態を手動でリセットします');
  isAutoSending = false;
  if (autoSendingTimeout) {
    clearTimeout(autoSendingTimeout);
    autoSendingTimeout = null;
  }
  updateAutoSendingStatus();
  console.log('[DEBUG] 自動送信状態をリセットしました');
}

// 漏液状態を確認（Jコマンド）
async function checkLeakStatus() {
  // 漏液チェックが無効の場合はスキップ
  if (!leakCheckEnabled) {
    console.log('漏液チェックが無効のため、スキップします');
    return;
  }
  
  // RPM設定中は漏液チェックをスキップ（通信衝突回避）
  if (isRpmSettingInProgress) {
    console.log('RPM設定処理中のため、漏液チェックをスキップします');
    return;
  }
  
  try {
    console.log('Jコマンド（状態確認）を実行中...', new Date().toLocaleTimeString());
    
    let leakDetectedPort1 = false;
    let leakDetectedPort2 = false;
    
    // ポート1の状態確認コマンドを送信
    console.log('[DEBUG] ポート1の状態確認を開始...');
    try {
      const response = await fetch('/api/check_leak_status');
      console.log('[DEBUG] ポート1 fetch完了, response.ok:', response.ok, 'status:', response.status);
      
      if (response.ok) {
        const data = await response.json();
        console.log('[DEBUG] ポート1 JSON取得:', data);
        
        if (data.success) {
          console.log('状態確認完了（ポート1）:', data.message, '- 漏液:', data.leak_detected);
          console.log('ポンプ回転速度:', `P1=${data.rpm_pump1}rpm, P2=${data.rpm_pump2}rpm, P3=${data.rpm_pump3}rpm`);
          
          leakDetectedPort1 = data.leak_detected;
          
          // 回転速度をUIに表示
          if (data.rpm_pump1 !== undefined) updateRpmDisplay(1, data.rpm_pump1);
          if (data.rpm_pump2 !== undefined) updateRpmDisplay(2, data.rpm_pump2);
          if (data.rpm_pump3 !== undefined) updateRpmDisplay(3, data.rpm_pump3);
        } else {
          console.log('状態確認エラー（ポート1）:', data.message);
        }
      } else {
        console.log('[DEBUG] ポート1 HTTPエラー:', response.status, response.statusText);
      }
    } catch (error) {
      console.log('ポート1の状態確認をスキップ:', error.message);
      console.error('[DEBUG] ポート1エラー詳細:', error);
    }
    
    // 200ms待機してからポート2をチェック
    console.log('[DEBUG] 200ms待機後、ポート2の状態確認を開始...');
    await new Promise(resolve => setTimeout(resolve, 200));
    
    // ポート2の状態確認コマンドを送信
    console.log('[DEBUG] ポート2の状態確認を開始...');
    try {
      const response2 = await fetch('/api/check_leak_status_port2');
      console.log('[DEBUG] ポート2 fetch完了, response.ok:', response2.ok, 'status:', response2.status);
      
      if (response2.ok) {
        const data2 = await response2.json();
        console.log('[DEBUG] ポート2 JSON取得:', data2);
        
        if (data2.success) {
          console.log('状態確認完了（ポート2）:', data2.message, '- 漏液:', data2.leak_detected);
          console.log('ポンプ回転速度:', `P4=${data2.rpm_pump4}rpm, P5=${data2.rpm_pump5}rpm, P6=${data2.rpm_pump6}rpm`);
          
          leakDetectedPort2 = data2.leak_detected;
          
          // 回転速度をUIに表示
          if (data2.rpm_pump4 !== undefined) updateRpmDisplay(4, data2.rpm_pump4);
          if (data2.rpm_pump5 !== undefined) updateRpmDisplay(5, data2.rpm_pump5);
          if (data2.rpm_pump6 !== undefined) updateRpmDisplay(6, data2.rpm_pump6);
        } else {
          console.log('状態確認エラー（ポート2）:', data2.message);
        }
      } else {
        console.log('[DEBUG] ポート2 HTTPエラー:', response2.status, response2.statusText);
      }
    } catch (error) {
      console.log('ポート2の状態確認をスキップ:', error.message);
      console.error('[DEBUG] ポート2エラー詳細:', error);
    }
    
    console.log('[DEBUG] 漏液状態: ポート1=' + leakDetectedPort1 + ', ポート2=' + leakDetectedPort2);
    
    // 漏液状態に応じてUIを更新（ポート1またはポート2で漏液検出）
    updateLeakDetectionUI(leakDetectedPort1 || leakDetectedPort2);
    
  } catch (error) {
    console.error('状態確認エラー:', error);
  }
}

// RPM表示を更新する関数
function updateRpmDisplay(pumpNumber, rpm) {
  console.log(`[DEBUG] updateRpmDisplay呼び出し: ポンプ${pumpNumber}, RPM=${rpm}`);
  
  const elementId = `rpmValue${pumpNumber}`;
  console.log(`[DEBUG] 検索する要素ID: ${elementId}`);
  
  const rpmElement = document.getElementById(elementId);
  console.log(`[DEBUG] 見つかった要素:`, rpmElement);
  
  if (rpmElement) {
    const oldText = rpmElement.textContent;
    rpmElement.textContent = rpm + ' rpm';
    console.log(`[DEBUG] ポンプ${pumpNumber}のRPM表示を更新: "${oldText}" -> "${rpm} rpm"`);
    console.log(`[DEBUG] 更新後の要素内容:`, rpmElement.textContent);
  } else {
    console.warn(`[ERROR] ポンプ${pumpNumber}のRPM表示要素が見つかりません (ID: ${elementId})`);
    console.log(`[DEBUG] 利用可能な要素を検索中...`);
    
    // 利用可能な要素を検索
    const allElements = document.querySelectorAll('[id*="rpm"]');
    console.log(`[DEBUG] RPM関連の要素:`, allElements);
    
    const allElementsWithValue = document.querySelectorAll('[id*="Value"]');
    console.log(`[DEBUG] Value関連の要素:`, allElementsWithValue);
  }
}

// 漏液検出UI更新関数
function updateLeakDetectionUI(leakDetected) {
  // グローバル変数を更新
  window.leakDetected = leakDetected;
  
  const leakStatusElement = document.getElementById('leakDetectionStatus');
  
  if (leakStatusElement) {
    if (leakDetected) {
      leakStatusElement.textContent = '【漏液検出】';
      leakStatusElement.style.color = 'red';
      leakStatusElement.style.fontWeight = 'bold';
      console.log('漏液が検出されました');
    } else {
      leakStatusElement.textContent = '正常';
      leakStatusElement.style.color = 'green';
      leakStatusElement.style.fontWeight = 'normal';
      console.log('漏液は検出されていません');
    }
  }
  
  // アラート表示を更新
  updateLeakAlert();
}

// トータル回転数をローカルストレージに保存
function saveTotalRevolutions(pump, revolutions) {
  const key = `pump_${pump}_total_revolutions`;
  localStorage.setItem(key, revolutions.toString());
  console.log(`トータル回転数を保存: ポンプ${pump} = ${revolutions} 回転`);
}

// トータル回転数をローカルストレージから取得
function getTotalRevolutionsFromStorage(pump) {
  const key = `pump_${pump}_total_revolutions`;
  const saved = localStorage.getItem(key);
  const revolutions = saved !== null ? parseInt(saved, 10) : 0;
  console.log(`トータル回転数を取得: ポンプ${pump} = ${revolutions} 回転`);
  return revolutions;
}

// トータル回転数取得
async function getTotalRevolutions(pump){
  console.log(`[DEBUG] getTotalRevolutions呼び出し: ポンプ${pump}, isAutoSending=${isAutoSending}`);
  
  if (isAutoSending) {
    console.log('自動送信中のため、手動トータル回転数取得をスキップします');
    alert('自動送信中です。しばらくお待ちください。');
    return;
  }
  
  try {
    console.log(`[DEBUG] getTotalRevolutions呼び出し: ポンプ${pump}`);
    const response = await fetch(`/api/get_total_revolutions?pump=${pump}`);
    const data = await response.json();
    
    console.log(`[DEBUG] getTotalRevolutions レスポンス:`, data);
    
    const totalRevolutionsDisplay = document.getElementById('totalRevolutions' + pump);
    console.log(`[DEBUG] getTotalRevolutions 見つかった要素:`, totalRevolutionsDisplay);
    
    // 送信コマンドの内容を表示
    if (data.command_bytes && data.command_bytes.length > 0) {
      const commandDisplay = document.getElementById('commandDisplay' + pump);
      if (commandDisplay) {
        const commandBytes = new Uint8Array(data.command_bytes);
        commandDisplay.value = formatCommandBytes(commandBytes, pump);
      }
    }
    
    if (data.success) {
      if (totalRevolutionsDisplay) {
        const revolutions = data.total_revolutions;
        totalRevolutionsDisplay.textContent = revolutions + ' 回転';
        // 取得した値をローカルストレージに保存
        saveTotalRevolutions(pump, revolutions);
        console.log(`[DEBUG] ポンプ${pump}のトータル回転数表示を更新: ${revolutions} 回転`);
      } else {
        console.warn(`[ERROR] ポンプ${pump}のトータル回転数表示要素が見つかりません`);
      }
    } else {
      console.error(`[ERROR] トータル回転数取得失敗: ${data.message}`);
      if (totalRevolutionsDisplay) {
        totalRevolutionsDisplay.textContent = 'エラー';
      }
    }
  } catch (error) {
    console.error(`[ERROR] トータル回転数取得エラー:`, error);
    const totalRevolutionsDisplay = document.getElementById('totalRevolutions' + pump);
    if (totalRevolutionsDisplay) {
      totalRevolutionsDisplay.textContent = 'エラー';
    }
  }
}

// ページが初めて表示されたかどうかをチェックする関数
// ページを閉じて再度開いた時もtrueを返す（Jコマンドを毎回送信）
function isPageFirstLoad() {
  // ページ内でのタブ切り替えのみを検出するためのフラグ
  const pageLoadKey = 'pump_control_page_load_flag';
  const isTabSwitch = sessionStorage.getItem(pageLoadKey);
  
  if (!isTabSwitch) {
    // 初回ロードまたはページを閉じて再度開いた場合
    sessionStorage.setItem(pageLoadKey, 'loaded');
    console.log('ページ初回表示: Jコマンドで制御状態を同期します');
    return true;
  } else {
    // 同一ページ内でのタブ切り替え（シリンジポンプ→ハイセラポンプなど）
    console.log('ページ内タブ切り替え: localStorageから制御状態を復元します');
    return false;
  }
}

// 制御状態を取得してスイッチに反映する関数
async function loadControlStatus() {
  console.log('制御状態を取得中...');
  
  try {
    const response = await fetch('/api/get_control_status');
    const data = await response.json();
    
    console.log('制御状態取得結果:', data);
    
    if (data.success) {
      // 各ポンプのスイッチ状態を反映
      for (let pump = 1; pump <= 3; pump++) {
        const idx = pump - 1;
        
        // バルブ常時Openスイッチ
        const valveSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleValve(${pump}"]`);
        if (valveSwitch) {
          valveSwitch.checked = data.valve[idx];
          document.getElementById('valveLabel' + pump).innerText = data.valve[idx] ? 'ON' : 'OFF';
          saveSwitchState(pump, 'valve', data.valve[idx]);
          console.log(`ポンプ${pump}のバルブ常時Openを設定: ${data.valve[idx] ? 'ON' : 'OFF'}`);
        }
        
        // 励磁常時ONスイッチ
        const excitationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleExcitation(${pump}"]`);
        if (excitationSwitch) {
          excitationSwitch.checked = data.excitation[idx];
          document.getElementById('excitationLabel' + pump).innerText = data.excitation[idx] ? 'ON' : 'OFF';
          saveSwitchState(pump, 'excitation', data.excitation[idx]);
          console.log(`ポンプ${pump}の励磁常時ONを設定: ${data.excitation[idx] ? 'ON' : 'OFF'}`);
        }
        
        // 台形加速スイッチ
        const accelerationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleAccel(${pump}"]`);
        if (accelerationSwitch) {
          accelerationSwitch.checked = data.trapezoid[idx];
          document.getElementById('accelLabel' + pump).innerText = data.trapezoid[idx] ? 'ON' : 'OFF';
          saveSwitchState(pump, 'acceleration', data.trapezoid[idx]);
          console.log(`ポンプ${pump}の台形加速を設定: ${data.trapezoid[idx] ? 'ON' : 'OFF'}`);
        }
      }
      
      console.log('制御状態の反映が完了しました');
    } else {
      console.log('制御状態取得失敗:', data.message);
    }
  } catch (error) {
    console.error('制御状態取得エラー:', error);
  }
}

// Jコマンドでポンプ制御状態を取得してUIに反映（初回のみ）
async function loadControlStatusFromJCommand() {
  console.log('[初回同期] Jコマンドでポンプ制御状態を取得中...');
  
  // ポンプ1-3（ポート1）の制御状態を取得
  try {
    const response1 = await fetch('/api/check_leak_status');
    const data1 = await response1.json();
    
    console.log('[初回同期] Jコマンド取得結果（ポート1）:', data1);
    
    if (data1.success && data1.pump_states) {
      // ポンプ1～3の制御状態をUIに反映
      for (let pump = 1; pump <= 3; pump++) {
        const idx = pump - 1;
        const state = data1.pump_states[idx];
        
        // 方向切替スイッチ
        const directionSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleDirection(${pump}"]`);
        if (directionSwitch) {
          directionSwitch.checked = state.direction_ccw;
          document.getElementById('dirLabel' + pump).innerText = state.direction_ccw ? '逆転' : '正転';
          saveSwitchState(pump, 'direction', state.direction_ccw);
          console.log(`[初回同期] ポンプ${pump}の方向: ${state.direction_ccw ? '逆転' : '正転'}`);
        }
        
        // 台形加速スイッチ
        const accelerationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleAccel(${pump}"]`);
        if (accelerationSwitch) {
          accelerationSwitch.checked = state.trapezoid;
          document.getElementById('accelLabel' + pump).innerText = state.trapezoid ? 'ON' : 'OFF';
          saveSwitchState(pump, 'acceleration', state.trapezoid);
          console.log(`[初回同期] ポンプ${pump}の台形加速: ${state.trapezoid ? 'ON' : 'OFF'}`);
        }
        
        // バルブ常時Openスイッチ
        const valveSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleValve(${pump}"]`);
        if (valveSwitch) {
          valveSwitch.checked = state.valve_open;
          document.getElementById('valveLabel' + pump).innerText = state.valve_open ? 'ON' : 'OFF';
          saveSwitchState(pump, 'valve', state.valve_open);
          console.log(`[初回同期] ポンプ${pump}のバルブ常時OPEN: ${state.valve_open ? 'ON' : 'OFF'}`);
        }
        
        // 励磁常時ONスイッチ
        const excitationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleExcitation(${pump}"]`);
        if (excitationSwitch) {
          excitationSwitch.checked = state.excitation_on;
          document.getElementById('excitationLabel' + pump).innerText = state.excitation_on ? 'ON' : 'OFF';
          saveSwitchState(pump, 'excitation', state.excitation_on);
          console.log(`[初回同期] ポンプ${pump}の励磁常時ON: ${state.excitation_on ? 'ON' : 'OFF'}`);
        }
      }
      
      console.log('[初回同期] ポート1（ポンプ1-3）のJコマンドによる制御状態の反映が完了しました');
    } else {
      console.log('[初回同期] ポート1 Jコマンド取得失敗または状態データなし:', data1.message);
    }
  } catch (error) {
    console.error('[初回同期] ポート1 Jコマンド取得エラー:', error);
  }
  
  // ポート1の処理完了後、少し待機してからポート2の処理を開始
  // （シリアル通信の安定性確保のため）
  await new Promise(resolve => setTimeout(resolve, 200));  // 200ms待機
  
  // ポンプ4-6（ポート2）の制御状態を取得
  try {
    const response2 = await fetch('/api/check_leak_status_port2');
    const data2 = await response2.json();
    
    console.log('[初回同期] Jコマンド取得結果（ポート2）:', data2);
    
    if (data2.success && data2.pump_states) {
      // ポンプ4～6の制御状態をUIに反映
      for (let pump = 4; pump <= 6; pump++) {
        const idx = pump - 4;  // ポンプ4-6はインデックス0-2
        const state = data2.pump_states[idx];
        
        // 方向切替スイッチ
        const directionSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleDirection(${pump}"]`);
        if (directionSwitch) {
          directionSwitch.checked = state.direction_ccw;
          document.getElementById('dirLabel' + pump).innerText = state.direction_ccw ? '逆転' : '正転';
          saveSwitchState(pump, 'direction', state.direction_ccw);
          console.log(`[初回同期] ポンプ${pump}の方向: ${state.direction_ccw ? '逆転' : '正転'}`);
        }
        
        // 台形加速スイッチ
        const accelerationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleAccel(${pump}"]`);
        if (accelerationSwitch) {
          accelerationSwitch.checked = state.trapezoid;
          document.getElementById('accelLabel' + pump).innerText = state.trapezoid ? 'ON' : 'OFF';
          saveSwitchState(pump, 'acceleration', state.trapezoid);
          console.log(`[初回同期] ポンプ${pump}の台形加速: ${state.trapezoid ? 'ON' : 'OFF'}`);
        }
        
        // バルブ常時Openスイッチ
        const valveSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleValve(${pump}"]`);
        if (valveSwitch) {
          valveSwitch.checked = state.valve_open;
          document.getElementById('valveLabel' + pump).innerText = state.valve_open ? 'ON' : 'OFF';
          saveSwitchState(pump, 'valve', state.valve_open);
          console.log(`[初回同期] ポンプ${pump}のバルブ常時OPEN: ${state.valve_open ? 'ON' : 'OFF'}`);
        }
        
        // 励磁常時ONスイッチ
        const excitationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleExcitation(${pump}"]`);
        if (excitationSwitch) {
          excitationSwitch.checked = state.excitation_on;
          document.getElementById('excitationLabel' + pump).innerText = state.excitation_on ? 'ON' : 'OFF';
          saveSwitchState(pump, 'excitation', state.excitation_on);
          console.log(`[初回同期] ポンプ${pump}の励磁常時ON: ${state.excitation_on ? 'ON' : 'OFF'}`);
        }
      }
      
      console.log('[初回同期] ポート2（ポンプ4-6）のJコマンドによる制御状態の反映が完了しました');
    } else {
      console.log('[初回同期] ポート2 Jコマンド取得失敗または状態データなし:', data2.message);
    }
  } catch (error) {
    console.error('[初回同期] ポート2 Jコマンド取得エラー:', error);
  }
}

// スイッチの状態をリセットする関数
function resetSwitchStates() {
  console.log('スイッチの状態をリセット中...');
  
  // 各ポンプのスイッチ状態をリセット
  for (let pump = 1; pump <= 6; pump++) {
    // 方向切替スイッチをリセット
    const directionSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleDirection(${pump}"]`);
    if (directionSwitch) {
      directionSwitch.checked = false;
      document.getElementById('dirLabel' + pump).innerText = '正転';
      saveSwitchState(pump, 'direction', false);
      console.log(`ポンプ${pump}の方向切替をリセット: 正転`);
    }
    
    // 台形加速スイッチをリセット
    const accelerationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleAccel(${pump}"]`);
    if (accelerationSwitch) {
      accelerationSwitch.checked = false;
      document.getElementById('accelLabel' + pump).innerText = 'OFF';
      saveSwitchState(pump, 'acceleration', false);
      console.log(`ポンプ${pump}の台形加速をリセット: OFF`);
    }
    
    // 弁常時Openスイッチをリセット
    const valveSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleValve(${pump}"]`);
    if (valveSwitch) {
      valveSwitch.checked = false;
      document.getElementById('valveLabel' + pump).innerText = 'OFF';
      saveSwitchState(pump, 'valve', false);
      console.log(`ポンプ${pump}の弁常時Openをリセット: OFF`);
    }
    
    // 励磁常時ONスイッチをリセット
    const excitationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleExcitation(${pump}"]`);
    if (excitationSwitch) {
      excitationSwitch.checked = false;
      document.getElementById('excitationLabel' + pump).innerText = 'OFF';
      saveSwitchState(pump, 'excitation', false);
      console.log(`ポンプ${pump}の励磁常時ONをリセット: OFF`);
    }
  }
  
  console.log('スイッチの状態リセット完了');
}

// スイッチの状態を復元する関数
function restoreSwitchStates() {
  console.log('スイッチの状態を復元中...');
  
  // 各ポンプのスイッチ状態を復元
  for (let pump = 1; pump <= 6; pump++) {
    // 方向切替スイッチの復元
    const directionState = getSwitchState(pump, 'direction', false);
    const directionSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleDirection(${pump}"]`);
    if (directionSwitch) {
      directionSwitch.checked = directionState;
      document.getElementById('dirLabel' + pump).innerText = directionState ? '逆転' : '正転';
      console.log(`ポンプ${pump}の方向切替を復元: ${directionState ? '逆転' : '正転'}`);
    }
    
    // 台形加速スイッチの復元
    const accelerationState = getSwitchState(pump, 'acceleration', false);
    const accelerationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleAccel(${pump}"]`);
    if (accelerationSwitch) {
      accelerationSwitch.checked = accelerationState;
      document.getElementById('accelLabel' + pump).innerText = accelerationState ? 'ON' : 'OFF';
      console.log(`ポンプ${pump}の台形加速を復元: ${accelerationState ? 'ON' : 'OFF'}`);
    }
    
    // 弁常時Openスイッチの復元
    const valveState = getSwitchState(pump, 'valve', false);
    const valveSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleValve(${pump}"]`);
    if (valveSwitch) {
      valveSwitch.checked = valveState;
      document.getElementById('valveLabel' + pump).innerText = valveState ? 'ON' : 'OFF';
      console.log(`ポンプ${pump}の弁常時Openを復元: ${valveState ? 'ON' : 'OFF'}`);
    }
    
    // 励磁常時ONスイッチの復元
    const excitationState = getSwitchState(pump, 'excitation', false);
    const excitationSwitch = document.querySelector(`input[type="checkbox"][onchange*="toggleExcitation(${pump}"]`);
    if (excitationSwitch) {
      excitationSwitch.checked = excitationState;
      document.getElementById('excitationLabel' + pump).innerText = excitationState ? 'ON' : 'OFF';
      console.log(`ポンプ${pump}の励磁常時ONを復元: ${excitationState ? 'ON' : 'OFF'}`);
    }
  }
  
  console.log('スイッチの状態復元完了');
}

// トータル回転数を復元する関数
function restoreTotalRevolutions() {
  console.log('トータル回転数を復元中...');
  
  // 各ポンプのトータル回転数を復元
  for (let pump = 1; pump <= 6; pump++) {
    const savedRevolutions = getTotalRevolutionsFromStorage(pump);
    const totalRevolutionsDisplay = document.getElementById('totalRevolutions' + pump);
    
    if (totalRevolutionsDisplay) {
      totalRevolutionsDisplay.textContent = savedRevolutions + ' 回転';
      console.log(`ポンプ${pump}のトータル回転数を復元: ${savedRevolutions} 回転`);
    } else {
      console.warn(`ポンプ${pump}のトータル回転数表示要素が見つかりません`);
    }
  }
  
  console.log('トータル回転数の復元完了');
}

// Choices.jsを初期化する関数
function initializeChoices() {
  console.log('Choices.jsを初期化中...');
  
  // 各ポンプのステップ数選択ボックスを初期化
  for (let pump = 1; pump <= 6; pump++) {
    const selectElement = document.getElementById('steps' + pump);
    if (selectElement) {
      const choices = new Choices(selectElement, {
        searchEnabled: false,
        searchChoices: false,
        removeItemButton: false,
        noResultsText: '結果が見つかりません',
        noChoicesText: '選択肢がありません',
        itemSelectText: '',
        placeholder: false,
        allowHTML: false,
        shouldSort: false,
        classNames: {
          containerOuter: 'choices',
          containerInner: 'choices__inner',
          input: 'choices__input',
          inputCloned: 'choices__input--cloned',
          list: 'choices__list',
          listItems: 'choices__list--multiple',
          listSingle: 'choices__list--single',
          listDropdown: 'choices__list--dropdown',
          item: 'choices__item',
          itemSelectable: 'choices__item--selectable',
          itemDisabled: 'choices__item--disabled',
          itemChoice: 'choices__item--choice',
          placeholder: 'choices__placeholder',
          group: 'choices__group',
          groupHeading: 'choices__heading',
          button: 'choices__button',
          activeState: 'is-active',
          focusState: 'is-focused',
          openState: 'is-open',
          disabledState: 'is-disabled',
          highlightedState: 'is-highlighted',
          selectedState: 'is-selected',
          flippedState: 'is-flipped',
          loadingState: 'is-loading',
          noResults: 'has-no-results',
          noChoices: 'has-no-choices'
        }
      });
      
      console.log(`ポンプ${pump}のChoices.jsを初期化しました`);
      
      // selectElementにchoicesインスタンスを保存
      selectElement.choices = choices;
      // 初期表示を0に設定（プレースホルダ表示を無効化して0を選択状態にする）
      try {
        choices.setChoiceByValue('0');
      } catch (e) {
        console.log('初期値0の設定に失敗しました:', e);
      }
    }
    
    // RPM設定選択ボックスを初期化
    const rpmElement = document.getElementById('rpmSetting' + pump);
    if (rpmElement) {
      const rpmChoices = new Choices(rpmElement, {
        searchEnabled: false,
        searchChoices: false,
        removeItemButton: false,
        noResultsText: '結果が見つかりません',
        noChoicesText: '選択肢がありません',
        itemSelectText: '',
        placeholder: true,
        placeholderValue: 'RPMを選択',
        allowHTML: false,
        shouldSort: false,
        classNames: {
          containerOuter: 'choices',
          containerInner: 'choices__inner',
          input: 'choices__input',
          inputCloned: 'choices__input--cloned',
          list: 'choices__list',
          listItems: 'choices__list--multiple',
          listSingle: 'choices__list--single',
          listDropdown: 'choices__list--dropdown',
          item: 'choices__item',
          itemSelectable: 'choices__item--selectable',
          itemDisabled: 'choices__item--disabled',
          itemChoice: 'choices__item--choice',
          placeholder: 'choices__placeholder',
          group: 'choices__group',
          groupHeading: 'choices__heading',
          button: 'choices__button',
          activeState: 'is-active',
          focusState: 'is-focused',
          openState: 'is-open',
          disabledState: 'is-disabled',
          highlightedState: 'is-highlighted',
          selectedState: 'is-selected',
          flippedState: 'is-flipped',
          loadingState: 'is-loading',
          noResults: 'has-no-results',
          noChoices: 'has-no-choices'
        }
      });
      
      console.log(`ポンプ${pump}のRPM設定Choices.jsを初期化しました`);
      
      // rpmElementにchoicesインスタンスを保存
      rpmElement.choices = rpmChoices;
      
      // ポンプ1～6の場合、値が変更されたら同じグループの他のポンプのRPMも同期
      if (pump >= 1 && pump <= 6) {
        rpmElement.addEventListener('change', function(event) {
          const selectedValue = event.target.value;
          if (selectedValue) {
            console.log(`ポンプ${pump}のRPM選択が変更されました: ${selectedValue} RPM`);
            syncRPMSettings(pump, selectedValue);
          }
        });
      }
    }
  }
  
  console.log('Choices.jsの初期化が完了しました');
}

// ストリーミング関連の関数
function toggleStreaming() {
  try {
    const overlay = document.getElementById('streamingOverlay');
    const minimizeBtn = overlay.querySelector('.streaming-minimize');
    
    if (overlay.classList.contains('minimized')) {
      overlay.classList.remove('minimized');
      minimizeBtn.textContent = '−';
    } else {
      overlay.classList.add('minimized');
      minimizeBtn.textContent = '';
    }
  } catch (error) {
    console.error('ストリーミングトグルエラー:', error);
  }
}

function refreshStream() {
  try {
    const streamingVideo = document.getElementById('streamingVideo');
    if (streamingVideo) {
      streamingVideo.src = streamingVideo.src.split('?')[0] + '?t=' + Date.now();
    }
  } catch (error) {
    console.error('ストリーム更新エラー:', error);
  }
}

function openFullStream() {
  try {
    window.open('/', '_blank');
  } catch (error) {
    console.error('フルストリーム表示エラー:', error);
  }
}

// ストリーミング画像のエラーハンドリング
function handleStreamingError() {
  console.warn('ストリーミング画像の読み込みに失敗しました');
  const streamingVideo = document.getElementById('streamingVideo');
  if (streamingVideo) {
    streamingVideo.style.display = 'none';
  }
}

// ドラッグ機能の実装
let isDragging = false;
let dragOffsetX = 0;
let dragOffsetY = 0;

function initDraggable() {
  const overlay = document.getElementById('streamingOverlay');
  const header = overlay.querySelector('.streaming-header');
  
  if (!overlay || !header) return;

  let clickStartTime = 0;
  let clickStartX = 0;
  let clickStartY = 0;

  // マウスダウン（ドラッグ開始）
  header.addEventListener('mousedown', function(e) {
    // ボタンクリック時はドラッグしない
    if (e.target.classList.contains('streaming-minimize')) {
      return;
    }

    clickStartTime = Date.now();
    clickStartX = e.clientX;
    clickStartY = e.clientY;

    isDragging = true;
    overlay.classList.add('dragging');
    
    const rect = overlay.getBoundingClientRect();
    dragOffsetX = e.clientX - rect.left;
    dragOffsetY = e.clientY - rect.top;
    
    e.preventDefault();
  });

  // マウスムーブ（ドラッグ中）
  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    
    let newX = e.clientX - dragOffsetX;
    let newY = e.clientY - dragOffsetY;
    
    // 画面外に出ないように制限
    const maxX = window.innerWidth - overlay.offsetWidth;
    const maxY = window.innerHeight - overlay.offsetHeight;
    
    newX = Math.max(0, Math.min(newX, maxX));
    newY = Math.max(0, Math.min(newY, maxY));
    
    overlay.style.left = newX + 'px';
    overlay.style.top = newY + 'px';
    
    e.preventDefault();
  });

  // マウスアップ（ドラッグ終了）
  document.addEventListener('mouseup', function(e) {
    if (isDragging) {
      const clickEndTime = Date.now();
      const timeDiff = clickEndTime - clickStartTime;
      const distanceX = Math.abs(e.clientX - clickStartX);
      const distanceY = Math.abs(e.clientY - clickStartY);
      const distance = Math.sqrt(distanceX * distanceX + distanceY * distanceY);
      
      // クリックと判定（200ms以下で5px以下の移動）
      if (timeDiff < 200 && distance < 5 && overlay.classList.contains('minimized')) {
        toggleStreaming();
      }
      
      isDragging = false;
      overlay.classList.remove('dragging');
    }
  });

  // タッチデバイス対応
  header.addEventListener('touchstart', function(e) {
    if (e.target.classList.contains('streaming-minimize')) {
      return;
    }

    isDragging = true;
    overlay.classList.add('dragging');
    
    const touch = e.touches[0];
    const rect = overlay.getBoundingClientRect();
    dragOffsetX = touch.clientX - rect.left;
    dragOffsetY = touch.clientY - rect.top;
    
    e.preventDefault();
  });

  document.addEventListener('touchmove', function(e) {
    if (!isDragging) return;
    
    const touch = e.touches[0];
    let newX = touch.clientX - dragOffsetX;
    let newY = touch.clientY - dragOffsetY;
    
    const maxX = window.innerWidth - overlay.offsetWidth;
    const maxY = window.innerHeight - overlay.offsetHeight;
    
    newX = Math.max(0, Math.min(newX, maxX));
    newY = Math.max(0, Math.min(newY, maxY));
    
    overlay.style.left = newX + 'px';
    overlay.style.top = newY + 'px';
    
    e.preventDefault();
  });

  document.addEventListener('touchend', function(e) {
    if (isDragging) {
      isDragging = false;
      overlay.classList.remove('dragging');
    }
  });
}

// ページ読み込み時に状態確認
document.addEventListener('DOMContentLoaded', function() {
  console.log('ページ読み込み完了 - 漏液検出監視を開始します');
  
  // ストリーミングを初期状態で最小化
  try {
    const streamingOverlay = document.getElementById('streamingOverlay');
    if (streamingOverlay) {
      streamingOverlay.classList.add('minimized');
    }
  } catch (error) {
    console.error('ストリーミング初期化エラー:', error);
  }
  
  // ドラッグ機能を初期化
  try {
    initDraggable();
    console.log('ストリーミングのドラッグ機能を初期化しました');
  } catch (error) {
    console.error('ドラッグ機能初期化エラー:', error);
  }
  
  // Choices.jsを初期化
  initializeChoices();
  
  // デバッグ: 利用可能な要素を確認
  console.log('[DEBUG] ページ読み込み時の要素確認');
  const allRpmElements = document.querySelectorAll('[id*="rpm"]');
  console.log('[DEBUG] RPM関連の要素:', allRpmElements);
  
  for (let i = 0; i < allRpmElements.length; i++) {
    console.log(`[DEBUG] 要素${i}: id="${allRpmElements[i].id}", text="${allRpmElements[i].textContent}"`);
  }
  
  // ブラウザ立ち上げかどうかをチェックして、スイッチの状態を処理
  if (isPageFirstLoad()) {
    console.log('ページ初回表示のため、スイッチの状態をリセットします');
    resetSwitchStates();
    
    // 初回のみJコマンドでポンプ制御状態を取得してUIに反映
    setTimeout(async () => {
      try {
        const statusResponse = await fetch('/api/status');
        const statusData = await statusResponse.json();
        
        if (statusData.hysera_port1_status || statusData.hysera_port2_status) {
          console.log('[初回同期] USB通信がオンラインのため、Jコマンドでポンプ制御状態を取得します');
          console.log(`[初回同期] ポート1: ${statusData.hysera_port1_status ? 'オンライン' : 'オフライン'}, ポート2: ${statusData.hysera_port2_status ? 'オンライン' : 'オフライン'}`);
          await loadControlStatusFromJCommand();
        } else {
          console.log('[初回同期] USB通信がオフラインのため、Jコマンド送信をスキップします');
        }
      } catch (error) {
        console.error('[初回同期] USB通信状態確認エラー:', error);
      }
    }, 500);  // 500ms待機してから制御状態を取得
  } else {
    console.log('ページ内タブ切り替えのため、スイッチの状態を復元します（Jコマンドは送信しません）');
    restoreSwitchStates();
  }
  
  // トータル回転数を常に復元（ブラウザ立ち上げ時もページ切り替え時も）
  restoreTotalRevolutions();
  
  // 漏液検出状態を初期化
  window.leakDetected = false;
  
  // 自動送信状態を初期化
  isAutoSending = false;
  updateAutoSendingStatus();
  
  // 漏液チェック状態を復元（デフォルトはOFF）
  const savedLeakCheckState = localStorage.getItem('leak_check_enabled');
  if (savedLeakCheckState !== null) {
    leakCheckEnabled = savedLeakCheckState === 'true';
  } else {
    leakCheckEnabled = false; // 初期値はOFF
  }
  
  // スイッチの状態を復元
  const leakCheckSwitch = document.getElementById('leakCheckSwitch');
  if (leakCheckSwitch) {
    leakCheckSwitch.checked = leakCheckEnabled;
    const leakCheckLabel = document.getElementById('leakCheckLabel');
    if (leakCheckLabel) {
      leakCheckLabel.textContent = leakCheckEnabled ? 'ON' : 'OFF';
    }
    console.log(`漏液チェック状態を復元: ${leakCheckEnabled ? 'ON' : 'OFF'}`);
  }
  
  // ページ読み込み直後に1回呼び出す（少し待ってから）
  setTimeout(checkStatus, 100);
  checkLeakStatus();
  
  // 30秒ごとに状態確認
  setInterval(checkStatus, 30000);
  
  // 5秒ごとに漏液検出状態を確認
  // 漏液チェックがONの場合のみインターバルを開始
  if (leakCheckEnabled) {
    autoLeakCheckInterval = setInterval(checkLeakStatus, 5000);
    console.log('漏液状態確認監視が開始されました');
    console.log('Jコマンド（状態確認）による定期チェック（5秒間隔）が開始されました');
    
    // 初回実行（即座に1回実行）
    setTimeout(autoGetRpm, 1000);
  } else {
    console.log('漏液チェックがOFFのため、自動回転速度取得は開始されません');
  }
  
  // ページを離脱する時（他のページへ移動、タブを閉じる、ブラウザを閉じる）に
  // sessionStorageのフラグをクリア
  window.addEventListener('beforeunload', () => {
    sessionStorage.removeItem('pump_control_page_load_flag');
    console.log('ページ離脱: 次回ページ表示時にJコマンドを送信します');
  });
});

// トータル回転数リセット（サーバーへ 'I' コマンドを送信）
async function onResetTotalClicked(pump) {
  try {
    const confirmMsg = 'ポンプ' + pump + 'のトータル回転数をリセットしてよいですか？\n\nこの操作は元に戻せません。';
    if (!confirm(confirmMsg)) return;

    // コマンド仕様に従い、値フィールドは000001～000003でポンプ1～3を指定する
    // UI上はポンプ1～6があるため、4-6はそれぞれ1-3にマップする
    let targetIndex = pump;
    if (pump >= 4 && pump <= 6) {
      targetIndex = pump - 3;
    }

    const valueStr = String(targetIndex).padStart(6, '0'); // e.g. "000001"

    // 送信（サーバーがArduinoへ転送する想定）
    const data = await sendPumpCommand(pump, 'I', valueStr);

    if (data && data.success) {
      // 成功したら画面表示とローカルストレージを0にする
      const display = document.getElementById('totalRevolutions' + pump);
      if (display) {
        display.textContent = '0 回転';
      }
      saveTotalRevolutions(pump, 0);

      alert('トータル回転数をリセットしました');
    } else if (data) {
      alert('リセットに失敗しました: ' + (data.message || '不明なエラー'));
    } else {
      alert('通信エラーによりリセットできませんでした');
    }
  } catch (err) {
    console.error('トータル回転数リセットエラー:', err);
    alert('リセット中にエラーが発生しました');
  }
}
