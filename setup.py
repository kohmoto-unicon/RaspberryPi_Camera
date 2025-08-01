#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ラズパイカメラストリーミング セットアップスクリプト（オフライン対応版）
"""

import os
import sys
import subprocess
import platform
import shutil
import glob

def run_command(command, description):
    """コマンドを実行"""
    print(f"\n🔧 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} 完了")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失敗: {e}")
        print(f"エラー出力: {e.stderr}")
        return False

def check_system():
    """システム要件をチェック"""
    print("🔍 システム要件をチェック中...")
    
    # OS確認
    if platform.system() != "Linux":
        print("⚠️  警告: このスクリプトはLinux（ラズパイOS）用です")
    
    # Python バージョン確認
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 7):
        print("❌ Python 3.7以上が必要です")
        return False
    
    print(f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    return True

def find_usb_packages():
    """USBメモリからパッケージを検索"""
    print("\n🔍 USBメモリからパッケージを検索中...")
    
    # 一般的なUSBマウントポイントをチェック
    usb_paths = [
        "/media/pi/*",
        "/media/*",
        "/mnt/usb*",
        "/mnt/*"
    ]
    
    package_paths = []
    for path_pattern in usb_paths:
        try:
            for path in glob.glob(path_pattern):
                if os.path.isdir(path):
                    print(f"📁 検索中: {path}")
                    # Pythonパッケージファイルを検索
                    for ext in ['*.whl', '*.tar.gz', '*.zip']:
                        package_paths.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
        except Exception as e:
            print(f"⚠️  {path_pattern} の検索中にエラー: {e}")
    
    if package_paths:
        print(f"✅ {len(package_paths)}個のパッケージファイルが見つかりました")
        for pkg in package_paths[:5]:  # 最初の5個を表示
            print(f"   📦 {os.path.basename(pkg)}")
        if len(package_paths) > 5:
            print(f"   ... 他 {len(package_paths) - 5}個")
    else:
        print("⚠️  USBメモリからパッケージファイルが見つかりませんでした")
    
    return package_paths

def install_system_dependencies_offline():
    """オフラインでシステム依存関係をインストール"""
    print("\n📦 システム依存関係をインストール中（オフライン）...")
    
    # 基本的なパッケージ（通常はOSに含まれている）
    basic_packages = [
        "python3",
        "python3-pip",
        "python3-venv"
    ]
    
    # オフラインで利用可能なパッケージをチェック
    available_packages = []
    for package in basic_packages:
        try:
            result = subprocess.run(f"dpkg -l | grep {package}", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {package} は既にインストールされています")
            else:
                available_packages.append(package)
        except:
            available_packages.append(package)
    
    if available_packages:
        print(f"⚠️  以下のパッケージが利用できません: {', '.join(available_packages)}")
        print("   システムに事前にインストールされているか確認してください")
    
    return True

def setup_virtual_environment():
    """仮想環境をセットアップ"""
    print("\n🐍 仮想環境をセットアップ中...")
    
    # 仮想環境作成
    if not run_command("python3 -m venv venv", "仮想環境作成"):
        return False
    
    # 仮想環境アクティベート
    if os.name == 'nt':  # Windows
        activate_script = "venv\\Scripts\\activate"
    else:  # Linux/Mac
        activate_script = "source venv/bin/activate"
    
    print(f"✅ 仮想環境が作成されました: {activate_script}")
    return True

def install_python_dependencies_offline(package_paths):
    """オフラインでPython依存関係をインストール"""
    print("\n📦 Python依存関係をインストール中（オフライン）...")
    
    # pip更新（オフラインではスキップ）
    print("⚠️  オフライン環境のため、pip更新をスキップします")
    
    # 必要なパッケージのリスト
    required_packages = [
        "Flask",
        "opencv-python",
        "picamera2",
        "numpy",
        "Pillow"
    ]
    
    # USBメモリからパッケージをインストール
    installed_count = 0
    for package in required_packages:
        print(f"\n🔍 {package} を検索中...")
        
        # パッケージ名に基づいてファイルを検索
        found_packages = []
        for pkg_path in package_paths:
            pkg_name = os.path.basename(pkg_path).lower()
            if package.lower().replace('-', '_') in pkg_name:
                found_packages.append(pkg_path)
        
        if found_packages:
            # 最新のパッケージを選択（ファイル名に日付やバージョンが含まれている場合）
            selected_pkg = sorted(found_packages)[-1]
            print(f"📦 インストール: {os.path.basename(selected_pkg)}")
            
            if run_command(f"venv/bin/pip install {selected_pkg}", f"{package} インストール"):
                installed_count += 1
        else:
            print(f"⚠️  {package} のパッケージファイルが見つかりませんでした")
            print(f"   手動で {package} のパッケージファイルをUSBメモリに配置してください")
    
    print(f"\n📊 インストール結果: {installed_count}/{len(required_packages)} パッケージ")
    
    if installed_count < len(required_packages):
        print("\n⚠️  一部のパッケージがインストールできませんでした")
        print("以下のパッケージファイルをUSBメモリに配置してください:")
        for package in required_packages:
            print(f"   - {package} (.whl または .tar.gz)")
    
    return installed_count > 0

def create_offline_requirements():
    """オフライン用のrequirements.txtを作成"""
    print("\n📝 オフライン用requirements.txtを作成中...")
    
    offline_requirements = """# オフラインインストール用 requirements.txt
# 以下のパッケージファイルをUSBメモリに配置してください

