# 統合制御システム 技術仕様書

## 1. プロジェクト概要

このプロジェクトは、Raspberry Piをホストとして、リアルタイムカメラストリーミング、複数のポンプ制御、および高精度ステッピングモーター制御を統合したWebベースの遠隔操作システムです。

Web UIから、カメラ映像の監視、スナップショットの取得、および接続された各種デバイスの制御をリアルタイムで行うことができます。システムのバックエンドはFlask（Python）でモジュール化されており、モーター制御のファームウェアはArduino（C++）で構築されています。

### アーキテクチャの特徴

-   **モジュール化設計**: コードベースは機能ごとに独立したモジュールに分割され、保守性とテスト容易性が向上しています。
-   **設定の外部化**: すべての設定値は`config.py`に集約され、環境変数にも対応しています。
-   **クラスベース設計**: カメラ管理、シリアル通信、ポンプ制御はそれぞれ独立したクラスとして実装されています。

### 主な機能

-   **リアルタイム映像配信**: Raspberry Pi公式カメラモジュールまたはPCのWebカメラからの映像をMJPEG形式でストリーミングします。
-   **ハイセラポンプ制御**: 2つのシリアルポート（ACM0, ACM1）を介して、最大6台のハイセラポンプを制御します。
-   **シリンジポンプ制御**: 別のシリアルポート（USB0）を介して、最大6台のシリンジポンプを個別に制御します。
-   **高精度モーター制御**: Arduino上で動作するファームウェアにより、最大3台のステッピングモーターを台形加減速制御付きで精密に操作します。
-   **Webインターフェース**: PCやスマートフォンのブラウザからシステム全体を操作・監視するためのレスポンシブUIを提供します。

## 2. システムアーキテクチャ

本システムは、以下のコンポーネントで構成されています。

```
+-----------------------------+      HTTP      +-----------------+
|      クライアント (ブラウザ)     | <----------> |  Flask Webサーバー |
| (PC / スマートフォン)         |              |     (app.py)    |
+-----------------------------+              +--------+--------+
                                                       |
+------------------------------------------------------+------------------------------------------------------+
| シリアル通信 (pyserial)                                                                                       |
+------------------------+-----------------------------+-----------------------------+------------------------+
                         |                             |                             |
+------------------+   |   +---------------------+   |   +---------------------+   |   +------------------+
| ハイセラポンプ 1-3 |<--+-->| ACM0 (RS-232C)      |<--+-->| ハイセラポンプ 4-6 |<--+-->| ACM1 (RS-232C)     |
+------------------+       +---------------------+       +---------------------+       +------------------+
                        |                             |                             |
+------------------+   |   +---------------------+   |   +---------------------+   |   +------------------+
| シリンジポンプ 1-6  |<--+-->| USB0 (RS-232C)      |<--+-->| (未使用)            |   |   | (未使用)           |
+------------------+       +---------------------+       +---------------------+       +------------------+
                         |                             |                             |
+------------------+   |   +---------------------+   |   +---------------------+   |   +------------------+
| Arduino (モーター)  |<--+-->| (未接続)            |<--+-->| (未接続)            |   |   | (未接続)           |
+------------------+       +---------------------+       +---------------------+       +------------------+
                         |
+------------------+   |
| カメラ (PiCamera2/CV2) |<--+
+------------------+
```

-   **クライアント**: ユーザーが操作を行うWebブラウザ。サーバーから配信されるHTML/CSS/JavaScriptによってUIが構築され、APIを介してバックエンドと通信します。
-   **Flask Webサーバー (`app.py`)**: システムの中核。クライアントへのUI提供、APIリクエストの処理、および各ハードウェアデバイスとのシリアル通信を担います。
-   **デバイス (ポンプ/カメラ/Arduino)**: 物理的な制御対象。それぞれが個別の通信プロトコルを持ち、Flaskサーバーからのコマンドに応じて動作します。

## 3. モジュール構造

システムは以下のモジュール構造に従って整理されています：

