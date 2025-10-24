# Phase 2: クラスベース設計の改善

## 実施日
2025年10月24日

## 概要
Phase 2では、既存のクラスベース設計を改善し、以下の機能を追加しました:
- ロギング機能の強化
- エラーハンドリングの改善
- 型ヒントの追加
- 自動再接続機能
- 統計情報の管理
- リトライ機能

## 改善されたクラス

### 1. CameraManager クラス

**場所**: `camera/camera_manager.py`

**改善内容**:
- ✅ ロギング機能の統合（logging モジュール使用）
- ✅ 型ヒントの追加（Type Hints）
- ✅ 統計情報の管理（フレーム数、エラー数）
- ✅ 詳細なドキュメント文字列
- ✅ エラーハンドリングの改善

**新機能**:
```python
# 統計情報の取得
camera = CameraManager()
# 内部的に_frame_count, _error_count, _last_error_timeを管理

# 改善されたログ出力
logger.info("カメラ初期化成功")
logger.error("カメラ初期化失敗", exc_info=True)
```

**主なメソッド**:
- `initialize() -> bool`: カメラ初期化
- `get_frame() -> Optional[np.ndarray]`: フレーム取得
- `generate_mjpeg_stream() -> Generator`: MJPEG ストリーミング
- `update_settings(width, height, fps) -> bool`: 設定更新
- `restart() -> bool`: カメラ再起動
- `close()`: カメラクローズ

---

### 2. SerialManager クラス

**場所**: `pump_controllers/serial_manager.py`

**改善内容**:
- ✅ 自動再接続機能の追加
- ✅ 統計情報の管理（送受信バイト数、エラー数）
- ✅ 型ヒントの追加
- ✅ ロギング機能の統合
- ✅ 詳細なドキュメント文字列

**新機能**:
```python
# 自動再接続を有効化
serial_mgr = SerialManager(
    port="/dev/ttyACM0",
    baud_rate=9600,
    auto_reconnect=True  # 新機能
)

# 統計情報の取得
stats = serial_mgr.get_statistics()
# => {
#     'name': 'HyseraPump1-3',
#     'port': '/dev/ttyACM0',
#     'baud_rate': 9600,
#     'is_connected': True,
#     'bytes_sent': 1024,
#     'bytes_received': 512,
#     'error_count': 0,
#     'last_error_time': 0
# }

# 手動再接続
serial_mgr.reconnect()
```

**主なメソッド**:
- `initialize() -> bool`: 初期化
- `write(data: bytes) -> bool`: データ送信（自動再接続付き）
- `read(size: int) -> bytes`: データ受信
- `reconnect() -> bool`: 再接続
- `get_statistics() -> dict`: 統計情報取得
- `wait_for_response(size, timeout) -> Optional[bytes]`: レスポンス待機

---

### 3. HyseraPumpController クラス

**場所**: `pump_controllers/hysera_pump.py`

**改善内容**:
- ✅ コマンドリトライ機能の追加
- ✅ ポンプ状態管理の追加
- ✅ 型ヒントの追加
- ✅ ロギング機能の統合
- ✅ 統計情報の管理

**新機能**:
```python
# リトライ回数を指定して初期化
controller = HyseraPumpController(max_retries=3)

# リトライ付きコマンド送信
result = controller.send_command_with_response(
    pump_no=1,
    action='S',
    value='001000',
    retry=True  # リトライを有効化
)
# => {
#     'success': True,
#     'pump_no': 1,
#     'attempts': 1,  # 何回目で成功したか
#     ...
# }

# ポンプ状態の取得
status = controller.get_pump_status(pump_no=1)
# => {
#     'running': True,
#     'rpm': 1000,
#     'last_command': 'S'
# }

# 全ポンプ状態の取得
all_status = controller.get_all_pump_status()
# => {1: {...}, 2: {...}, ..., 6: {...}}

# 統計情報の取得
stats = controller.get_statistics()
# => {
#     'port1': {...},
#     'port2': {...},
#     'leak_detected': False,
#     'pump_status': {...}
# }
```

**主なメソッド**:
- `initialize() -> bool`: 初期化
- `send_command(pump_no, action, value) -> Tuple`: コマンド送信（基本）
- `send_command_with_response(pump_no, action, value, retry=True) -> Dict`: コマンド送信（リトライ付き）
- `get_pump_status(pump_no) -> Optional[Dict]`: ポンプ状態取得
- `get_all_pump_status() -> Dict`: 全ポンプ状態取得
- `get_statistics() -> Dict`: 統計情報取得
- `check_leak_detection() -> bool`: 漏液検出チェック
- `reset_leak_detection()`: 漏液検出リセット

---

### 4. SyringePumpManager クラス

**場所**: `pump_controllers/syringe_pump.py`

**改善内容**:
- ✅ 型ヒントの追加
- ✅ ロギング機能の統合
- ✅ エラーハンドリングの改善
- ✅ 統計情報の管理
- ✅ 詳細なドキュメント文字列

**新機能**:
```python
manager = SyringePumpManager()
manager.initialize()

# ポンプ番号でコントローラーを取得（1-6）
controller = manager.get_controller_by_number(pump_number=1)

# 全コントローラーを取得
all_controllers = manager.get_all_controllers()

# 統計情報の取得
stats = manager.get_statistics()
# => {
#     'serial_port': {...},
#     'controller_count': 6,
#     'is_connected': True
# }
```

**主なメソッド**:
- `initialize() -> bool`: 初期化
- `get_controller(pump_index: int) -> Optional[Controller]`: コントローラー取得（0-5）
- `get_controller_by_number(pump_number: int) -> Optional[Controller]`: コントローラー取得（1-6）
- `get_all_controllers() -> List[Controller]`: 全コントローラー取得
- `get_statistics() -> Dict`: 統計情報取得
- `close()`: クローズ

