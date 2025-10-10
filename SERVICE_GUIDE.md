# サービス管理ガイド

このドキュメントでは、ラズパイカメラストリーミングアプリケーション（`app.py`）のサービス管理について説明します。

## 目次

1. [概要](#概要)
2. [自動起動について](#自動起動について)
3. [コマンド操作](#コマンド操作)
4. [トラブルシューティング](#トラブルシューティング)
5. [設定ファイル](#設定ファイル)

---

## 概要

このアプリケーションは、systemdサービスとして登録されており、ラズパイOS起動時に自動的に起動します。

### サービス名
```
raspi-camera-streaming.service
```

### サービスの機能
- OS起動時に自動起動
- クラッシュ時の自動再起動（10秒後）
- バックグラウンドでの動作
- システムログへの記録

---

## 自動起動について

### OS起動時の動作フロー

1. **ラズパイOS起動**
2. **ネットワーク初期化** (`network.target`の完了を待機)
3. **app.pyの自動起動** (systemdサービスとして)
4. **カメラとシリアル通信の初期化**
5. **Webサーバー起動** (ポート5000でアクセス可能)

### 自動起動の確認方法

OS起動後、サービスが自動起動しているか確認：

```bash
app status
```

または

```bash
sudo systemctl status raspi-camera-streaming.service
```

**正常な場合の表示例：**
```
● raspi-camera-streaming.service - Raspberry Pi Camera Streaming Server (Offline)
     Loaded: loaded (...; enabled; ...)
     Active: active (running) since ...
```

- `Loaded: ... enabled` → 自動起動が有効
- `Active: active (running)` → サービスが動作中

### 自動起動の有効化/無効化

#### 自動起動を有効化（デフォルトで有効）
```bash
app enable
```

または

```bash
sudo systemctl enable raspi-camera-streaming.service
```

#### 自動起動を無効化
```bash
app disable
```

または

```bash
sudo systemctl disable raspi-camera-streaming.service
```

**注意**: 無効化しても、現在実行中のサービスは停止しません。

---

## コマンド操作

### 短縮コマンド `app`（推奨）

最も簡単な操作方法です。どこからでも実行できます。

#### 基本コマンド

| コマンド | 説明 | 実行例 |
|---------|------|--------|
| `app start` | サービスを起動 | `app start` |
| `app stop` | サービスを停止 | `app stop` |
| `app restart` | サービスを再起動 | `app restart` |
| `app status` | 状態を確認 | `app status` |
| `app enable` | 自動起動を有効化 | `app enable` |
| `app disable` | 自動起動を無効化 | `app disable` |
| `app log` | リアルタイムログ表示 | `app log` |

#### 使用例

**サービスの起動**
```bash
app start
```

**サービスの停止**
```bash
app stop
```

**コードを変更した後の再起動**
```bash
app restart
```

**現在の状態確認**
```bash
app status
```

**リアルタイムでログを確認**
```bash
app log
# Ctrl+C で終了
```

### systemctlコマンド（詳細な操作）

より詳細な制御が必要な場合は、systemctlコマンドを直接使用できます。

#### 基本操作

**起動**
```bash
sudo systemctl start raspi-camera-streaming.service
```

**停止**
```bash
sudo systemctl stop raspi-camera-streaming.service
```

**再起動**
```bash
sudo systemctl restart raspi-camera-streaming.service
```

**状態確認**
```bash
sudo systemctl status raspi-camera-streaming.service
```

**自動起動の有効化**
```bash
sudo systemctl enable raspi-camera-streaming.service
```

**自動起動の無効化**
```bash
sudo systemctl disable raspi-camera-streaming.service
```

**停止と同時に自動起動を無効化**
```bash
sudo systemctl disable --now raspi-camera-streaming.service
```

#### ログの確認

**最新のログを表示**
```bash
sudo journalctl -u raspi-camera-streaming.service -n 50
```

**リアルタイムでログを監視**
```bash
sudo journalctl -u raspi-camera-streaming.service -f
```

**本日のログのみ表示**
```bash
sudo journalctl -u raspi-camera-streaming.service --since today
```

**エラーのみ表示**
```bash
sudo journalctl -u raspi-camera-streaming.service -p err
```

---

## トラブルシューティング

### サービスが起動しない場合

#### 1. サービスの状態を確認
```bash
app status
```

エラーメッセージを確認してください。

#### 2. 詳細なログを確認
```bash
app log
```

または

```bash
sudo journalctl -u raspi-camera-streaming.service -n 100
```

#### 3. よくある問題と解決方法

**問題: カメラが初期化できない**
```
エラー: カメラ初期化失敗
```

解決策：
- カメラモジュールが正しく接続されているか確認
- カメラケーブルの接続を確認
- `vcgencmd get_camera` でカメラが認識されているか確認

**問題: シリアルポートが開けない**
```
エラー: シリアル通信初期化エラー
```

解決策：
- USBデバイスが接続されているか確認
- デバイスファイルの存在確認: `ls -la /dev/ttyACM*` または `ls -la /dev/ttyUSB*`
- ユーザー権限の確認: `sudo usermod -a -G dialout kohmoto`

**問題: ポート5000が既に使用されている**
```
エラー: Address already in use
```

解決策：
```bash
# ポート5000を使用しているプロセスを確認
sudo lsof -i :5000

# 既存のプロセスを終了してから再起動
app restart
```

### サービスを完全にリセットする

```bash
# サービスを停止
app stop

# サービスを無効化
app disable

# systemdの設定をリロード
sudo systemctl daemon-reload

# サービスを再度有効化
app enable

# サービスを起動
app start
```

### 手動でアプリを実行（デバッグ用）

サービスを停止して、手動で実行することもできます：

```bash
# サービスを停止
app stop

# プロジェクトディレクトリに移動
cd /home/kohmoto/projects/RaspberryPi_Camera

# 仮想環境をアクティベート
source venv/bin/activate

# アプリを手動実行（デバッグモード）
python app.py --debug
```

終了するには `Ctrl+C` を押します。

---

## 設定ファイル

### サービス設定ファイル

**場所**: `/etc/systemd/system/raspi-camera-streaming.service`

**内容**:
```ini
[Unit]
Description=Raspberry Pi Camera Streaming Server (Offline)
After=network.target

[Service]
Type=simple
User=kohmoto
WorkingDirectory=/home/kohmoto/projects/RaspberryPi_Camera
ExecStart=/home/kohmoto/projects/RaspberryPi_Camera/venv/bin/python /home/kohmoto/projects/RaspberryPi_Camera/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**設定の説明**:
- `After=network.target`: ネットワーク初期化後に起動
- `User=kohmoto`: ユーザー`kohmoto`として実行
- `Restart=always`: クラッシュ時に自動再起動
- `RestartSec=10`: 再起動までの待機時間（10秒）

### サービス設定を変更した場合

設定ファイルを編集した後は、必ず以下を実行：

```bash
# 設定をリロード
sudo systemctl daemon-reload

# サービスを再起動
app restart
```

### 短縮コマンドスクリプト

**場所**: `/usr/local/bin/app`

このスクリプトは `app start` などの短縮コマンドを提供します。

---

## よく使うコマンド一覧

### 日常的な操作

```bash
# サービスの状態確認
app status

# サービスの起動
app start

# サービスの停止
app stop

# サービスの再起動（コード変更後など）
app restart

# リアルタイムログの確認
app log
```

### 設定変更時

```bash
# コードを変更した場合
app restart

# サービス設定ファイルを変更した場合
sudo systemctl daemon-reload
app restart
```

### 自動起動の管理

```bash
# 自動起動を有効化
app enable

# 自動起動を無効化
app disable

# 自動起動の状態確認
systemctl is-enabled raspi-camera-streaming.service
```

### トラブル時

```bash
# 詳細なログ確認
app log

# サービスの完全な状態確認
sudo systemctl status raspi-camera-streaming.service -l

# システムログの確認
sudo journalctl -xe
```

---

## 補足情報

### Webアクセス

サービスが起動している場合、以下のURLでアクセスできます：

- **メインページ**: http://localhost:5000
- **ポンプ制御**: http://localhost:5000/pump_control
- **シリンジポンプ**: http://localhost:5000/syringe_pump
- **ビデオフィード**: http://localhost:5000/video_feed

### 他のマシンからのアクセス

ラズパイのIPアドレスを確認：
```bash
hostname -I
```

他のマシンから:
```
http://[ラズパイのIPアドレス]:5000
```

例: `http://192.168.1.100:5000`

### パフォーマンス情報

サービスのリソース使用状況を確認：
```bash
sudo systemctl status raspi-camera-streaming.service
```

CPU時間やメモリ使用量が表示されます。

---

## まとめ

- **OS起動時**: アプリは自動的に起動します
- **基本操作**: `app start`, `app stop`, `app restart`, `app status`
- **ログ確認**: `app log`
- **問題発生時**: ログを確認して、必要に応じてサービスを再起動

困ったときは、まず `app status` と `app log` でログを確認してください。

---

**作成日**: 2025-10-10  
**バージョン**: 1.0