```
RaspberryPi_Camera/
├── config.py                    # 設定管理（環境変数対応）
├── app.py                       # Flaskアプリケーションのエントリーポイント
├── camera/                      # カメラ制御モジュール
│   ├── __init__.py
│   └── camera_manager.py        # CameraManagerクラス
├── pump_controllers/            # ポンプ制御モジュール
│   ├── __init__.py
│   ├── serial_manager.py        # SerialManager基底クラス
│   ├── hysera_pump.py          # HyseraPumpControllerクラス
│   └── syringe_pump.py         # SyringePumpManagerクラス
├── utils/                       # ユーティリティ関数
│   ├── __init__.py
│   ├── command_builder.py      # コマンド生成
│   └── response_parser.py      # レスポンス解析
├── api/                         # API エンドポイント（開発中）
├── templates/                   # HTMLテンプレート
│   ├── index.html
│   ├── pump_control.html
│   └── syringe_pump.html
├── static/                      # 静的ファイル
│   ├── css/
│   │   └── pump_control.css
│   └── js/
│       └── pump_control.js
└── command.py                   # レガシーシリンジポンプコントローラー
```

### 3.1. `config.py` - 設定管理

すべてのアプリケーション設定を一元管理します。

#### 主要な設定項目

-   **ログ出力制御**: `DEBUG_SERIAL_LOG`, `DEBUG_LEAK_LOG`, `DEBUG_SYSTEM_LOG`, `DEBUG_STREAM_LOG`
-   **カメラ設定**: `CAM_WIDTH`, `CAM_HEIGHT`, `CAM_FPS`
-   **FFmpegストリーミング設定**: `HLS_SEGMENT_DURATION`, `HLS_PLAYLIST_SIZE`
-   **シリアルポート設定**: 
    -   ハイセラポンプ: `SERIAL_PORT_1`, `SERIAL_PORT_2`
    -   シリンジポンプ: `SYRINGE_SERIAL_PORT`
-   **Flaskサーバー設定**: `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG`

#### 環境変数サポート

設定値は環境変数から読み込むことができます：
```bash
export HYSERA_PORT_1=/dev/ttyACM0
export HYSERA_PORT_2=/dev/ttyACM1
export SYRINGE_PORT=/dev/ttyUSB0
export FLASK_PORT=8080
```

### 3.2. `camera/camera_manager.py` - カメラ管理

`CameraManager`クラスがカメラの初期化、フレーム取得、ストリーミング生成を管理します。

#### 主要な機能

-   **自動環境判別**: Raspberry Pi環境では`Picamera2`、PC環境では`OpenCV`を自動選択
-   **ハードウェアJPEGエンコード**: Picamera2使用時、ハードウェアエンコーダーを活用
-   **MJPEGストリーミング**: `generate_mjpeg_stream()`メソッドでリアルタイム映像を生成
-   **動的設定変更**: `update_settings()`で解像度・FPSを実行時に変更可能
-   **カメラ再起動**: `restart()`メソッドで安全にカメラを再初期化

#### 使用例

```python
from camera import CameraManager

camera_mgr = CameraManager()
if camera_mgr.initialize():
    frame = camera_mgr.get_frame()
    camera_mgr.update_settings(width=1280, height=720, fps=30)
```

### 3.3. `pump_controllers/` - ポンプ制御モジュール

#### 3.3.1. `serial_manager.py` - シリアル通信基底クラス

`SerialManager`クラスは、すべてのシリアル通信デバイスの基底クラスです。

-   **スレッドセーフ**: `threading.Lock`による排他制御
-   **自動バッファ管理**: `clear_buffer()`で古いデータを自動クリア
-   **タイムアウト付き受信**: `wait_for_response()`でレスポンスを待機
-   **接続状態管理**: `is_connected()`で接続状態を確認

#### 3.3.2. `hysera_pump.py` - ハイセラポンプ制御

`HyseraPumpController`クラスが最大6台のハイセラポンプを制御します。

-   **2ポート管理**: ACM0（ポンプ1-3）、ACM1（ポンプ4-6）
-   **漏液検出**: `check_leak_detection()`で漏液センサーを監視
-   **コマンド送信**: `send_command()`で基本コマンド、`send_command_with_response()`でレスポンス付き
-   **レスポンス解析**: `utils.response_parser`を使用して自動解析

#### 3.3.3. `syringe_pump.py` - シリンジポンプ管理

`SyringePumpManager`クラスが最大6台のシリンジポンプを管理します。