# Webフレームワーク
Flask==2.3.3

# 画像処理
opencv-python==4.8.1.78
Pillow==10.0.1

# ラズパイカメラ
picamera2==0.3.12

# 数値計算
numpy==1.24.3

# インストール方法:
# 1. 上記パッケージの.whlファイルをUSBメモリに配置
# 2. venv/bin/pip install /path/to/usb/package.whl
"""
    
    try:
        with open("requirements_offline.txt", "w") as f:
            f.write(offline_requirements)
        print("✅ requirements_offline.txt が作成されました")
        return True
    except Exception as e:
        print(f"❌ requirements_offline.txt 作成に失敗: {e}")
        return False

def check_camera():
    """カメラモジュールをチェック"""
    print("\n📹 カメラモジュールをチェック中...")
    
    # カメラデバイス確認
    if os.path.exists("/dev/video0"):
        print("✅ カメラデバイス (/dev/video0) が見つかりました")
    else:
        print("⚠️  カメラデバイス (/dev/video0) が見つかりません")
        print("   カメラモジュールが正しく接続されているか確認してください")
    
    # vcgencmdでカメラ確認
    try:
        result = subprocess.run("vcgencmd get_camera", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ カメラ情報: {result.stdout.strip()}")
        else:
            print("⚠️  カメラ情報の取得に失敗しました")
    except:
        print("⚠️  vcgencmdコマンドが見つかりません")
    
    return True

def create_startup_script():
    """起動スクリプトを作成"""
    print("\n🚀 起動スクリプトを作成中...")
    
    startup_script = """#!/bin/bash
# ラズパイカメラストリーミング起動スクリプト（オフライン版）

cd "$(dirname "$0")"

# 仮想環境をアクティベート
source venv/bin/activate

# アプリケーションを起動
python app.py
"""
    
    try:
        with open("start.sh", "w") as f:
            f.write(startup_script)
        
        # 実行権限を付与
        os.chmod("start.sh", 0o755)
        print("✅ 起動スクリプト (start.sh) が作成されました")
        return True
    except Exception as e:
        print(f"❌ 起動スクリプト作成に失敗: {e}")
        return False

def create_offline_install_guide():
    """オフラインインストールガイドを作成"""
    print("\n📖 オフラインインストールガイドを作成中...")
    
    guide_content = """# オフラインインストールガイド

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
"""
    
    try:
        with open("OFFLINE_INSTALL_GUIDE.md", "w", encoding="utf-8") as f:
            f.write(guide_content)
        print("✅ OFFLINE_INSTALL_GUIDE.md が作成されました")
        return True
    except Exception as e:
        print(f"❌ ガイド作成に失敗: {e}")
        return False

def create_systemd_service():
    """systemdサービスファイルを作成"""
    print("\n🔧 systemdサービスファイルを作成中...")
    
    current_dir = os.getcwd()
    service_content = f"""[Unit]
Description=Raspberry Pi Camera Streaming Server (Offline)
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory={current_dir}
ExecStart={current_dir}/venv/bin/python {current_dir}/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    
    try:
        with open("raspi-camera-streaming.service", "w") as f:
            f.write(service_content)
        
        print("✅ systemdサービスファイル (raspi-camera-streaming.service) が作成されました")
        print("\n📋 サービスを有効化するには以下のコマンドを実行してください:")
        print("sudo cp raspi-camera-streaming.service /etc/systemd/system/")
        print("sudo systemctl daemon-reload")
        print("sudo systemctl enable raspi-camera-streaming.service")
        print("sudo systemctl start raspi-camera-streaming.service")
        
        return True
    except Exception as e:
        print(f"❌ systemdサービスファイル作成に失敗: {e}")
        return False

def main():
    """メイン関数"""
    print("🚀 ラズパイカメラストリーミング セットアップ（オフライン版）")
    print("=" * 60)
    
    # システムチェック
    if not check_system():
        print("❌ システム要件を満たしていません")
        return False
    
    # USBメモリからパッケージを検索
    package_paths = find_usb_packages()
    
    # システム依存関係インストール（オフライン）
    if not install_system_dependencies_offline():
        print("❌ システム依存関係のインストールに失敗しました")
        return False
    
    # 仮想環境セットアップ
    if not setup_virtual_environment():
        print("❌ 仮想環境のセットアップに失敗しました")
        return False
    
    # Python依存関係インストール（オフライン）
    if package_paths:
        if not install_python_dependencies_offline(package_paths):
            print("⚠️  Python依存関係のインストールに一部失敗しました")
    else:
        print("⚠️  USBメモリからパッケージが見つかりませんでした")
        print("   手動でパッケージをインストールしてください")
    
    # オフライン用ファイルを作成
    create_offline_requirements()
    create_offline_install_guide()
    
    # カメラチェック
    check_camera()
    
    # 起動スクリプト作成
    create_startup_script()
    
    # systemdサービスファイル作成
    create_systemd_service()
    
    print("\n🎉 セットアップが完了しました！")
    print("\n📋 使用方法:")
    print("1. 仮想環境をアクティベート: source venv/bin/activate")
    print("2. アプリケーションを起動: python app.py")
    print("3. ブラウザで http://localhost:5000 にアクセス")
    print("\nまたは、起動スクリプトを使用: ./start.sh")
    
    if not package_paths:
        print("\n⚠️  オフラインインストールガイドを確認してください:")
        print("   cat OFFLINE_INSTALL_GUIDE.md")
    
    return True

if __name__ == "__main__":
    main() 