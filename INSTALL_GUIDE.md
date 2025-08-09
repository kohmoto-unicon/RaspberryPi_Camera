# オフラインインストールガイド

## ダウンロード結果

- ダウンロード済みパッケージ: 2個
- ダウンロード場所: D:\raspi\packages

## インストール手順

### 1. USBメモリにパッケージをコピー

```bash
# パッケージディレクトリをUSBメモリにコピー
cp -r packages /path/to/usb/
```

### 2. ラズパイでセットアップ

```bash
# プロジェクトディレクトリに移動
cd /path/to/raspi-camera-streaming

# セットアップスクリプトを実行
python3 setup.py

# 仮想環境をアクティベート
source venv/bin/activate
```

### 3. パッケージをインストール

```bash
# USBメモリからパッケージをインストール
for pkg in /path/to/usb/packages/*.whl; do
    venv/bin/pip install "$pkg"
done
```

### 4. アプリケーションを起動

```bash
# アプリケーションを起動
python app.py
```

## 注意事項

- ラズパイのアーキテクチャに合ったパッケージをダウンロードしてください
- Python 3.9用のパッケージをダウンロードしてください
- 依存関係のあるパッケージも一緒にダウンロードしてください

## トラブルシューティング

### パッケージが見つからない場合

手動でパッケージをダウンロード:
1. https://pypi.org/ にアクセス
2. パッケージ名で検索
3. ラズパイ用の.whlファイルをダウンロード
4. USBメモリに配置

### インストールエラーの場合

```bash
# 詳細なエラー情報を表示
venv/bin/pip install --verbose /path/to/package.whl

# 依存関係を確認
venv/bin/pip check
```