-   **コントローラー管理**: 各ポンプに対応する`SyringePumpController`インスタンスを保持
-   **統一インターフェース**: `get_controller(pump_index)`で個別コントローラーを取得

### 3.4. `utils/` - ユーティリティモジュール

#### 3.4.1. `command_builder.py` - コマンド生成

-   `calc_checksum()`: チェックサム計算
-   `build_pump_command()`: ポンプ制御コマンド生成
-   `format_command_bytes()`: コマンドバイトの可読性向上

#### 3.4.2. `response_parser.py` - レスポンス解析

-   `decode_rpm_from_status_byte()`: RPM値のデコード
-   `verify_checksum()`: チェックサム検証
-   `parse_pump_response()`: レスポンスタイプ別の解析

### 3.5. `app.py` - メインアプリケーション (Flask)

システムのエントリーポイントとなるFlaskアプリケーションです。

#### 主要な機能

-   **Webサーバー機能**: Flaskフレームワークを使用し、3つのHTMLページとAPIエンドポイントを提供
-   **モジュールの統合**: 各モジュールをインポートしてシステム全体を協調動作させる
-   **APIエンドポイント**:
    -   `/`: カメラストリーミングのメインページを表示
    -   `/video_feed`: MJPEGストリームを配信
    -   `/api/status`: カメラとシリアルポートの初期化状態を返す
    -   `/api/snapshot`: 現在のカメラフレームをJPEG画像として返す
    -   `/api/restart_camera`: カメラを再初期化する
    -   `/api/pump_control`: ハイセラポンプにコマンドを送信する
    -   `/api/get_current`: ハイセラポンプから電流値を取得する
    -   `/api/get_rpm`: ハイセラポンプから回転数を取得する
    -   `/api/get_total_revolutions`: トータル回転数を取得する
    -   `/api/check_leak_status`: 漏液状態を確認する
    -   `/api/reset_leak`: 漏液検出状態をリセットする
    -   `/api/syringe_pump_control`: シリンジポンプにコマンドを送信する

### 3.6. `command.py` - レガシーシリンジポンプ制御モジュール

シリンジポンプとの通信コマンドを生成・送信するためのクラスを定義しています（後方互換性のため保持）。

-   **`SyringePumpController` クラス**:
    -   `__init__(self, pump_number, serial_port)`: ポンプ番号と、通信に使用する`pyserial`のインスタンスを受け取ります。
    -   `create_command(self, command, address)`: シリンジポンプのプロトコルに従って、送信用のバイトシーケンスを構築します。
        -   **フレーム形式**: `STX(0x02) + ADDR + 0x31 + COMMAND + ETX(0x03) + Checksum`
        -   **Checksum**: STXからETXまで、全てのバイトのXOR（排他的論理和）です。
    -   `send_command(self, command, address)`: 生成したコマンドをシリアルポートに書き込みます。

**注**: このクラスは`pump_controllers.SyringePumpManager`によってラップされ、統一されたインターフェースで使用されます。

### 3.7. フロントエンド - テンプレートと静的ファイル

#### 3.7.1. `templates/index.html` - カメラストリーミングページ

メインのカメラストリーミングページのUIを定義します。

-   **構造**: ヘッダー、ナビゲーションリンク、システム状態表示、ビデオコンテナ、操作ボタン、スナップショット表示エリア
-   **JavaScriptによる非同期通信**:
    -   `fetch` APIを使用してバックエンドAPIを呼び出し
    -   状態確認、スナップショット取得、カメラ再起動などの機能を提供

#### 3.7.2. `templates/pump_control.html` - ポンプ制御ページ

ハイセラポンプの制御UIを提供します。

-   **外部CSS**: `static/css/pump_control.css`
-   **外部JavaScript**: `static/js/pump_control.js`
-   **モジュール化された構造**: HTML/CSS/JavaScriptが明確に分離

#### 3.7.3. `static/css/pump_control.css` - ポンプ制御スタイル

ポンプ制御ページの統一されたスタイルシートです。

-   **論理的セクション**: Reset, Layout, Components, Responsive
-   **改善された命名**: `.pump-card`, `.control-group`など
-   **レスポンシブデザイン**: モバイル、タブレット、デスクトップ対応

#### 3.7.4. `static/js/pump_control.js` - ポンプ制御ロジック

