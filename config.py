#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
設定ファイル - アプリケーション全体の設定値を管理
"""

import os
import platform

# ========================================
# ログ出力制御設定
# ========================================
DEBUG_SERIAL_LOG = True       # シリアル通信の送受信ログ
DEBUG_LEAK_LOG = True         # 漏液検出のログ
DEBUG_SYSTEM_LOG = True       # システム初期化・状態のログ
DEBUG_STREAM_LOG = False      # ストリーミング関連のログ（通常はFalse推奨）

# ========================================
# カメラ設定
# ========================================
CAM_WIDTH = 640
CAM_HEIGHT = 480
CAM_FPS = 60

# ========================================
# FFmpegストリーミング設定
# ========================================
HLS_SEGMENT_DURATION = 2      # HLSセグメントの長さ（秒）
HLS_PLAYLIST_SIZE = 3         # プレイリストに保持するセグメント数

# ========================================
# OS判定
# ========================================
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_RASPBERRY_PI = IS_LINUX and "raspberry" in platform.machine().lower()

# ========================================
# シリアル通信設定（ハイセラポンプ用）
# ========================================
if IS_WINDOWS:
    SERIAL_PORT_1 = os.getenv("HYSERA_PORT_1", "COM18")  # ハイセラポンプ1-3用
    SERIAL_PORT_2 = os.getenv("HYSERA_PORT_2", "COM20")  # ハイセラポンプ4-6用
else:
    SERIAL_PORT_1 = os.getenv("HYSERA_PORT_1", "/dev/ttyACM0")  # ハイセラポンプ1-3用
    SERIAL_PORT_2 = os.getenv("HYSERA_PORT_2", "/dev/ttyACM1")  # ハイセラポンプ4-6用

BAUD_RATE = 115200  # シリアル通信のボーレート（ハイセラポンプ用）

# ========================================
# シリアル通信設定（シリンジポンプ用）
# ========================================
if IS_WINDOWS:
    SYRINGE_SERIAL_PORT = os.getenv("SYRINGE_PORT", "COM4")
else:
    SYRINGE_SERIAL_PORT = os.getenv("SYRINGE_PORT", "/dev/ttyUSB0")

SYRINGE_BAUD_RATE = 9600  # シリンジポンプのボーレート

# ========================================
# Flaskサーバー設定
# ========================================
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# ========================================
# Picamera2利用可否チェック
# ========================================
try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

# ========================================
# 設定情報表示用関数
# ========================================
def print_config():
    """現在の設定情報を表示"""
    print("=" * 50)
    print("システム設定情報:")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    print(f"Raspberry Pi: {IS_RASPBERRY_PI}")
    print(f"カメラライブラリ: {'Picamera2' if PICAMERA_AVAILABLE else 'OpenCV'}")
    print("\nカメラ設定:")
    print(f"解像度: {CAM_WIDTH}x{CAM_HEIGHT}")
    print(f"FPS: {CAM_FPS}")
    print("\nシリアルポート設定:")
    print(f"ハイセラポンプ1-3: {SERIAL_PORT_1}")
    print(f"ハイセラポンプ4-6: {SERIAL_PORT_2}")
    print(f"シリンジポンプ: {SYRINGE_SERIAL_PORT}")
    print("\nFlaskサーバー設定:")
    print(f"ホスト: {FLASK_HOST}")
    print(f"ポート: {FLASK_PORT}")
    print(f"デバッグモード: {FLASK_DEBUG}")
    print("=" * 50)