---

### 5. SyringePumpController クラス（レガシー）

**場所**: `command.py`

**改善内容**:
- ✅ 型ヒントの追加
- ✅ ロギング機能の統合
- ✅ 詳細なドキュメント文字列
- ✅ レガシー注記の追加

**注意**: このクラスは後方互換性のために保持されています。新しいコードでは `SyringePumpManager` を使用してください。

---

## 共通改善事項

### 1. ロギングシステム

全てのクラスで統一されたロギングを実装:

```python
import logging

logger = logging.getLogger(__name__)

# DEBUGレベル（詳細ログ）
logger.debug("詳細な情報")

# INFOレベル（通常の情報）
logger.info("✓ 初期化成功")

# WARNINGレベル（警告）
logger.warning("ポート1のみ初期化成功")

# ERRORレベル（エラー）
logger.error("✗ 初期化失敗", exc_info=True)
```

### 2. 型ヒント（Type Hints）

全てのメソッドに型ヒントを追加:

```python
def send_command(self, pump_no: int, action: str, value: str = "000000") -> Dict:
    ...

def get_statistics(self) -> Dict:
    ...

def is_connected(self) -> bool:
    ...
```

### 3. 統計情報管理

各クラスで以下の統計情報を管理:

- **CameraManager**:
  - `_frame_count`: フレーム数
  - `_error_count`: エラー数
  - `_last_error_time`: 最終エラー時刻

- **SerialManager**:
  - `_bytes_sent`: 送信バイト数
  - `_bytes_received`: 受信バイト数
  - `_error_count`: エラー数
  - `_last_error_time`: 最終エラー時刻

- **HyseraPumpController**:
  - `_pump_status`: 各ポンプの状態（running, rpm, last_command）

### 4. エラーハンドリング

全てのクラスで改善されたエラーハンドリング:

```python
try:
    # 処理
    logger.info("処理成功")
    return True
except Exception as e:
    logger.error(f"処理エラー: {e}", exc_info=True)
    self._error_count += 1
    self._last_error_time = time.time()
    return False
```

---

## 使用例

### カメラ制御

```python
from camera.camera_manager import CameraManager

# カメラ初期化
camera = CameraManager()
if camera.initialize():
    # MJPEGストリーミング
    for frame in camera.generate_mjpeg_stream():
        yield frame
    
    # 設定変更
    camera.update_settings(width=1280, height=720, fps=30)
```

### ハイセラポンプ制御

```python
from pump_controllers.hysera_pump import HyseraPumpController

# ポンプ初期化（リトライ3回）
controller = HyseraPumpController(max_retries=3)
if controller.initialize():
    # ポンプ起動（リトライ付き）
    result = controller.send_command_with_response(
        pump_no=1,
        action='S',
        value='001000',
        retry=True
    )
    
    if result['success']:
        print(f"ポンプ1起動成功（{result['attempts']}回目で成功）")
    
    # ポンプ状態確認
    status = controller.get_pump_status(1)
    print(f"ポンプ1状態: {status}")
    
    # 統計情報
    stats = controller.get_statistics()
    print(f"統計: {stats}")
```

### シリンジポンプ制御

```python
from pump_controllers.syringe_pump import SyringePumpManager

# マネージャー初期化
manager = SyringePumpManager()
if manager.initialize():
    # ポンプ1のコントローラー取得
    controller = manager.get_controller_by_number(1)
    
    # コマンド送信
    success, cmd, response = controller.send_command("RUN", address=1)
    
    # 統計情報
    stats = manager.get_statistics()
    print(f"統計: {stats}")
```

---

## 互換性

### 既存機能との互換性

✅ **完全互換**: 既存のすべての機能は保持されています
✅ **メソッドシグネチャ**: 既存のメソッド呼び出しはすべて動作します
✅ **戻り値**: 既存の戻り値形式は変更されていません

### 新機能（オプション）

新機能はすべてオプションです:
- `auto_reconnect=True`: デフォルトで有効
- `retry=True`: リトライ機能（既存コードに影響なし）
- `get_statistics()`: 新しいメソッド（既存コードに影響なし）

---

## テスト推奨事項

Phase 2の改善をテストする際の推奨事項:

1. **カメラ初期化テスト**
   ```python
   camera = CameraManager()
   assert camera.initialize() == True
   ```

2. **シリアル通信テスト**
   ```python
   serial_mgr = SerialManager("/dev/ttyACM0", 9600)
   assert serial_mgr.initialize() == True
   assert serial_mgr.is_connected() == True
   ```

3. **ポンプ制御テスト**
   ```python
   controller = HyseraPumpController(max_retries=3)
   assert controller.initialize() == True
   result = controller.send_command_with_response(1, 'S', '001000')
   assert result['success'] == True
   ```

4. **統計情報テスト**
   ```python
   stats = controller.get_statistics()
   assert 'port1' in stats
   assert 'pump_status' in stats
   ```

---

## 次のステップ（Phase 3予定）

- [ ] API ルートの分離（`api/` モジュール作成）
- [ ] Flask Blueprints の実装
- [ ] app.py のリファクタリング（新モジュールの統合）
- [ ] 統合テストの作成
- [ ] ユニットテストの追加

---

## まとめ

Phase 2では、既存のクラスベース設計を大幅に改善しました:

1. **保守性向上**: ロギング、型ヒント、ドキュメントの追加
2. **信頼性向上**: 自動再接続、リトライ機能、エラーハンドリング
3. **可視性向上**: 統計情報管理、詳細なログ出力
4. **互換性維持**: すべての既存機能を保持

これらの改善により、システムの保守性、信頼性、デバッグ性が大幅に向上しました。