ポンプ制御の全ロジックをクラスベースで実装しています。

-   **PumpController**: ポンプ操作と状態管理
-   **StreamingManager**: カメラストリーミングとオーバーレイ制御
-   **UIManager**: UI更新とChoices.js初期化
-   **APIManager**: バックエンドAPI通信
-   **StorageManager**: localStorage操作

#### 3.7.5. `templates/syringe_pump.html` - シリンジポンプ制御ページ

シリンジポンプの制御UIを提供します。

### 3.8. `arduino/kousoku5/kousoku5.ino` - ステッピングモーター制御ファームウェア

Arduino Mega (または互換機) で動作する、最大3台のステッピングモーターを制御するためのファームウェアです。**`app.py`のハイセラポンプ制御とは異なる、独立したコンポーネントです。**

-   **高度なモーター制御**:
    -   **タイマー割り込み駆動**: 3つのハードウェアタイマー（TIMER3, 4, 5）を使用し、マイクロ秒単位で正確なステップパルスを生成します。これにより、メインループの処理に影響されずに安定したモーター駆動が可能です。
    -   **台形加減速制御**: `useTrapezoid`フラグが有効な場合、モーターの開始・停止時に滑らかな加減速を行います。目標速度や移動ステップ数から、加速・等速・減速の各フェーズを自動で計算し、滑らかな動作を実現します。
    -   **動的な速度変更**: モーター動作中にも、シリアルコマンドで目標速度をリアルタイムに変更できます。
-   **センサー監視**:
    -   **漏液センサー**: 3つのデジタルピンで漏液を監視します。
    -   **電流センサー**: 3つのアナログピンでモーターの消費電流を監視し、移動平均を計算して脱調検知などに利用できます。
-   **シリアル通信**:
    -   `app.py`のハイセラポンプと同様の`STX(0x02)`で始まる11バイトの固定長コマンドを受け付けます。
    -   `C`コマンドで要求されると、計算済みの平均電流値をシリアルで返信します。

## 4. 通信プロトコル

### 4.1. ハイセラポンプ / Arduino (`app.py` / `kousoku5.ino`)

両者は類似した11バイトの固定長コマンド形式を使用します。

-   **送信フォーマット**:
    -   `[0]` STX (0x02)
    -   `[1]` ポンプ番号 (`'1'`-`'3'`)
    -   `[2]` アクションコマンド (ASCII文字, e.g., `'M'`, `'S'`)
    -   `[3-8]` 値 (ASCII数字6桁, e.g., `"001000"`)
    -   `[9]` チェックサム (byte[1]からbyte[8]までのXOR)
    -   `[10]` ETX (0x03)

### 4.2. シリンジポンプ (`command.py`)

-   **送信フォーマット**:
    -   `[0]` STX (0x02)
    -   `[1]` ポンプアドレス (ASCII文字, `'1'`-`'6'`)
    -   `[2]` 固定値 (0x31)
    -   `[...]` コマンド文字列 (ASCII, 可変長, e.g., `"ZR"`, `"D3000"`)
    -   `[...]` ETX (0x03)
    -   `[...]` チェックサム (STXからETXまでの全バイトのXOR)

## 5. セットアップと実行方法

基本的な手順は`README.md`に記載されています。

### 5.1. 基本セットアップ

1.  **ハードウェア接続**: Raspberry Piにカメラ、各種ポンプ（対応するシリアル変換器経由）、Arduinoを接続します。

2.  **依存関係インストール**: `requirements.txt` に基づいてPythonライブラリをインストールします。
    ```bash
    pip install -r requirements.txt
    ```

3.  **ファームウェア書き込み**: `arduino/kousoku5/kousoku5.ino` をArduino IDEで開き、Arduino Megaに書き込みます。

### 5.2. 環境設定

環境変数または`config.py`を編集して設定をカスタマイズできます：

```bash
# シリアルポート設定
export HYSERA_PORT_1=/dev/ttyACM0
export HYSERA_PORT_2=/dev/ttyACM1
export SYRINGE_PORT=/dev/ttyUSB0

# Flaskサーバー設定
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
export FLASK_DEBUG=False
```

### 5.3. サーバー起動

