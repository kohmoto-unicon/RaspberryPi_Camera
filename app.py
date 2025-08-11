#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ラズパイ公式カメラモジュール ストリーミングWebサーバー + ポンプ制御
"""

import os
import time
import threading
from flask import Flask, render_template, Response, jsonify, request
import cv2
import io
import serial
from command import SyringePumpController

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

# シリアル通信設定（ハイセラポンプ制御用）
SERIAL_PORT = "COM18"  # Windows環境の場合（ハイセラポンプ）
BAUD_RATE = 9600
ser = None
serial_initialized = False

# シリアル通信設定（シリンジポンプ制御用）
SYRINGE_SERIAL_PORT = "COM19"  # Windows環境の場合（シリンジポンプ）
SYRINGE_BAUD_RATE = 9600
ser_syringe = None
syringe_serial_initialized = False
syringe_pump_controllers = []  # シリンジポンプ制御インスタンスのリスト

def initialize_serial():
    """シリアル通信を初期化（ハイセラポンプ）"""
    global ser, serial_initialized
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        serial_initialized = True
        print(f"ハイセラポンプ用シリアル通信が正常に初期化されました: {SERIAL_PORT}")
        return True
    except Exception as e:
        print(f"ハイセラポンプ用シリアル通信初期化エラー: {e}")
        serial_initialized = False
        return False

def initialize_syringe_serial():
    """シリアル通信を初期化（シリンジポンプ）"""
    global ser_syringe, syringe_serial_initialized, syringe_pump_controllers
    try:
        ser_syringe = serial.Serial(SYRINGE_SERIAL_PORT, SYRINGE_BAUD_RATE, timeout=1)
        syringe_serial_initialized = True
        
        # 6個のポンプ制御インスタンスを作成
        syringe_pump_controllers.clear()
        for i in range(1, 7):
            controller = SyringePumpController(i, ser_syringe)
            syringe_pump_controllers.append(controller)
        
        print(f"シリンジポンプ用シリアル通信が正常に初期化されました: {SYRINGE_SERIAL_PORT}")
        print(f"6個のポンプ制御インスタンスを作成しました")
        return True
    except Exception as e:
        print(f"シリンジポンプ用シリアル通信初期化エラー: {e}")
        syringe_serial_initialized = False
        return False

def calc_checksum(data_bytes):
    """チェックサムを計算"""
    checksum = 0
    for b in data_bytes[1:9]:
        checksum ^= b
    return checksum

def send_serial_command(pump_no, action, value="000000"):
    """シリアルコマンドを送信"""
    if not serial_initialized:
        print("シリアル通信が初期化されていません")
        return False
    
    try:
        value_str = value.zfill(6)
        cmd = bytearray(11)
        cmd[0] = 0x02
        cmd[1] = ord(str(pump_no))
        cmd[2] = ord(action)
        for i, c in enumerate(value_str):
            cmd[3 + i] = ord(c)
        cmd[9] = calc_checksum(cmd)
        cmd[10] = 0x03
        ser.write(cmd)
        print(f"[Pump {pump_no}] 送信: {' '.join(f'{b:02X}' for b in cmd)}")
        return True
    except Exception as e:
        print(f"シリアル送信エラー: {e}")
        return False

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
                camera.set(cv2.CAP_PROP_FPS, 60)
                
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

@app.route('/pump_control')
def pump_control():
    """ポンプ制御ページ"""
    return render_template('pump_control.html')

@app.route('/syringe_pump')
def syringe_pump():
    """シリンジポンプ制御ページ"""
    return render_template('syringe_pump.html')

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
        'serial_initialized': serial_initialized,  # 後方互換（ハイセラポンプ）
        'hysera_serial_initialized': serial_initialized,
        'syringe_serial_initialized': syringe_serial_initialized,
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

@app.route("/api/pump_control")
def api_pump_control():
    """ポンプ制御API"""
    pump = request.args.get("pump", "1")
    action = request.args.get("action", "M")
    value = request.args.get("value", "000000")
    
    success = send_serial_command(pump, action, value)
    
    return jsonify({
        'success': success,
        'message': f'送信完了: pump={pump}, action={action}, value={value}' if success else '送信失敗'
    })

@app.route("/api/get_current")
def api_get_current():
    """電流値取得API"""
    pump = request.args.get("pump", "1")
    
    # 電流データ取得コマンドを送信
    success = send_serial_command(pump, "C", "000000")
    
    if not success:
        return jsonify({
            'success': False,
            'current': 0,
            'message': '送信失敗'
        })
    
    # 応答を待機（最大1秒）
    import time
    start_time = time.time()
    response = None
    
    while time.time() - start_time < 1.0:
        if ser.in_waiting >= 10:  # 10バイトの応答を待機
            response = ser.read(10)
            break
        time.sleep(0.01)
    
    if response and len(response) == 10:
        # 応答フォーマット: STX + ポンプNo + 電流値(符号+5桁整数) + ETX + CS
        if response[0] == 0x02 and response[8] == 0x03:
            # チェックサム検証
            checksum = 0
            for i in range(1, 8):
                checksum ^= response[i]
            
            if checksum == response[9]:
                # 電流値を解析
                current_str = response[2:8].decode('ascii')
                try:
                    current = int(current_str)
                    return jsonify({
                        'success': True,
                        'current': current,
                        'message': f'電流値取得完了: {current}mA'
                    })
                except ValueError:
                    return jsonify({
                        'success': False,
                        'current': 0,
                        'message': '電流値解析エラー'
                    })
    
    return jsonify({
        'success': False,
        'current': 0,
        'message': '応答タイムアウトまたはエラー'
    })

@app.route("/api/syringe_pump_control")
def api_syringe_pump_control():
    """シリンジポンプ制御API"""
    pump_index = request.args.get("pump", "1")
    action = request.args.get("action", "")
    steps = request.args.get("steps", "3000")
    
    try:
        pump_index = int(pump_index) - 1  # 0ベースのインデックスに変換
        if pump_index < 0:
            return jsonify({
                'success': False,
                'message': f'無効なポンプ番号: {pump_index + 1}'
            })
        
        # シリアル未初期化でも、コマンド内容は返すため一時コントローラを生成
        if 0 <= pump_index < len(syringe_pump_controllers):
            controller = syringe_pump_controllers[pump_index]
        else:
            controller = SyringePumpController(pump_index + 1, ser_syringe)
        
        # フロントエンドから選択されたアドレスを取得
        selected_address = request.args.get("address", "1")
        try:
            selected_address = int(selected_address)
        except ValueError:
            selected_address = 1
        
        if action == "initialize":
            success, command_bytes = controller.send_command("ZR", selected_address)
            message = "初期化コマンド送信完了" if success else "初期化コマンド送信失敗"
        elif action == "move_up":
            success, command_bytes = controller.send_command(f"D{steps}", selected_address)
            message = f"上移動コマンド送信完了（{steps}ステップ）" if success else "上移動コマンド送信失敗"
        elif action == "move_down":
            success, command_bytes = controller.send_command(f"P{steps}", selected_address)
            message = f"下移動コマンド送信完了（{steps}ステップ）" if success else "下移動コマンド送信失敗"
        elif action == "stop":
            success, command_bytes = controller.send_command("TR", selected_address)
            message = "停止コマンド送信完了" if success else "停止コマンド送信失敗"
        elif action == "loop":
            # ループコマンド: "P" + 下移動ステップ数 + "D" + 上移動ステップ数 + "G" + ループ数
            down_steps = request.args.get("downSteps", "3000")
            up_steps = request.args.get("steps", "3000")
            loop_count = request.args.get("loopCount", "0")
            loop_command = f"P{down_steps}D{up_steps}G{loop_count}R"
            success, command_bytes = controller.send_command(loop_command, selected_address)
            message = f"ループコマンド送信完了（下:{down_steps}、上:{up_steps}、ループ:{loop_count}）" if success else "ループコマンド送信失敗"
        elif action == "qr":
            success, command_bytes = controller.send_command("QR", selected_address)
            message = "ステータス確認コマンド送信完了" if success else "ステータス確認コマンド送信失敗"
        else:
            return jsonify({
                'success': False,
                'message': f'無効なアクション: {action}'
            })
        
        return jsonify({
            'success': success,
            'message': message,
            'pump': pump_index + 1,
            'action': action,
            'command_bytes': list(command_bytes) if command_bytes else []
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'エラーが発生しました: {str(e)}'
        })

if __name__ == '__main__':
    import argparse
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='ラズパイカメラストリーミング + ポンプ制御Webサーバー')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで起動')
    parser.add_argument('--port', type=int, default=5000, help='ポート番号（デフォルト: 5000）')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='ホストアドレス（デフォルト: 0.0.0.0）')
    parser.add_argument('--serial-port', type=str, default='COM18', help='ハイセラポンプ用シリアルポート（デフォルト: COM18）')
    parser.add_argument('--syringe-serial-port', type=str, default='COM19', help='シリンジポンプ用シリアルポート（デフォルト: COM19）')
    
    args = parser.parse_args()
    
    # シリアルポート設定を更新（ハイセラ／シリンジ）
    SERIAL_PORT = args.serial_port
    SYRINGE_SERIAL_PORT = args.syringe_serial_port
    
    # カメラ初期化
    camera_success = initialize_camera()
    
    # シリアル通信初期化（ハイセラ／シリンジ）
    serial_success = initialize_serial()
    syringe_serial_success = initialize_syringe_serial()
    
    print("Webサーバーを起動します...")
    print(f"ブラウザで http://localhost:{args.port} にアクセスしてください")
    print(f"ポンプ制御ページ: http://localhost:{args.port}/pump_control")
    
    if not camera_success:
        print("警告: カメラの初期化に失敗しました。")
        if PICAMERA_AVAILABLE:
            print("ラズパイにカメラモジュールが接続されているか確認してください。")
        else:
            print("PCにWebカメラが接続されているか確認してください。")
    
    if not serial_success:
        print("警告: ハイセラポンプ用シリアル通信の初期化に失敗しました。")
        print(f"シリアルポート {SERIAL_PORT} が利用可能か確認してください。")
    if not syringe_serial_success:
        print("警告: シリンジポンプ用シリアル通信の初期化に失敗しました。")
        print(f"シリアルポート {SYRINGE_SERIAL_PORT} が利用可能か確認してください。")
    
    # 開発サーバー起動（本番環境ではgunicorn等を使用）
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True) 