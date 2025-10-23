# 漏液チェック機能の仕様変更（Zコマンド実装）

## 概要

漏液チェック機能をリファクタリングしました。従来のポーリング方式（回転速度取得コマンド（Xコマンド）のおまけ処理）から、専用の状態確認コマンド（Zコマンド）を使用する方式に変更しました。

## 変更前の仕組み

```
【従来の方式】
Python側 ---(Xコマンド)---> Arduino側
          （回転速度取得）
          
Python側 <---(応答)------ Arduino側
          （回転速度+漏液判定の埋め込み）

（問題）
- 回転速度取得が不要でも漏液チェックのため定期実行
- シリアルバッファが混在
- 他のコマンド（C, T, J）の処理に影響
```

## 変更後の仕組み

```
【新方式】Zコマンド（状態確認）
Python側 ---(Zコマンド)---> Arduino側
          STX/0/Z/000000/CS/ETX
          
Python側 <---(応答)------- Arduino側
          STX/Z/00000X/CS/ETX
          X = bit状態（bit0=漏液フラグ）
```

## コマンド仕様

### Python → Arduino（リクエスト）

```
フレーム構成：STX / ポンプNo / Z / 値 / CS / ETX
例:           0x02 / '0' / 'Z' / "000000" / CS / 0x03

バイト位置:   [0] [1] [2] [3-8] [9] [10]
```

**説明:**
- **STX** (0x02): フレーム開始
- **ポンプNo** ('0'): 状態確認では無視される
- **アクション** ('Z'): 状態確認コマンド
- **値** ("000000"): 固定値（状態確認のため無意味）
- **CS**: チェックサム（バイト[1]～[7]のXOR）
- **ETX** (0x03): フレーム終了

### Arduino → Python（レスポンス）

```
正常時:
フレーム構成：STX / 'Z' / 状態 / CS / ETX
例:           0x02 / 'Z' / "000000" / CS / 0x03

漏液検出時:
フレーム構成：STX / 'Z' / 状態 / CS / ETX
例:           0x02 / 'Z' / "000001" / CS / 0x03

バイト位置:   [0] [1] [2-7] [8] [9]
```

**説明:**
- **STX** (0x02): フレーム開始
- **応答タイプ** ('Z'): 状態確認応答（ポンプNo位置に'Z'を配置）
- **ステータス** (6桁): 
  - "000000" = 正常（すべてのビット=0）
  - "000001" = 漏液検出（bit0=1）
  - ビット0: 漏液フラグ
  - ビット1-5: 予約（将来拡張用）
- **CS**: チェックサム（バイト[1]～[7]のXOR）
- **ETX** (0x03): フレーム終了

## 実装箇所

### Arduino側 (`kousoku5.ino`)

**processCommand()関数に追加:**
```cpp
else if (action == 'Z') {  // 状態確認コマンド
    char response[11];
    response[0] = 0x02;  // STX
    response[1] = 'Z';   // 応答タイプ
    
    // 漏液状態をbit0に反映
    byte statusValue = leakDetected ? 0x01 : 0x00;
    char statusStr[7];
    sprintf(statusStr, "%06d", statusValue);
    
    // ... チェックサム計算 ...
    Serial.write(response, 10);
}
```

### Python側 (`app.py`)

**新APIエンドポイント:**
```python
@app.route("/api/check_leak_status")
def api_check_leak_status():
    # Zコマンド送信
    # Arduino応答を解析
    # bit0で漏液判定
    # グローバル leak_detected を更新
```

**処理フロー:**
1. シリアルバッファをクリア
2. Zコマンドを送信 (`send_serial_command(1, "Z", "000000")`)
3. 応答待機（最大1秒）
4. 応答フレーム解析
5. ステータス値の6桁目（bit0）で漏液判定
6. グローバル変数 `leak_detected` を更新

### フロントエンド (`pump_control.html`)

**変更点:**
- `autoGetRpm()` → `checkLeakStatus()` へ変更
- `autoRpmInterval` → `autoLeakCheckInterval` へ変更
- 定期実行（5秒間隔）は同じ

**定期実行フロー:**
```javascript
// 漏液チェックがONの場合のみ
if (leakCheckEnabled) {
    autoLeakCheckInterval = setInterval(checkLeakStatus, 5000);
}

// checkLeakStatus() 実行内容
async function checkLeakStatus() {
    if (!leakCheckEnabled) return;
    
    const response = await fetch('/api/check_leak_status');
    const data = await response.json();
    
    if (data.success) {
        updateLeakDetectionUI(data.leak_detected);
    }
}
```

## メリット

✅ **独立した専用コマンド**: 回転速度取得との干渉なし
✅ **シリアルバッファの分離**: 各コマンドが独立して動作
✅ **シンプルな仕様**: 状態確認のみの専用コマンド
✅ **将来の拡張性**: ビット1-5で他の状態も追加可能
✅ **信頼性向上**: チェックサム検証でデータ整合性確保

## テスト方法

1. **正常状態での動作確認**
   - 漏液チェックスイッチをON
   - コンソールで定期的に「状態確認完了」が表示
   - UI上で「正常」と表示

2. **漏液検出時の動作確認**
   - Arduino側で `leakDetected` をtrueに
   - Zコマンド応答が「000001」に
   - Python側が `leak_detected` をtrueに更新
   - UI上で「【漏液検出】」と赤表示

3. **通信ログの確認**
   - `DEBUG_SERIAL_LOG = True` で有効化
   - Zコマンド送受信の詳細ログが表示

## ログ例

```
[ACM0(COM18)] Zコマンド送信完了。応答待機中...
[ACM0(COM18)] Zコマンド応答受信: 02 5A 30 30 30 30 30 31 E7 03 (10 bytes)
状態確認完了: 漏液検出 - 漏液: True
```

## トラブルシューティング

| 問題 | 原因 | 対処法 |
|------|------|--------|
| 応答タイムアウト | Arduino側未実装 | kousoku5.inoをアップロード |
| 常に漏液検出 | leakDetectedフラグの異常 | Arduino側のセンサ設定確認 |
| UI更新されない | `leakDetectionStatus`要素がない | HTML側でIDを確認 |
| バッファエラー | シリアル干渉 | 他のコマンドとの重複実行を避ける |

## 互換性

- **従来の漏液検出コマンド**: `sendLeakDetectionCommand()` は廃止予定
- **回転速度取得**: 独立して動作、影響なし
- **他のコマンド**: C, X, T, J コマンドは独立動作

---

実装日: 2025年10月23日
バージョン: 2.0（Zコマンド対応版）
