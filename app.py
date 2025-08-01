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
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import io

app = Flask(__name__)

# カメラ設定
camera = None
camera_initialized = False
stream_thread = None
frame_buffer = None
frame_lock = threading.Lock()

def initialize_camera():
    """カメラを初期化"""
    global camera, camera_initialized
    
    try:
        # Picamera2を使用（ラズパイ公式カメラモジュール用）
        camera = Picamera2()
        
        # カメラ設定
        config = camera.create_preview_configuration(
            main={"size": (640, 480)},
            encode="main"
        )
        camera.configure(config)
        camera.start()
        
        camera_initialized = True
        print("カメラが正常に初期化されました")
        return True
        
    except Exception as e:
        print(f"カメラ初期化エラー: {e}")
        camera_initialized = False
        return False

def get_frame():
    """カメラからフレームを取得"""
    global camera, camera_initialized
    
    if not camera_initialized:
        return None
    
    try:
        # カメラから画像をキャプチャ
        frame = camera.capture_array()
        
        # BGRからRGBに変換（OpenCVはBGR、Web表示はRGB）
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        return frame_rgb
        
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
            camera.stop()
            camera.close()
        
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
        print("ラズパイにカメラモジュールが接続されているか確認してください。") 