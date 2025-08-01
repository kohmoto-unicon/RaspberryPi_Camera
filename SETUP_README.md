# 🔧 setup.py 使用方法ガイド

このファイルは、ラズパイカメラストリーミングWebサーバーのセットアップスクリプト（`setup.py`）の使用方法を説明します。

## 📋 概要

`setup.py`は、ラズパイでカメラストリーミングWebサーバーを自動的にセットアップするためのスクリプトです。オフライン環境にも対応しており、USBメモリからパッケージをインストールできます。

## 🚀 基本的な使用方法

### 1. オンライン環境での実行

```bash
# プロジェクトディレクトリに移動
cd /path/to/raspi-camera-streaming

# セットアップスクリプトを実行
python3 setup.py
```

### 2. オフライン環境での実行

```bash
# USBメモリからパッケージをコピー
cp -r /path/to/usb/packages ./

# セットアップスクリプトを実行
python3 setup.py
```

## 🔍 セットアップスクリプトの機能

### 自動実行される処理

1. **システム要件チェック**
   - Python 3.7以上のバージョン確認
   - OSがLinux（ラズパイOS）かどうかの確認

2. **USBメモリ検索**
   - `/media/pi/*`, `/media/*`, `/mnt/usb*`, `/mnt/*` を自動検索
   - `.whl`, `.tar.gz`, `.zip` ファイルを自動認識

3. **システム依存関係確認**
   - `python3`, `python3-pip`, `python3-venv` の存在確認
   - 不足しているパッケージの報告

4. **仮想環境セットアップ**
   - `python3 -m venv venv` で仮想環境を作成
   - アクティベート方法の表示

5. **Python依存関係インストール**
   - USBメモリからパッケージを自動検索・インストール
   - 必要なパッケージ：
     - Flask (Webフレームワーク)
     - opencv-python (画像処理)
     - picamera2 (ラズパイカメラ)
     - numpy (数値計算)
     - Pillow (画像処理)

6. **カメラモジュールチェック**
   - `/dev/video0` デバイスの存在確認
   - `vcgencmd get_camera` でカメラ情報を取得

7. **起動スクリプト作成**
   - `start.sh` ファイルを作成（実行権限付与）
   - 仮想環境をアクティベートしてアプリを起動するスクリプト

8. **systemdサービスファイル作成**
   - `raspi-camera-streaming.service` ファイルを作成
   - システム起動時に自動でアプリを起動するための設定

9. **オフライン用ファイル作成**
   - `requirements_offline.txt` - オフライン用依存関係リスト
   - `OFFLINE_INSTALL_GUIDE.md` - オフラインインストールガイド

## 📦 必要なパッケージファイル

オフライン環境で使用する場合、以下のパッケージファイルをUSBメモリに配置してください：

### 主要パッケージ
- **Flask** - Webフレームワーク
- **opencv-python** - 画像処理ライブラリ
- **picamera2** - ラズパイカメラライブラリ
- **numpy** - 数値計算ライブラリ
- **Pillow** - 画像処理ライブラリ

### 依存関係パッケージ
- **Werkzeug** - Flaskの依存関係
- **Jinja2** - テンプレートエンジン
- **MarkupSafe** - セキュリティライブラリ
- **itsdangerous** - 署名ライブラリ
- **click** - コマンドラインインターフェース
- **blinker** - シグナルライブラリ

## 🔧 パッケージファイルの準備方法

### 方法1: 自動ダウンロード（推奨）

インターネット接続可能な環境で：

```bash
# パッケージダウンロードスクリプトを実行
python3 download_packages.py

# ダウンロードされたパッケージをUSBメモリにコピー
cp -r packages /path/to/usb/
```

### 方法2: 手動ダウンロード

1. https://pypi.org/ にアクセス
2. 各パッケージのページで「Files」セクションを確認
3. ラズパイ用の.whlファイルをダウンロード：
   - アーキテクチャ: `aarch64` または `armv7l`
   - Python: `cp39` (Python 3.9用)
   - 例: `Flask-2.3.3-py3-none-any.whl`

## 📁 実行例

### 成功時の出力例

