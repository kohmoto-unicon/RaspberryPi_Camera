# 📹 ラズパイカメラストリーミングWebサーバー

ラズパイ公式カメラモジュールを使用したリアルタイムストリーミングWebサーバーです。

## 🚀 機能

- **リアルタイムストリーミング**: MJPEG形式でのライブビデオ配信
- **スナップショット機能**: 静止画の撮影とダウンロード
- **カメラ制御**: カメラの再起動と状態監視
- **レスポンシブUI**: モバイル対応の美しいインターフェース
- **RESTful API**: プログラムからの制御が可能
- **オフライン対応**: インターネット接続不要でセットアップ可能

## 📋 システム要件

- **ハードウェア**: Raspberry Pi（3/4/Zero等）
- **OS**: Raspberry Pi OS（Bullseye以上推奨）
- **カメラ**: ラズパイ公式カメラモジュール
- **Python**: 3.7以上
- **メモリ**: 512MB以上推奨

## 🔧 セットアップ

### 1. カメラモジュールの接続

1. ラズパイの電源を切る
2. カメラモジュールをCSIポートに接続
3. カメラケーブルの向きに注意（青い面がラズパイ側）
4. ラズパイの電源を入れる

### 2. カメラの有効化

```bash
# カメラを有効化
sudo raspi-config

# または、config.txtを直接編集
echo "camera_auto_detect=1" | sudo tee -a /boot/config.txt
echo "dtoverlay=imx219" | sudo tee -a /boot/config.txt  # Pi Camera Module v2
# または
echo "dtoverlay=ov5647" | sudo tee -a /boot/config.txt  # Pi Camera Module v1

# 再起動
sudo reboot
```

### 3. オフライン環境でのセットアップ

#### 3-1. パッケージの準備（インターネット接続可能な環境で実行）

```bash
# パッケージダウンロードスクリプトを実行
python3 download_packages.py

# ダウンロードされたパッケージをUSBメモリにコピー
cp -r packages /path/to/usb/
```

#### 3-2. ラズパイでのセットアップ

```bash
# プロジェクトファイルをラズパイにコピー
# USBメモリからパッケージをコピー
cp -r /path/to/usb/packages ./

# セットアップスクリプトを実行
python3 setup.py
```

### 4. オンライン環境でのセットアップ

```bash
# セットアップスクリプトを実行（自動でパッケージをダウンロード）
python3 setup.py
```

### 5. 手動セットアップ（セットアップスクリプトを使用しない場合）

```bash
# システム依存関係をインストール
sudo apt update
sudo apt install -y python3-pip python3-venv libatlas-base-dev

# 仮想環境を作成
python3 -m venv venv
source venv/bin/activate

# Python依存関係をインストール
pip install --upgrade pip
pip install -r requirements.txt
```

## 🚀 使用方法

### 基本的な起動

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# アプリケーションを起動
python app.py
```

### 起動スクリプトを使用

```bash
# 実行権限を付与
chmod +x start.sh

# 起動
./start.sh
```

### systemdサービスとして登録

```bash
# サービスファイルをコピー
sudo cp raspi-camera-streaming.service /etc/systemd/system/

# systemdを再読み込み
sudo systemctl daemon-reload

# サービスを有効化
sudo systemctl enable raspi-camera-streaming.service

# サービスを起動
sudo systemctl start raspi-camera-streaming.service

# 状態確認
sudo systemctl status raspi-camera-streaming.service
```

## 🌐 アクセス方法

アプリケーション起動後、以下のURLでアクセスできます：

- **メインページ**: http://localhost:5000
- **ストリーミング**: http://localhost:5000/video_feed
- **API状態確認**: http://localhost:5000/api/status
- **スナップショット**: http://localhost:5000/api/snapshot

### 外部からのアクセス

ラズパイのIPアドレスを使用して外部からアクセス：

```bash
# IPアドレスを確認
hostname -I

# 例: http://192.168.1.100:5000
```

## 📡 API エンドポイント

### GET /api/status
カメラの状態を取得

**レスポンス例:**
```json
{
  "camera_initialized": true,
  "timestamp": 1640995200.0
}
```

### GET /api/snapshot
現在のフレームのスナップショットを取得

**レスポンス:** JPEG画像

### POST /api/restart_camera
カメラを再起動

**レスポンス例:**
```json
{
  "success": true,
  "message": "カメラを再起動しました"
}
```

## 🔧 設定

### カメラ設定の変更

`app.py`の`initialize_camera()`関数でカメラ設定を変更できます：

```python
# 解像度を変更
config = camera.create_preview_configuration(
    main={"size": (1280, 720)},  # 720p
    encode="main"
)

# フレームレートを変更
config = camera.create_preview_configuration(
    main={"size": (640, 480)},
    encode="main",
    controls={"FrameDurationLimits": (33333, 33333)}  # 30FPS
)
```

### ポート番号の変更

```python
# app.pyの最後の行を変更
app.run(host='0.0.0.0', port=8080, debug=False, threaded=True)
```

## 🛠️ トラブルシューティング

### カメラが認識されない

```bash
# カメラデバイスを確認
ls -la /dev/video*

# カメラ情報を確認
vcgencmd get_camera

# カメラテスト
raspistill -o test.jpg
```

### パッケージのインストールエラー

```bash
# システムパッケージを更新
sudo apt update && sudo apt upgrade

# 依存関係を再インストール
sudo apt install -y python3-dev libatlas-base-dev
```

### メモリ不足エラー

```bash
# スワップファイルを有効化
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# CONF_SWAPSIZE=100 を CONF_SWAPSIZE=512 に変更
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### パフォーマンスの最適化

1. **解像度を下げる**: 640x480に設定
2. **フレームレートを下げる**: 15FPSに設定
3. **JPEG品質を下げる**: 60%に設定

```python
# app.pyで設定変更
config = camera.create_preview_configuration(
    main={"size": (640, 480)},
    encode="main",
    controls={"FrameDurationLimits": (66666, 66666)}  # 15FPS
)

# JPEG品質を変更
ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
```

## 📁 プロジェクト構造

```
raspi-camera-streaming/
├── app.py                 # メインアプリケーション
├── requirements.txt       # Python依存関係
├── setup.py              # セットアップスクリプト（オフライン対応）
├── download_packages.py   # パッケージダウンロードスクリプト
├── start.sh              # 起動スクリプト
├── raspi-camera-streaming.service  # systemdサービスファイル
├── packages/             # ダウンロードされたパッケージ（オフライン用）
├── templates/
│   └── index.html        # Webインターフェース
├── OFFLINE_INSTALL_GUIDE.md  # オフラインインストールガイド
├── INSTALL_GUIDE.md      # インストールガイド
└── README.md             # このファイル
```

## 🤝 貢献

バグ報告や機能要望は、GitHubのIssuesでお知らせください。

## 📄 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 謝辞

- [Picamera2](https://github.com/raspberrypi/picamera2) - ラズパイカメラライブラリ
- [Flask](https://flask.palletsprojects.com/) - Webフレームワーク
- [OpenCV](https://opencv.org/) - コンピュータビジョンライブラリ

---

**注意**: このアプリケーションは開発・テスト目的で作成されています。本番環境での使用には、適切なセキュリティ対策を講じてください。 