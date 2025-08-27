# オフラインインストールガイド

## 必要なパッケージファイル

以下のPythonパッケージの.whlファイルをUSBメモリに配置してください：

### 1. Flask (Webフレームワーク)
- ファイル名例: Flask-2.3.3-py3-none-any.whl
- ダウンロード: https://pypi.org/project/Flask/#files

### 2. opencv-python (画像処理)
- ファイル名例: opencv_python-4.8.1.78-cp39-cp39-linux_aarch64.whl
- ダウンロード: https://pypi.org/project/opencv-python/#files

### 3. picamera2 (ラズパイカメラ)
- ファイル名例: picamera2-0.3.12-py3-none-any.whl
- ダウンロード: https://pypi.org/project/picamera2/#files

### 4. numpy (数値計算)
- ファイル名例: numpy-1.24.3-cp39-cp39-linux_aarch64.whl
- ダウンロード: https://pypi.org/project/numpy/#files

### 5. Pillow (画像処理)
- ファイル名例: Pillow-10.0.1-cp39-cp39-linux_aarch64.whl
- ダウンロード: https://pypi.org/project/Pillow/#files

## インストール手順

1. USBメモリをラズパイに接続
2. パッケージファイルをUSBメモリのルートディレクトリに配置
3. setup.pyを実行: `python3 setup.py`
4. 仮想環境をアクティベート: `source venv/bin/activate`
5. 手動でパッケージをインストール（必要な場合）:
   ```
   venv/bin/pip install /path/to/usb/package.whl
   ```

## 注意事項

- ラズパイのアーキテクチャ（armv7l, aarch64）に合ったパッケージをダウンロードしてください
- Python 3.9用のパッケージをダウンロードしてください
- 依存関係のあるパッケージも一緒にダウンロードしてください