```
🚀 ラズパイカメラストリーミング セットアップ（オフライン版）
============================================================

🔍 システム要件をチェック中...
✅ Python 3.9.2

🔍 USBメモリからパッケージを検索中...
📁 検索中: /media/pi/USB_DRIVE
✅ 15個のパッケージファイルが見つかりました
   📦 Flask-2.3.3-py3-none-any.whl
   📦 opencv_python-4.8.1.78-cp39-cp39-linux_aarch64.whl
   📦 picamera2-0.3.12-py3-none-any.whl
   📦 numpy-1.24.3-cp39-cp39-linux_aarch64.whl
   📦 Pillow-10.0.1-cp39-cp39-linux_aarch64.whl
   ... 他 10個

📦 システム依存関係をインストール中（オフライン）...
✅ python3 は既にインストールされています
✅ python3-pip は既にインストールされています
✅ python3-venv は既にインストールされています

🐍 仮想環境をセットアップ中...

🔧 仮想環境作成...
✅ 仮想環境作成 完了
✅ 仮想環境が作成されました: source venv/bin/activate

📦 Python依存関係をインストール中（オフライン）...
⚠️  オフライン環境のため、pip更新をスキップします

🔍 Flask を検索中...
📦 インストール: Flask-2.3.3-py3-none-any.whl

🔧 Flask インストール...
✅ Flask インストール 完了

🔍 opencv-python を検索中...
📦 インストール: opencv_python-4.8.1.78-cp39-cp39-linux_aarch64.whl

🔧 opencv-python インストール...
✅ opencv-python インストール 完了

📊 インストール結果: 5/5 パッケージ

📝 オフライン用requirements.txtを作成中...
✅ requirements_offline.txt が作成されました

📖 オフラインインストールガイドを作成中...
✅ OFFLINE_INSTALL_GUIDE.md が作成されました

📹 カメラモジュールをチェック中...
✅ カメラデバイス (/dev/video0) が見つかりました
✅ カメラ情報: supported=1 detected=1

🚀 起動スクリプトを作成中...
✅ 起動スクリプト (start.sh) が作成されました

🔧 systemdサービスファイルを作成中...
✅ systemdサービスファイル (raspi-camera-streaming.service) が作成されました

📋 サービスを有効化するには以下のコマンドを実行してください:
sudo cp raspi-camera-streaming.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable raspi-camera-streaming.service
sudo systemctl start raspi-camera-streaming.service

🎉 セットアップが完了しました！

📋 使用方法:
1. 仮想環境をアクティベート: source venv/bin/activate
2. アプリケーションを起動: python app.py
3. ブラウザで http://localhost:5000 にアクセス

または、起動スクリプトを使用: ./start.sh
```

### エラー時の対処法

#### パッケージが見つからない場合

```
⚠️  USBメモリからパッケージファイルが見つかりませんでした
   手動でパッケージをインストールしてください

⚠️  オフラインインストールガイドを確認してください:
   cat OFFLINE_INSTALL_GUIDE.md
```

**対処法:**
1. USBメモリにパッケージファイルが正しく配置されているか確認
2. ファイル名にパッケージ名が含まれているか確認
3. 手動でパッケージをインストール

#### カメラが認識されない場合

```
⚠️  カメラデバイス (/dev/video0) が見つかりません
   カメラモジュールが正しく接続されているか確認してください
```

**対処法:**
1. カメラモジュールの接続を確認
2. `sudo raspi-config` でカメラを有効化
3. システムを再起動

## 🛠️ トラブルシューティング

### よくある問題と解決方法

#### 1. 権限エラー

```bash
# 実行権限を付与
chmod +x setup.py

# 管理者権限で実行
sudo python3 setup.py
```

#### 2. Pythonが見つからない

```bash
# Python3のインストール
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

#### 3. 仮想環境作成エラー

```bash
# 手動で仮想環境を作成
python3 -m venv venv
source venv/bin/activate
```

#### 4. パッケージインストールエラー

```bash
# 手動でパッケージをインストール
source venv/bin/activate
pip install /path/to/package.whl
```

#### 5. カメラ初期化エラー

```bash
# カメラの有効化
sudo raspi-config
# Interface Options → Camera → Enable

# システム再起動
sudo reboot
```

## 📋 セットアップ後の確認

### 1. 仮想環境の確認

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# インストールされたパッケージを確認
pip list
```

### 2. カメラの確認

```bash
# カメラデバイスの確認
ls -la /dev/video*

# カメラ情報の確認
vcgencmd get_camera
```

### 3. アプリケーションの起動

```bash
# 仮想環境をアクティベート
source venv/bin/activate

# アプリケーションを起動
python app.py
```

### 4. Webブラウザでの確認

ブラウザで `http://localhost:5000` にアクセスして、カメラストリーミングが正常に動作することを確認してください。

## 🔄 セットアップの再実行

セットアップを再実行する場合：

```bash
# 既存の仮想環境を削除
rm -rf venv

# セットアップスクリプトを再実行
python3 setup.py
```

## 📞 サポート

問題が発生した場合は、以下のファイルを確認してください：

- `OFFLINE_INSTALL_GUIDE.md` - オフラインインストールガイド
- `requirements_offline.txt` - 必要なパッケージリスト
- `INSTALL_GUIDE.md` - インストールガイド

---

**注意**: このスクリプトは開発・テスト目的で作成されています。本番環境での使用には、適切なセキュリティ対策を講じてください。 