```bash
# 基本起動
python app.py

# カスタムポート指定
python app.py --port 8080

# デバッグモード
python app.py --debug

# シリアルポート指定
python app.py --serial-port-1 /dev/ttyACM0 --serial-port-2 /dev/ttyACM1
```

### 5.4. 開発環境のセットアップ

モジュール化されたコードベースで開発する場合：

```bash
# 仮想環境の作成
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 開発用依存関係のインストール
pip install -r requirements.txt

# テスト実行（将来的に実装予定）
pytest tests/
```

## 6. アーキテクチャの利点

### 6.1. 保守性の向上

-   **関心の分離**: カメラ、ポンプ、APIが独立したモジュールに分離され、各部分を個別に変更可能
-   **クラスベース設計**: オブジェクト指向設計により、状態管理と動作がカプセル化
-   **設定の外部化**: `config.py`により、コード変更なしで設定を調整可能

### 6.2. テスト容易性

-   **モジュール化**: 各モジュールを独立してテスト可能
-   **依存性注入**: SerialManagerなどの基底クラスによりモック化が容易
-   **明確なインターフェース**: 各クラスの責務が明確で単体テストが書きやすい

### 6.3. 拡張性

-   **新しいポンプタイプの追加**: `SerialManager`を継承して新しいコントローラーを実装
-   **新しいカメラデバイスの対応**: `CameraManager`を拡張して新しいバックエンドを追加
-   **APIの追加**: `api/`ディレクトリに新しいエンドポイントを追加

### 6.4. コードの再利用

-   **ユーティリティ関数**: `utils/`モジュールの関数は複数の場所で再利用
-   **基底クラス**: `SerialManager`は異なるデバイスタイプで共通処理を提供
-   **レスポンスパーサー**: 標準化されたレスポンス解析ロジック

## 7. 注意点と考察

### 7.1. 技術的考慮事項

-   **Arduinoとの連携**: `kousoku5.ino`と直接通信するためのAPIエンドポイントは現在実装されていません。ハイセラポンプ用の`/api/pump_control`がArduinoのプロトコルと互換性があるため、このAPIを流用してArduinoを制御することを想定しています。

-   **シリアルポート設定**: `config.py`はWindows/Linux両方に対応しており、環境変数での上書きも可能です。

-   **名前衝突の解決**: 元々`serial/`ディレクトリを使用していましたが、Pythonの`pyserial`ライブラリとの名前衝突を避けるため、`pump_controllers/`にリネームしました。

### 7.2. 今後の改善点

-   **エラーハンドリング**: より堅牢な再接続処理とロギング機構の実装
-   **セキュリティ**: 認証機能の追加（Basic認証、JWT、OAuth等）
-   **単体テスト**: `tests/`ディレクトリに各モジュールのテストを追加
-   **API モジュール化**: `api/`ディレクトリへのAPIエンドポイント分離（開発中）
-   **ドキュメント生成**: Sphinxなどによる自動APIドキュメント生成
-   **型ヒント**: Python型アノテーションの追加でIDEサポートの向上

### 7.3. パフォーマンス

-   **スレッドセーフ**: すべてのシリアル通信は`threading.Lock`で保護
-   **バッファ管理**: 自動バッファクリアによるデータの新鮮性保証
-   **ハードウェアエンコード**: Picamera2使用時、ハードウェアJPEGエンコーダーを活用

### 7.4. 互換性

-   **後方互換性**: レガシーコード（`command.py`）は保持され、新しいモジュールからラップして使用
-   **環境対応**: Raspberry Pi、PC（Windows/Linux）の両方で動作
-   **Pythonバージョン**: Python 3.7以上を推奨

## 8. モジュール間の依存関係

```
app.py
├── config.py
├── camera.CameraManager
│   ├── config (設定値)
│   └── cv2 / picamera2 (カメラバックエンド)
├── pump_controllers.HyseraPumpController
│   ├── pump_controllers.SerialManager (基底クラス)
│   ├── utils.command_builder (コマンド生成)
│   └── utils.response_parser (レスポンス解析)
├── pump_controllers.SyringePumpManager
│   ├── pump_controllers.SerialManager (基底クラス)
│   └── command.SyringePumpController (レガシー)
└── utils (共通ユーティリティ)
```

---
このドキュメントは、リファクタリング後のプロジェクト構造を反映して更新されました（2025年10月24日）。
