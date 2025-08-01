#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
オフラインインストール用パッケージダウンロードスクリプト
"""

import os
import sys
import subprocess
import platform
import urllib.request
import json
from pathlib import Path

def get_python_version():
    """Pythonバージョンを取得"""
    version = sys.version_info
    return f"{version.major}.{version.minor}"

def get_architecture():
    """システムアーキテクチャを取得"""
    arch = platform.machine()
    if arch == "aarch64":
        return "aarch64"
    elif arch == "armv7l":
        return "armv7l"
    else:
        return arch

def download_file(url, filename):
    """ファイルをダウンロード"""
    try:
        print(f"📥 ダウンロード中: {filename}")
        urllib.request.urlretrieve(url, filename)
        print(f"✅ ダウンロード完了: {filename}")
        return True
    except Exception as e:
        print(f"❌ ダウンロード失敗: {filename} - {e}")
        return False

def get_package_info(package_name):
    """PyPIからパッケージ情報を取得"""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            return data
    except Exception as e:
        print(f"❌ パッケージ情報取得失敗: {package_name} - {e}")
        return None

def find_compatible_wheel(package_info, python_version, architecture):
    """互換性のあるwheelファイルを検索"""
    if not package_info:
        return None
    
    releases = package_info.get('releases', {})
    
    # 最新バージョンを取得
    latest_version = max(releases.keys())
    files = releases[latest_version]
    
    # wheelファイルを検索
    for file_info in files:
        filename = file_info['filename']
        if filename.endswith('.whl'):
            # Pythonバージョンとアーキテクチャをチェック
            if f"cp{python_version.replace('.', '')}" in filename:
                if architecture in filename or "any" in filename:
                    return {
                        'filename': filename,
                        'url': file_info['url'],
                        'version': latest_version
                    }
    
    return None

def download_packages():
    """必要なパッケージをダウンロード"""
    print("🚀 オフラインインストール用パッケージダウンロード")
    print("=" * 60)
    
    # システム情報を取得
    python_version = get_python_version()
    architecture = get_architecture()
    
    print(f"🐍 Python バージョン: {python_version}")
    print(f"🏗️  アーキテクチャ: {architecture}")
    
    # ダウンロードディレクトリを作成
    download_dir = Path("packages")
    download_dir.mkdir(exist_ok=True)
    
    # 必要なパッケージリスト
    packages = [
        "Flask",
        "opencv-python",
        "picamera2",
        "numpy",
        "Pillow"
    ]
    
    # 依存関係パッケージ
    dependencies = [
        "Werkzeug",
        "Jinja2",
        "MarkupSafe",
        "itsdangerous",
        "click",
        "blinker"
    ]
    
    all_packages = packages + dependencies
    
    print(f"\n📦 {len(all_packages)}個のパッケージをダウンロードします")
    
    downloaded_count = 0
    failed_packages = []
    
    for package in all_packages:
        print(f"\n🔍 {package} の情報を取得中...")
        
        package_info = get_package_info(package)
        if not package_info:
            failed_packages.append(package)
            continue
        
        wheel_info = find_compatible_wheel(package_info, python_version, architecture)
        if not wheel_info:
            print(f"⚠️  {package} の互換性のあるwheelファイルが見つかりません")
            failed_packages.append(package)
            continue
        
        filename = wheel_info['filename']
        url = wheel_info['url']
        version = wheel_info['version']
        
        print(f"📋 パッケージ: {package} {version}")
        print(f"📁 ファイル: {filename}")
        
        filepath = download_dir / filename
        
        if download_file(url, filepath):
            downloaded_count += 1
        else:
            failed_packages.append(package)
    
    # 結果表示
    print(f"\n📊 ダウンロード結果:")
    print(f"✅ 成功: {downloaded_count}/{len(all_packages)}")
    print(f"❌ 失敗: {len(failed_packages)}")
    
    if failed_packages:
        print(f"\n⚠️  ダウンロードに失敗したパッケージ:")
        for package in failed_packages:
            print(f"   - {package}")
    
    # インストールガイドを作成
    create_install_guide(download_dir, downloaded_count)
    
    return downloaded_count > 0

def create_install_guide(download_dir, downloaded_count):
    """インストールガイドを作成"""
    print(f"\n📖 インストールガイドを作成中...")
    
    guide_content = f"""# オフラインインストールガイド

## ダウンロード結果

- ダウンロード済みパッケージ: {downloaded_count}個
- ダウンロード場所: {download_dir.absolute()}

## インストール手順

### 1. USBメモリにパッケージをコピー

```bash
# パッケージディレクトリをUSBメモリにコピー
cp -r {download_dir} /path/to/usb/
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
for pkg in /path/to/usb/{download_dir}/*.whl; do
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
"""
    
    try:
        with open("INSTALL_GUIDE.md", "w", encoding="utf-8") as f:
            f.write(guide_content)
        print("✅ INSTALL_GUIDE.md が作成されました")
    except Exception as e:
        print(f"❌ ガイド作成に失敗: {e}")

def main():
    """メイン関数"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("使用方法:")
        print("python3 download_packages.py")
        print("\nこのスクリプトは、オフラインインストール用のPythonパッケージをダウンロードします。")
        return
    
    try:
        success = download_packages()
        if success:
            print(f"\n🎉 パッケージダウンロードが完了しました！")
            print(f"📁 ダウンロード場所: {Path('packages').absolute()}")
            print(f"📖 インストールガイド: INSTALL_GUIDE.md")
        else:
            print(f"\n❌ パッケージダウンロードに失敗しました")
            sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n⚠️  ダウンロードが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 予期しないエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 