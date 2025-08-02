#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ラズパイ公式カメラモジュール ストリーミングWebサーバー
"""

import os
import time
import threading
from flask import Flask, render_template, Response, jsonify
import cv2
import numpy as np
import io

# Raspberry Pi専用ライブラリのインポート（PCでは利用不可）
try:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput
    PICAMERA_AVAILABLE = True
    print("Picamera2ライブラリが利用可能です（Raspberry Pi環境）")
except ImportError:
    PICAMERA_AVAILABLE = False
    print("Picamera2ライブラリが利用できません（PC環境）。OpenCVのVideoCaptureを使用します。")

app = Flask(__name__)

# カメラ設定
camera = None
camera_initialized = False
stream_thread = None
frame_buffer = None
frame_lock = threading.Lock()
is_raspberry_pi = False

def initialize_camera():
    """カメラを初期化"""
    global camera, camera_initialized, is_raspberry_pi
    
    try:
        if PICAMERA_AVAILABLE:
            # Picamera2を使用（ラズパイ公式カメラモジュール用）
            camera = Picamera2()
            
            # カメラ設定
            config = camera.create_preview_configuration(
                main={"size": (640, 480)},
                encode="main"
            )
            camera.configure(config)
            camera.start()
            
            is_raspberry_pi = True
            camera_initialized = True
            print("Raspberry Piカメラが正常に初期化されました")
            return True
        else:
            # PC環境ではOpenCVのVideoCaptureを使用
            camera = cv2.VideoCapture(0)  # デフォルトカメラ
            
            if camera.isOpened():
                # カメラ設定
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                camera.set(cv2.CAP_PROP_FPS, 30)
                
                is_raspberry_pi = False
                camera_initialized = True
                print("PCカメラが正常に初期化されました")
                return True
            else:
                print("PCカメラの初期化に失敗しました")
                camera_initialized = False
                return False
        
    except Exception as e:
        print(f"カメラ初期化エラー: {e}")
        camera_initialized = False
        return False

def get_frame():
    """カメラからフレームを取得"""
    global camera, camera_initialized, is_raspberry_pi
    
    if not camera_initialized:
        return None
    
    try:
        if is_raspberry_pi and PICAMERA_AVAILABLE:
            # Raspberry Piカメラから画像をキャプチャ
            frame = camera.capture_array()
            
            # BGRからRGBに変換（OpenCVはBGR、Web表示はRGB）
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            return frame_rgb
        else:
            # PCカメラから画像をキャプチャ
            ret, frame = camera.read()
            
            if ret:
                # BGRからRGBに変換
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame_rgb
            else:
                return None
        
    except Exception as e:
        print(f"フレーム取得エラー: {e}")
        return None

def generate_frames():
    """MJPEGストリーミング用のフレーム生成"""
    while True:
        frame = get_frame()
        
        if frame is not None:
            # JPEGエンコード
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            
            if ret:
                # MJPEGストリーミング用のヘッダー付きでフレームを返す
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        # フレームレート制御（30FPS）
        time.sleep(1/30)

@app.route('/')
def index():
    """メインページ"""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """ビデオストリーミングエンドポイント"""
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def api_status():
    """カメラ状態API"""
    return jsonify({
        'camera_initialized': camera_initialized,
        'timestamp': time.time()
    })

@app.route('/api/snapshot')
def api_snapshot():
    """スナップショットAPI"""
    frame = get_frame()
    
    if frame is not None:
        # JPEGエンコード
        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        
        if ret:
            return Response(buffer.tobytes(), mimetype='image/jpeg')
    
    return jsonify({'error': 'スナップショット取得に失敗しました'}), 500

@app.route('/api/restart_camera')
def api_restart_camera():
    """カメラ再起動API"""
    global camera, camera_initialized
    
    try:
        if camera is not None:
            if is_raspberry_pi and PICAMERA_AVAILABLE:
                camera.stop()
                camera.close()
            else:
                camera.release()
        
        success = initialize_camera()
        return jsonify({
            'success': success,
            'message': 'カメラを再起動しました' if success else 'カメラ再起動に失敗しました'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='ラズパイカメラストリーミングWebサーバー')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで起動')
    parser.add_argument('--port', type=int, default=5000, help='ポート番号（デフォルト: 5000）')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='ホストアドレス（デフォルト: 0.0.0.0）')
    
    args = parser.parse_args()
    
    # カメラ初期化
    if initialize_camera():
        print("Webサーバーを起動します...")
        print(f"ブラウザで http://localhost:{args.port} にアクセスしてください")
        
        # 開発サーバー起動（本番環境ではgunicorn等を使用）
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    else:
        print("カメラの初期化に失敗しました。")
        if PICAMERA_AVAILABLE:
            print("ラズパイにカメラモジュールが接続されているか確認してください。")
        else:
            print("PCにWebカメラが接続されているか確認してください。") 