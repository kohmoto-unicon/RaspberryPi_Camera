#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ラズパイ公式カメラモジュール ストリーミングWebサーバー + ポンプ制御
"""

import os
import time
import threading
import subprocess
import tempfile
import shutil
from flask import Flask, render_template, Response, jsonify, request, send_file
from flask_cors import CORS
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
    print("Picamera2ライブラリが利用できません。OpenCVのVideoCaptureを使用します。")
    
    # ラズパイ環境かどうかを判定
    import platform
    if platform.system() == "Linux" and "raspberry" in platform.machine().lower():
        print("ラズパイ環境を検出しました。OpenCVでカメラにアクセスを試行します。")
        # ラズパイで利用可能なカメラデバイスを確認
        try:
            import os
            video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
            if video_devices:
                print(f"利用可能なビデオデバイス: {video_devices}")
                # ラズパイカメラモジュール用のデバイスを優先
                for device in video_devices:
                    if device in ['video0', 'video10', 'video11', 'video12']:
                        print(f"ラズパイカメラモジュール用デバイスを検出: {device}")
                        break
            else:
                print("ビデオデバイスが見つかりません")
        except Exception as e:
            print(f"ビデオデバイス確認エラー: {e}")

app = Flask(__name__)
# CORSを有効化（モバイルデバイス対応）
CORS(app, resources={
    r"/video_feed*": {"origins": "*"},
    r"/hls_segment/*": {"origins": "*"},
    r"/api/*": {"origins": "*"}
})

# カメラ設定
camera = None
camera_initialized = False
stream_thread = None
frame_buffer = None
frame_lock = threading.Lock()
is_raspberry_pi = False

# FFmpegストリーミング設定
ffmpeg_process = None
ffmpeg_temp_dir = None
hls_segment_duration = 2  # HLSセグメントの長さ（秒）
hls_playlist_size = 3     # プレイリストに保持するセグメント数

# --- 追加: 動的設定用のグローバル変数 ---
CAM_WIDTH = 640
CAM_HEIGHT = 480
CAM_FPS = 45

# OS判定
import platform
IS_WINDOWS = platform.system() == "Windows"

# シリアル通信設定（ハイセラポンプ制御用）
if IS_WINDOWS:
    SERIAL_PORT_1 = "COM18"  # Windows環境の場合（ハイセラポンプ1-3用）
    SERIAL_PORT_2 = "COM20"  # Windows環境の場合（ハイセラポンプ4-6用）
else:
    SERIAL_PORT_1 = "/dev/ttyACM0"  # Linux/Raspberry Pi環境の場合（ハイセラポンプ1-3用）
    SERIAL_PORT_2 = "/dev/ttyACM1"  # Linux/Raspberry Pi環境の場合（ハイセラポンプ4-6用）

BAUD_RATE = 9600
ser_1 = None  # ポンプ1-3用
ser_2 = None  # ポンプ4-6用
serial_initialized1 = False # ポンプ1-3用シリアル通信初期化フラグ
serial_initialized2 = False # ポンプ4-6用シリアル通信初期化フラグ

# シリアル通信設定（シリンジポンプ制御用）
if IS_WINDOWS:
    SYRINGE_SERIAL_PORT = "COM22"  # Windows環境の場合（シリンジポンプ）
else:
    SYRINGE_SERIAL_PORT = "/dev/ttyACM2"  # Linux/Raspberry Pi環境の場合（シリンジポンプ）

SYRINGE_BAUD_RATE = 9600
ser_syringe = None
syringe_serial_initialized = False
syringe_pump_controllers = []  # シリンジポンプ制御インスタンスのリスト

def initialize_serial():
    """シリアル通信を初期化（ハイセラポンプ）"""
    global ser_1, ser_2, serial_initialized_1, serial_initialized_2
    
    print(f"OS: {platform.system()}")
    print(f"シリアルポート設定:")
    print(f"  ポンプ1-3用: {SERIAL_PORT_1}")
    print(f"  ポンプ4-6用: {SERIAL_PORT_2}")
    
    try:
        # ポンプ1-3用ポートの初期化
        print(f"ポート {SERIAL_PORT_1} を開こうとしています...")
        ser_1 = serial.Serial(SERIAL_PORT_1, BAUD_RATE, timeout=1)
        print(f"✓ ハイセラポンプ1-3用シリアル通信が正常に初期化されました: {SERIAL_PORT_1}")
        serial_initialized_1 = True
    except Exception as e:
        print(f"✗ ハイセラポンプ1-3用シリアル通信初期化エラー: {e}")
        if not IS_WINDOWS:
            print("   → デバイスが接続されているか確認してください")
            print("   → デバイス権限があるか確認してください（sudoが必要な場合があります）")
        serial_initialized_1 = False

    try:
        # ポンプ4-6用ポートの初期化
        print(f"ポート {SERIAL_PORT_2} を開こうとしています...")
        ser_2 = serial.Serial(SERIAL_PORT_2, BAUD_RATE, timeout=1)
        print(f"✓ ハイセラポンプ4-6用シリアル通信が正常に初期化されました: {SERIAL_PORT_2}")
        serial_initialized_2 = True
    except Exception as e:
        print(f"✗ ハイセラポンプ4-6用シリアル通信初期化エラー: {e}")
        if not IS_WINDOWS:
            print("   → デバイスが接続されているか確認してください")
            print("   → デバイス権限があるか確認してください（sudoが必要な場合があります）")
        serial_initialized_2 = False

    # 両方の初期化結果を返す
    return serial_initialized_1 or serial_initialized_2    

def initialize_syringe_serial():
    """シリアル通信を初期化（シリンジポンプ）"""
    global ser_syringe, syringe_serial_initialized, syringe_pump_controllers
    
    print(f"シリンジポンプ用ポート: {SYRINGE_SERIAL_PORT}")
    
    try:
        ser_syringe = serial.Serial(SYRINGE_SERIAL_PORT, SYRINGE_BAUD_RATE, timeout=1)
        syringe_serial_initialized = True
        
        # 6個のポンプ制御インスタンスを作成
        syringe_pump_controllers.clear()
        for i in range(1, 7):
            controller = SyringePumpController(i, ser_syringe)
            syringe_pump_controllers.append(controller)
        
        print(f"✓ シリンジポンプ用シリアル通信が正常に初期化されました: {SYRINGE_SERIAL_PORT}")
        print(f"✓ 6個のポンプ制御インスタンスを作成しました")
        return True
    except Exception as e:
        print(f"✗ シリンジポンプ用シリアル通信初期化エラー: {e}")
        if not IS_WINDOWS:
            print("   → デバイスが接続されているか確認してください")
            print("   → デバイス権限があるか確認してください（sudoが必要な場合があります）")
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
    if (pump_no < 4) and (not serial_initialized_1):
        print("シリアル通信1が初期化されていません")
        return False
    if (pump_no > 3) and (not serial_initialized_2):
        print("シリアル通信2が初期化されていません")
        return False
    
    try:
        # ポンプ番号に応じて適切なシリアルポートを選択し、コマンド番号を変換
        if 1 <= pump_no <= 3:
            target_ser = ser_1
            port_name = f"COM1-3({SERIAL_PORT_1})"
            command_pump_no = pump_no  # そのまま
        elif 4 <= pump_no <= 6:
            target_ser = ser_2
            port_name = f"COM4-6({SERIAL_PORT_2})"
            command_pump_no = pump_no - 3  # 4→1, 5→2, 6→3
        else:
            print(f"無効なポンプ番号: {pump_no}")
            return False
        
        value_str = value.zfill(6)
        cmd = bytearray(11)
        cmd[0] = 0x02
        cmd[1] = ord(str(command_pump_no))  # 変換されたコマンド番号を使用
        cmd[2] = ord(action)
        for i, c in enumerate(value_str):
            cmd[3 + i] = ord(c)
        cmd[9] = calc_checksum(cmd)
        cmd[10] = 0x03
        
        target_ser.write(cmd)
        print(f"[Pump {pump_no}] {port_name} に送信: {' '.join(f'{b:02X}' for b in cmd)} (コマンド番号: {command_pump_no})")
        return True
    except Exception as e:
        print(f"シリアル送信エラー: {e}")
        return False

def initialize_camera():
    try:
        # jpeg_buffer 等も関数内で設定するので global 宣言を追加
        global camera, camera_initialized, is_raspberry_pi, jpeg_buffer, jpeg_encoder, jpeg_output
        if PICAMERA_AVAILABLE:
            # Picamera2を使用（ラズパイ公式カメラモジュール用）
            print("Picamera2でカメラを初期化中...")

            # カメラモジュールの状態確認
            try:
                import subprocess
                result = subprocess.run(['vcgencmd', 'get_camera'],
                                        capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    print(f"カメラモジュール状態: {result.stdout.strip()}")
                else:
                    print("カメラモジュール状態確認に失敗")
            except Exception as e:
                print(f"カメラモジュール状態確認エラー: {e}")

            # カメラデバイスの確認
            try:
                import os
                video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
                print(f"利用可能なビデオデバイス: {video_devices}")
            except Exception as e:
                print(f"ビデオデバイス確認エラー: {e}")

            camera = Picamera2()

            # カメラ設定
            print("カメラ設定を作成中...")
            config = camera.create_preview_configuration(
                main={"size": (CAM_WIDTH, CAM_HEIGHT), "format": "RGB888"},
                encode="main",
                buffer_count=4  # バッファ数を増やす
            )
            print("カメラ設定を適用中...")
            camera.configure(config)

            # Picamera2 のハードウェアJPEGエンコーダ準備（利用可能なら）
            try:
                jpeg_buffer = _JpegBuffer()
                # JpegEncoder の引数名はバージョンにより差異があるため双方を試す
                try:
                    jpeg_encoder = JpegEncoder(quality=85)
                except TypeError:
                    jpeg_encoder = JpegEncoder(q=85)
                # FileOutput に BufferedIOBase を渡す
                jpeg_output = FileOutput(jpeg_buffer)
                print("ハードウェアJPEGエンコーダを初期化しました")
            except Exception as e:
                print(f"ハードウェアJPEGエンコーダ初期化失敗: {e}")
                jpeg_buffer = None
                jpeg_encoder = None
                jpeg_output = None

            # Picamera2 にフレームレートを明示設定
            try:
                camera.set_controls({"FrameRate": CAM_FPS})
                print(f"FrameRate を {CAM_FPS}fps に設定しました")
            except Exception as e:
                print(f"FrameRate 設定に失敗しました: {e}")

            print("カメラを起動中...")
            camera.start()

            # ハードウェアエンコーダの録画/出力開始（可能なら試行）
            started_hw = False
            if jpeg_encoder and jpeg_output:
                try:
                    camera.start_recording(jpeg_encoder, jpeg_output)
                    print("Picamera2: ハードウェアエンコード録画を開始しました")
                    started_hw = True
                except Exception as e:
                    print(f"Picamera2 ハードウェア録画開始エラー: {e}")
                    # フォールバック：jpeg_buffer を無効化（出力経路は無効化）
                    jpeg_buffer = None
                    jpeg_encoder = None
                    jpeg_output = None

            # 成功とみなす（start() 成功ならカメラは使用可能）
            camera_initialized = True
            is_raspberry_pi = True
            print("Picamera2 カメラ初期化完了（ハードウェアエンコーダ使用:" + ("有効" if started_hw else "無効") + "）")
            return True

        else:
            # OpenCVを使用（PCカメラまたはラズパイカメラモジュール）
            import platform
            is_raspberry_pi_hardware = platform.system() == "Linux" and "raspberry" in platform.machine().lower()

            if is_raspberry_pi_hardware:
                print("OpenCVでラズパイカメラモジュールを初期化中...")
                camera_devices = [0, 10, 11, 12]  # ラズパイ用候補
            else:
                print("OpenCVでPCカメラを初期化中...")
                camera_devices = [0]  # PCカメラ用

            camera_local = None
            for device_id in camera_devices:
                try:
                    print(f"カメラデバイス {device_id} を試行中...")
                    camera_local = cv2.VideoCapture(device_id)

                    if camera_local.isOpened():
                        # カメラ設定
                        camera_local.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
                        camera_local.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
                        camera_local.set(cv2.CAP_PROP_FPS, CAM_FPS)

                        # 要求したFPSが反映されたかログ出力
                        try:
                            actual_fps = camera_local.get(cv2.CAP_PROP_FPS)
                            print(f"要求FPS={CAM_FPS} -> 実際FPS={actual_fps}")
                        except Exception as e:
                            print(f"OpenCV FPS確認エラー: {e}")

                        # テストフレームを取得して動作確認
                        ret, test_frame = camera_local.read()
                        if ret and test_frame is not None:
                            print(f"カメラデバイス {device_id} でテストフレーム取得成功: サイズ={test_frame.shape}")
                            camera = camera_local
                            is_raspberry_pi = is_raspberry_pi_hardware
                            camera_initialized = True
                            camera_type = "ラズパイカメラモジュール" if is_raspberry_pi_hardware else "PCカメラ"
                            print(f"{camera_type}が正常に初期化されました（デバイスID: {device_id}）")
                            return True
                        else:
                            print(f"カメラデバイス {device_id} でテストフレーム取得に失敗")
                            camera_local.release()
                            camera_local = None
                    else:
                        print(f"カメラデバイス {device_id} を開けませんでした")
                except Exception as e:
                    print(f"カメラデバイス {device_id} の初期化エラー: {e}")
                    if camera_local:
                        camera_local.release()
                        camera_local = None

            print("利用可能なカメラデバイスが見つかりませんでした")
            camera_initialized = False
            return False

    except Exception as e:
        print(f"カメラ初期化エラー: {e}")
        print(f"エラーの詳細: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        camera_initialized = False
        return False

def get_frame():
    """カメラからフレームを取得"""
    global camera, camera_initialized, is_raspberry_pi
    
    if not camera_initialized:
        print("カメラが初期化されていません")
        return None
    
    try:
        if is_raspberry_pi and PICAMERA_AVAILABLE:
            # Raspberry Piカメラから画像をキャプチャ
            try:
                frame = camera.capture_array()
                
                if frame is None or frame.size == 0:
                    print("ラズパイカメラから空のフレームが取得されました")
                    return None
                
                # フレームサイズの確認
                if frame.shape[0] == 0 or frame.shape[1] == 0:
                    print(f"ラズパイカメラから無効なフレームサイズ: {frame.shape}")
                    return None
                
                # BGRからRGBに変換（OpenCVはBGR、Web表示はRGB）
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                return frame_rgb
                
            except Exception as e:
                print(f"ラズパイカメラフレーム取得エラー: {e}")
                return None
        else:
            # PCカメラから画像をキャプチャ
            ret, frame = camera.read()
            
            if ret and frame is not None:
                # BGRからRGBに変換
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame_rgb
            else:
                print("PCカメラからフレームが取得できませんでした")
                return None
        
    except Exception as e:
        print(f"フレーム取得エラー: {e}")
        return None

def generate_frames():
    """MJPEGストリーミング用のフレーム生成（ハードウェアJPEGがあれば優先使用）"""
    global jpeg_buffer, camera, camera_initialized, is_raspberry_pi

    frame_count = 0
    error_count = 0

    while True:
        try:
            # ハードウェアエンコード経路（Picamera2 が有効でかつバッファがある場合）
            if is_raspberry_pi and PICAMERA_AVAILABLE and jpeg_buffer is not None:
                jpeg_bytes = jpeg_buffer.get()
                if jpeg_bytes and len(jpeg_bytes) > 0:
                    frame_count += 1
                    if frame_count % 1000 == 0:
                        print(f"ハードウェア経路で送信: {frame_count}フレーム")
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
                    time.sleep(1.0 / max(1, CAM_FPS))
                    continue
                # バッファ空なら通常経路へフォールバック

            # 既存のソフトウェア経路（cv2.imencode）
            frame = get_frame()
            if frame is not None:
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    frame_count += 1
                    if frame_count % 1000 == 0:
                        print(f"ソフトウェア経路で送信: {frame_count}フレーム")
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                else:
                    error_count += 1
                    print("JPEGエンコードに失敗しました（ソフトウェア経路）")
            else:
                error_count += 1
                if error_count % 10 == 0:
                    print(f"フレーム取得エラー: {error_count}回目")

            time.sleep(1.0 / max(1, CAM_FPS))

        except Exception as e:
            print(f"ストリーミング生成エラー: {e}")
            error_count += 1
            time.sleep(1)

def setup_ffmpeg_streaming():
    """FFmpegストリーミングのセットアップ"""
    global ffmpeg_process, ffmpeg_temp_dir, camera_initialized, is_raspberry_pi
    
    if not camera_initialized:
        print("カメラが初期化されていません")
        return False
    
    try:
        # 一時ディレクトリを作成
        ffmpeg_temp_dir = tempfile.mkdtemp(prefix='ffmpeg_stream_')
        print(f"FFmpeg一時ディレクトリを作成: {ffmpeg_temp_dir}")
        
        # カメラ入力ソースを決定
        if is_raspberry_pi and PICAMERA_AVAILABLE:
            # ラズパイカメラの場合
            input_source = "/dev/video0"  # ラズパイカメラのデフォルトデバイス
        else:
            # PCカメラの場合
            input_source = "0"  # OpenCVのデフォルトカメラID
        
        # FFmpegコマンドを構築（Safari互換設定）
        ffmpeg_cmd = [
            'ffmpeg',
            '-f', 'v4l2' if is_raspberry_pi else 'dshow' if IS_WINDOWS else 'v4l2',
            '-i', input_source,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-profile:v', 'baseline',  # Safari互換のためbaselineプロファイルを使用
            '-level', '3.0',           # Safari互換のレベル
            '-pix_fmt', 'yuv420p',     # Safari互換のピクセルフォーマット
            '-crf', '23',
            '-maxrate', '2M',
            '-bufsize', '4M',
            '-g', str(CAM_FPS * 2),    # GOP size
            '-keyint_min', str(CAM_FPS),
            '-sc_threshold', '0',
            '-f', 'hls',
            '-hls_time', str(hls_segment_duration),
            '-hls_list_size', str(hls_playlist_size),
            '-hls_flags', 'delete_segments+independent_segments',  # Safari互換フラグ
            '-hls_allow_cache', '0',
            '-hls_segment_type', 'mpegts',  # 明示的にMPEG-TSを指定
            '-hls_segment_filename', os.path.join(ffmpeg_temp_dir, 'segment_%03d.ts'),
            os.path.join(ffmpeg_temp_dir, 'playlist.m3u8')
        ]
        
        # Windowsの場合はdshowを使用（Safari互換設定）
        if IS_WINDOWS:
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'dshow',
                '-i', f'video={input_source}',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'zerolatency',
                '-profile:v', 'baseline',  # Safari互換のためbaselineプロファイルを使用
                '-level', '3.0',           # Safari互換のレベル
                '-pix_fmt', 'yuv420p',     # Safari互換のピクセルフォーマット
                '-crf', '23',
                '-maxrate', '2M',
                '-bufsize', '4M',
                '-g', str(CAM_FPS * 2),
                '-keyint_min', str(CAM_FPS),
                '-sc_threshold', '0',
                '-f', 'hls',
                '-hls_time', str(hls_segment_duration),
                '-hls_list_size', str(hls_playlist_size),
                '-hls_flags', 'delete_segments+independent_segments',  # Safari互換フラグ
                '-hls_allow_cache', '0',
                '-hls_segment_type', 'mpegts',  # 明示的にMPEG-TSを指定
                '-hls_segment_filename', os.path.join(ffmpeg_temp_dir, 'segment_%03d.ts'),
                os.path.join(ffmpeg_temp_dir, 'playlist.m3u8')
            ]
        
        print(f"FFmpegコマンド: {' '.join(ffmpeg_cmd)}")
        
        # FFmpegプロセスを開始
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=ffmpeg_temp_dir
        )
        
        # プロセスが正常に開始されたか確認
        time.sleep(2)  # プロセス開始を待機
        if ffmpeg_process.poll() is None:
            print("FFmpegストリーミングプロセスが正常に開始されました")
            return True
        else:
            stdout, stderr = ffmpeg_process.communicate()
            print(f"FFmpegプロセス開始エラー: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"FFmpegストリーミングセットアップエラー: {e}")
        return False

def cleanup_ffmpeg_streaming():
    """FFmpegストリーミングのクリーンアップ"""
    global ffmpeg_process, ffmpeg_temp_dir
    
    try:
        if ffmpeg_process:
            print("FFmpegプロセスを終了中...")
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)
            ffmpeg_process = None
        
        if ffmpeg_temp_dir and os.path.exists(ffmpeg_temp_dir):
            print(f"一時ディレクトリを削除中: {ffmpeg_temp_dir}")
            shutil.rmtree(ffmpeg_temp_dir)
            ffmpeg_temp_dir = None
            
    except Exception as e:
        print(f"FFmpegクリーンアップエラー: {e}")

def generate_hls_stream():
    """HLSストリーミング用のプレイリスト生成"""
    global ffmpeg_temp_dir
    
    if not ffmpeg_temp_dir or not os.path.exists(ffmpeg_temp_dir):
        return None
    
    playlist_path = os.path.join(ffmpeg_temp_dir, 'playlist.m3u8')
    
    if os.path.exists(playlist_path):
        try:
            with open(playlist_path, 'r') as f:
                content = f.read()
            return content
        except Exception as e:
            print(f"プレイリスト読み込みエラー: {e}")
            return None
    
    return None

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
    """ビデオストリーミングエンドポイント（MJPEG - 後方互換性のため保持）"""
    response = Response(generate_frames(),
                       mimetype='multipart/x-mixed-replace; boundary=frame')
    # モバイルデバイス互換のためのCORSヘッダーを追加
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/video_feed_hls')
def video_feed_hls():
    """HLSストリーミングエンドポイント（FFmpeg使用）"""
    global ffmpeg_temp_dir
    
    if not ffmpeg_temp_dir or not os.path.exists(ffmpeg_temp_dir):
        return jsonify({'error': 'FFmpegストリーミングが開始されていません'}), 503
    
    playlist_path = os.path.join(ffmpeg_temp_dir, 'playlist.m3u8')
    
    if os.path.exists(playlist_path):
        try:
            response = send_file(playlist_path, mimetype='application/vnd.apple.mpegurl')
            # Safari互換のためのCORSヘッダーを追加
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        except Exception as e:
            print(f"HLSプレイリスト送信エラー: {e}")
            return jsonify({'error': 'プレイリストの送信に失敗しました'}), 500
    else:
        return jsonify({'error': 'プレイリストファイルが見つかりません'}), 404

@app.route('/hls_segment/<segment_name>')
def hls_segment(segment_name):
    """HLSセグメントファイルの配信"""
    global ffmpeg_temp_dir
    
    if not ffmpeg_temp_dir or not os.path.exists(ffmpeg_temp_dir):
        return jsonify({'error': 'FFmpegストリーミングが開始されていません'}), 503
    
    segment_path = os.path.join(ffmpeg_temp_dir, segment_name)
    
    if os.path.exists(segment_path):
        try:
            response = send_file(segment_path, mimetype='video/mp2t')
            # Safari互換のためのCORSヘッダーを追加
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
        except Exception as e:
            print(f"HLSセグメント送信エラー: {e}")
            return jsonify({'error': 'セグメントの送信に失敗しました'}), 500
    else:
        return jsonify({'error': 'セグメントファイルが見つかりません'}), 404

@app.route('/api/status')
def api_status():
    """カメラ状態API"""
    # カメラの詳細情報を取得
    camera_info = {
        'initialized': camera_initialized,
        'type': 'Raspberry Pi' if is_raspberry_pi else 'PC',
        'picamera_available': PICAMERA_AVAILABLE
    }
    
    # カメラが初期化されている場合、追加情報を取得
    if camera_initialized and camera is not None:
        try:
            if is_raspberry_pi and PICAMERA_AVAILABLE:
                # ラズパイカメラの情報
                camera_info.update({
                    'status': 'active',
                    'resolution': f"{CAM_WIDTH}x{CAM_HEIGHT}",
                    'fps': CAM_FPS
                })
            else:
                # PCカメラの情報
                camera_info.update({
                    'status': 'active' if camera.isOpened() else 'inactive',
                    'resolution': f"{int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))}",
                    'fps': int(camera.get(cv2.CAP_PROP_FPS))
                })
        except Exception as e:
            camera_info['error'] = str(e)
    
    return jsonify({
        'camera': camera_info,
        'serial_initialized_1': serial_initialized_1,  # ハイセラポンプ1-3
        'serial_initialized_2': serial_initialized_2,  # ハイセラポンプ4-6
        'syringe_serial_initialized': syringe_serial_initialized,
        'hysera_port1_status': serial_initialized_1 and ser_1 is not None,  # COM18（ポンプ1-3）
        'hysera_port2_status': serial_initialized_2 and ser_2 is not None,  # COM20（ポンプ4-6）
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
    global camera, camera_initialized, is_raspberry_pi
    
    try:
        print("カメラ再起動を開始します...")
        
        if camera is not None:
            if is_raspberry_pi and PICAMERA_AVAILABLE:
                print("ラズパイカメラを停止中...")
                camera.stop()
                camera.close()
            else:
                print("PCカメラを停止中...")
                camera.release()
        
        # カメラ変数をリセット
        camera = None
        camera_initialized = False
        
        # 少し待機してから再初期化
        time.sleep(1)
        
        success = initialize_camera()
        
        if success:
            print("カメラ再起動が完了しました")
            return jsonify({
                'success': True,
                'message': 'カメラを再起動しました',
                'camera_type': 'Raspberry Pi' if is_raspberry_pi else 'PC'
            })
        else:
            print("カメラ再起動に失敗しました")
            return jsonify({
                'success': False,
                'message': 'カメラ再起動に失敗しました'
            })
        
    except Exception as e:
        print(f"カメラ再起動エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

@app.route('/api/start_ffmpeg_streaming')
def api_start_ffmpeg_streaming():
    """FFmpegストリーミング開始API"""
    global ffmpeg_process
    
    try:
        if ffmpeg_process and ffmpeg_process.poll() is None:
            return jsonify({
                'success': False,
                'message': 'FFmpegストリーミングは既に実行中です'
            })
        
        success = setup_ffmpeg_streaming()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'FFmpegストリーミングを開始しました',
                'hls_url': '/video_feed_hls'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'FFmpegストリーミングの開始に失敗しました'
            })
        
    except Exception as e:
        print(f"FFmpegストリーミング開始エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

@app.route('/api/stop_ffmpeg_streaming')
def api_stop_ffmpeg_streaming():
    """FFmpegストリーミング停止API"""
    try:
        cleanup_ffmpeg_streaming()
        return jsonify({
            'success': True,
            'message': 'FFmpegストリーミングを停止しました'
        })
        
    except Exception as e:
        print(f"FFmpegストリーミング停止エラー: {e}")
        return jsonify({
            'success': False,
            'message': f'エラー: {str(e)}'
        }), 500

@app.route('/api/ffmpeg_status')
def api_ffmpeg_status():
    """FFmpegストリーミング状態API"""
    global ffmpeg_process, ffmpeg_temp_dir
    
    is_running = ffmpeg_process is not None and ffmpeg_process.poll() is None
    temp_dir_exists = ffmpeg_temp_dir is not None and os.path.exists(ffmpeg_temp_dir)
    
    return jsonify({
        'ffmpeg_running': is_running,
        'temp_dir_exists': temp_dir_exists,
        'temp_dir_path': ffmpeg_temp_dir if temp_dir_exists else None,
        'hls_url': '/video_feed_hls' if is_running else None
    })

@app.route("/api/pump_control")
def api_pump_control():
    """ポンプ制御API"""
    pump = request.args.get("pump", "1")
    action = request.args.get("action", "M")
    value = request.args.get("value", "000000")
    
    try:
        pump = int(pump)
    except ValueError:
        return jsonify({
            'success': False,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': []
        })
    
    # コマンドの内容を生成（送信前に）
    value_str = value.zfill(6)
    cmd = bytearray(11)
    cmd[0] = 0x02
    
    # ポンプ番号に応じてコマンド番号を変換
    if 1 <= pump <= 3:
        command_pump_no = pump  # そのまま
    elif 4 <= pump <= 6:
        command_pump_no = pump - 3  # 4→1, 5→2, 6→3
    else:
        return jsonify({
            'success': False,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': []
        })
    
    cmd[1] = ord(str(command_pump_no))  # 変換されたコマンド番号を使用
    cmd[2] = ord(action)
    for i, c in enumerate(value_str):
        cmd[3 + i] = ord(c)
    cmd[9] = calc_checksum(cmd)
    cmd[10] = 0x03
    
    success = send_serial_command(pump, action, value)
    
    return jsonify({
        'success': success,
        'message': f'送信完了: pump={pump}, action={action}, value={value}' if success else '送信失敗',
        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
    })

@app.route("/api/get_current")
def api_get_current():
    """電流値取得API"""
    pump = request.args.get("pump", "1")
    
    try:
        pump = int(pump)
    except ValueError:
        return jsonify({
            'success': False,
            'current': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': []
        })
    
    # 電流データ取得コマンドを生成（送信前に）
    value_str = "000000"
    cmd = bytearray(11)
    cmd[0] = 0x02
    
    # ポンプ番号に応じてコマンド番号を変換
    if 1 <= pump <= 3:
        command_pump_no = pump  # そのまま
    elif 4 <= pump <= 6:
        command_pump_no = pump - 3  # 4→1, 5→2, 6→3
    else:
        return jsonify({
            'success': False,
            'current': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': list(cmd)
        })
    
    cmd[1] = ord(str(command_pump_no))  # 変換されたコマンド番号を使用
    cmd[2] = ord("C")  # 電流値取得コマンド
    for i, c in enumerate(value_str):
        cmd[3 + i] = ord(c)
    cmd[9] = calc_checksum(cmd)
    cmd[10] = 0x03
    
    # 電流データ取得コマンドを送信
    success = send_serial_command(pump, "C", "000000")
    
    if not success:
        return jsonify({
            'success': False,
            'current': 0,
            'message': '送信失敗',
            'command_bytes': list(cmd)  # 送信コマンドの内容を追加
        })
    
    # 応答を待機（最大1秒）
    import time
    start_time = time.time()
    response = None
    
    # ポンプ番号に応じて適切なシリアルポートを選択
    if 1 <= pump <= 3:
        target_ser = ser_1
        port_name = f"COM1-3({SERIAL_PORT_1})"
    elif 4 <= pump <= 6:
        target_ser = ser_2
        port_name = f"COM4-6({SERIAL_PORT_2})"
    else:
        return jsonify({
            'success': False,
            'current': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': list(cmd)
        })
    
    while time.time() - start_time < 1.0:
        if target_ser.in_waiting >= 10:  # 10バイトの応答を待機
            response = target_ser.read(10)
            break
        time.sleep(0.01)
    
    if response and len(response) == 10:
        # 応答フォーマット: STX + ポンプNo + 電流値(符号+5桁整数) + CS + ETX
        if response[0] == 0x02 and response[9] == 0x03:
            # チェックサム検証
            checksum = 0
            for i in range(1, 8):
                checksum ^= response[i]
            
            if checksum == response[8]:
                # 電流値を解析
                current_str = response[2:8].decode('ascii')
                try:
                    current = int(current_str)
                    return jsonify({
                        'success': True,
                        'current': current,
                        'message': f'電流値取得完了: {current}mA',
                        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
                    })
                except ValueError:
                    return jsonify({
                        'success': False,
                        'current': 0,
                        'message': '電流値解析エラー',
                        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
                    })
    
    return jsonify({
        'success': False,
        'current': 0,
        'message': '応答タイムアウトまたはエラー',
        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
    })

@app.route("/api/get_rpm")
def api_get_rpm():
    """回転数取得API"""
    pump = request.args.get("pump", "1")
    
    try:
        pump = int(pump)
    except ValueError:
        return jsonify({
            'success': False,
            'rpm': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': []
        })
    
    # 回転数データ取得コマンドを生成（送信前に）
    value_str = "000000"
    cmd = bytearray(11)
    cmd[0] = 0x02
    
    # ポンプ番号に応じてコマンド番号を変換
    if 1 <= pump <= 3:
        command_pump_no = pump  # そのまま
    elif 4 <= pump <= 6:
        command_pump_no = pump - 3  # 4→1, 5→2, 6→3
    else:
        return jsonify({
            'success': False,
            'rpm': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': list(cmd)
        })
    
    cmd[1] = ord(str(command_pump_no))  # 変換されたコマンド番号を使用
    cmd[2] = ord("X")  # 回転数取得コマンド
    for i, c in enumerate(value_str):
        cmd[3 + i] = ord(c)
    cmd[9] = calc_checksum(cmd)
    cmd[10] = 0x03
    
    # 回転数データ取得コマンドを送信
    success = send_serial_command(pump, "X", "000000")
    
    if not success:
        return jsonify({
            'success': False,
            'rpm': 0,
            'message': '送信失敗',
            'command_bytes': list(cmd)  # 送信コマンドの内容を追加
        })
    
    # 応答を待機（最大1秒）
    import time
    start_time = time.time()
    response = None
    
    # ポンプ番号に応じて適切なシリアルポートを選択
    if 1 <= pump <= 3:
        target_ser = ser_1
        port_name = f"COM1-3({SERIAL_PORT_1})"
    elif 4 <= pump <= 6:
        target_ser = ser_2
        port_name = f"COM4-6({SERIAL_PORT_2})"
    else:
        return jsonify({
            'success': False,
            'rpm': 0,
            'message': f'無効なポンプ番号: {pump}',
            'command_bytes': list(cmd)
        })
    
    while time.time() - start_time < 1.0:
        if target_ser.in_waiting >= 10:  # 10バイトの応答を待機
            response = target_ser.read(10)
            break
        time.sleep(0.01)
    
    if response and len(response) == 10:
        # 応答フォーマット: STX + ポンプNo + RPM(6桁整数) + CS + ETX
        if response[0] == 0x02 and response[9] == 0x03:
            # チェックサム検証
            checksum = 0
            for i in range(1, 8):
                checksum ^= response[i]
            
            if checksum == response[8]:
                # 回転数を解析
                rpm_str = response[2:8].decode('ascii')
                try:
                    rpm = int(rpm_str)
                    return jsonify({
                        'success': True,
                        'rpm': rpm,
                        'message': f'回転数取得完了: {rpm}rpm',
                        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
                    })
                except ValueError:
                    return jsonify({
                        'success': False,
                        'rpm': 0,
                        'message': '回転数解析エラー',
                        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
                    })
    
    return jsonify({
        'success': False,
        'rpm': 0,
        'message': '応答タイムアウトまたはエラー',
        'command_bytes': list(cmd)  # 送信コマンドの内容を追加
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
            success, command_bytes = controller.send_command(f"D{steps}R", selected_address)
            message = f"上移動コマンド送信完了（{steps}ステップ）" if success else "上移動コマンド送信失敗"
        elif action == "move_down":
            success, command_bytes = controller.send_command(f"P{steps}R", selected_address)
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

# --- 追加: カメラ設定を適用する関数と API エンドポイント ---
def apply_camera_settings():
    """現在の CAM_* 設定をカメラに適用"""
    global camera, is_raspberry_pi, PICAMERA_AVAILABLE
    try:
        if camera is None:
            print("apply_camera_settings: カメラ未初期化")
            return False
        if is_raspberry_pi and PICAMERA_AVAILABLE:
            print(f"Picamera2 に設定を適用: {CAM_WIDTH}x{CAM_HEIGHT}@{CAM_FPS}fps")
            try:
                # 再設定は一度停止して configure -> start
                camera.stop()
            except Exception:
                pass
            config = camera.create_preview_configuration(
                main={"size": (CAM_WIDTH, CAM_HEIGHT), "format": "RGB888"},
                buffer_count=4
            )
            camera.configure(config)
            try:
                camera.set_controls({"FrameRate": CAM_FPS})
            except Exception as e:
                print(f"FrameRate設定エラー: {e}")
            camera.start()
        else:
            print(f"OpenCV カメラに設定を適用: {CAM_WIDTH}x{CAM_HEIGHT}@{CAM_FPS}fps")
            try:
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
                camera.set(cv2.CAP_PROP_FPS, CAM_FPS)
            except Exception as e:
                print(f"OpenCV設定エラー: {e}")
        return True
    except Exception as e:
        print(f"apply_camera_settings エラー: {e}")
        return False

@app.route('/api/get_camera_settings')
def api_get_camera_settings():
    return jsonify({
        'width': CAM_WIDTH,
        'height': CAM_HEIGHT,
        'fps': CAM_FPS,
        'camera_initialized': camera_initialized
    })

@app.route('/api/set_camera_settings')
def api_set_camera_settings():
    """例: /api/set_camera_settings?width=1280&height=720&fps=15"""
    global CAM_WIDTH, CAM_HEIGHT, CAM_FPS
    w = request.args.get('width')
    h = request.args.get('height')
    f = request.args.get('fps')
    try:
        if w is not None:
            CAM_WIDTH = int(w)
        if h is not None:
            CAM_HEIGHT = int(h)
        if f is not None:
            CAM_FPS = int(f)
    except ValueError:
        return jsonify({'success': False, 'message': '無効なパラメータ'}), 400

    success = apply_camera_settings()
    return jsonify({
        'success': success,
        'width': CAM_WIDTH,
        'height': CAM_HEIGHT,
        'fps': CAM_FPS
    })

# --- 変更: BufferedIOBase を継承する JPEG バッファ ---
class _JpegBuffer(io.BufferedIOBase):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()
        self._data = b''

    def writable(self):
        return True

    def write(self, b):
        """FileOutput から渡される JPEG バイト列を受け取る"""
        if not isinstance(b, (bytes, bytearray)):
            b = bytes(b)
        with self.lock:
            self._data = b
        # 書き込んだバイト数を返す（BufferedIOBase の規約）
        return len(b)

    def flush(self):
        # 何もしない（必要なら実装）
        return None

    def get(self):
        with self.lock:
            return self._data

# グローバル変数
jpeg_buffer = None
jpeg_encoder = None
jpeg_output = None

if __name__ == '__main__':
    import argparse
    import atexit
    import signal
    
    # クリーンアップ関数を登録
    def cleanup_on_exit():
        print("\nアプリケーション終了処理を開始します...")
        cleanup_ffmpeg_streaming()
        print("クリーンアップが完了しました")
    
    atexit.register(cleanup_on_exit)
    
    # シグナルハンドラーを登録（Ctrl+C等）
    def signal_handler(signum, frame):
        print(f"\nシグナル {signum} を受信しました。終了処理を開始します...")
        cleanup_on_exit()
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='ラズパイカメラストリーミング + ポンプ制御Webサーバー')
    parser.add_argument('--debug', action='store_true', help='デバッグモードで起動')
    parser.add_argument('--port', type=int, default=5000, help='ポート番号（デフォルト: 5000）')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='ホストアドレス（デフォルト: 0.0.0.0）')
    parser.add_argument('--use-ffmpeg', action='store_true', help='FFmpegストリーミングを使用（デフォルト: MJPEG）')
    # OSに応じたデフォルトポート設定
    default_port_1 = 'COM18' if IS_WINDOWS else '/dev/ttyACM0'
    default_port_2 = 'COM20' if IS_WINDOWS else '/dev/ttyACM1'
    default_syringe_port = 'COM19' if IS_WINDOWS else '/dev/ttyACM2'
    
    parser.add_argument('--serial-port-1', type=str, default=default_port_1, 
                       help=f'ハイセラポンプ1-3用シリアルポート（デフォルト: {default_port_1}）')
    parser.add_argument('--serial-port-2', type=str, default=default_port_2, 
                       help=f'ハイセラポンプ4-6用シリアルポート（デフォルト: {default_port_2}）')
    parser.add_argument('--syringe-serial-port', type=str, default=default_syringe_port, 
                       help=f'シリンジポンプ用シリアルポート（デフォルト: {default_syringe_port}）')
    
    args = parser.parse_args()
    
    # シリアルポート設定を更新（ハイセラ／シリンジ）
    # コマンドライン引数で指定された場合は上書き
    SERIAL_PORT_1 = args.serial_port_1
    SERIAL_PORT_2 = args.serial_port_2
    SYRINGE_SERIAL_PORT = args.syringe_serial_port
    
    # システム情報表示
    print("=" * 50)
    print("システム情報:")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Python: {platform.python_version()}")
    print(f"カメラライブラリ: {'Picamera2' if PICAMERA_AVAILABLE else 'OpenCV'}")
    print("=" * 50)
    
    # シリアルポート設定表示
    print("\nシリアルポート設定:")
    print(f"ハイセラポンプ1-3用: {SERIAL_PORT_1}")
    print(f"ハイセラポンプ4-6用: {SERIAL_PORT_2}")
    print(f"シリンジポンプ用: {SYRINGE_SERIAL_PORT}")
    print("=" * 50)
    
    # カメラ初期化前のシステムチェック
    print("\nカメラ初期化前のシステムチェック...")
    if not IS_WINDOWS:
        try:
            # カメラモジュールの状態確認
            import subprocess
            result = subprocess.run(['vcgencmd', 'get_camera'], 
                                 capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✓ カメラモジュール状態: {result.stdout.strip()}")
            else:
                print("✗ カメラモジュール状態確認に失敗")
        except Exception as e:
            print(f"✗ カメラモジュール状態確認エラー: {e}")
        
        try:
            # カメラデバイスの確認
            import os
            video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
            if video_devices:
                print(f"✓ 利用可能なビデオデバイス: {video_devices}")
                # ラズパイカメラモジュール用のデバイスを特定
                raspberry_camera_devices = [d for d in video_devices if d in ['video0', 'video10', 'video11', 'video12']]
                if raspberry_camera_devices:
                    print(f"✓ ラズパイカメラモジュール用デバイス: {raspberry_camera_devices}")
                else:
                    print("⚠ ラズパイカメラモジュール用デバイスが見つかりません")
            else:
                print("✗ ビデオデバイスが見つかりません")
        except Exception as e:
            print(f"✗ ビデオデバイス確認エラー: {e}")
        
        # OpenCVのバージョン確認
        try:
            opencv_version = cv2.__version__
            print(f"✓ OpenCVバージョン: {opencv_version}")
        except Exception as e:
            print(f"✗ OpenCVバージョン確認エラー: {e}")
    
    # カメラ初期化
    print("\nカメラ初期化を開始します...")
    camera_success = initialize_camera()
    
    if camera_success:
        print(f"✓ カメラ初期化成功: {'Raspberry Pi' if is_raspberry_pi else 'PC'}カメラ")
    else:
        print("✗ カメラ初期化失敗")
        if PICAMERA_AVAILABLE:
            print("   → ラズパイにカメラモジュールが接続されているか確認してください")
            print("   → カメラモジュールの電源が入っているか確認してください")
            print("   → カメラケーブルが正しく接続されているか確認してください")
        else:
            print("   → PCにWebカメラが接続されているか確認してください")
    
    # シリアル通信初期化（ハイセラ／シリンジ）
    print("\nシリアル通信初期化を開始します...")
    serial_success = initialize_serial()
    syringe_serial_success = initialize_syringe_serial()
    
    print("\n" + "=" * 50)
    print("Webサーバーを起動します...")
    print(f"ブラウザで http://localhost:{args.port} にアクセスしてください")
    print(f"ポンプ制御ページ: http://localhost:{args.port}/pump_control")
    print("=" * 50)
    
    if not serial_success:
        print("警告: ハイセラポンプ用シリアル通信の初期化に失敗しました。")
        print(f"シリアルポート {SERIAL_PORT_1}（ポンプ1-3用）または {SERIAL_PORT_2}（ポンプ4-6用）が利用可能か確認してください。")
        if not IS_WINDOWS:
            print("   → ラズパイでUSBデバイスが認識されているか確認してください")
            print("   → デバイス権限があるか確認してください")
    if not syringe_serial_success:
        print("警告: シリンジポンプ用シリアル通信の初期化に失敗しました。")
        print(f"シリアルポート {SYRINGE_SERIAL_PORT} が利用可能か確認してください。")
        if not IS_WINDOWS:
            print("   → ラズパイでUSBデバイスが認識されているか確認してください")
            print("   → デバイス権限があるか確認してください")
    
    # FFmpegストリーミングの自動開始（オプション）
    if args.use_ffmpeg and camera_success:
        print("\nFFmpegストリーミングを自動開始します...")
        ffmpeg_success = setup_ffmpeg_streaming()
        if ffmpeg_success:
            print("✓ FFmpegストリーミングが自動開始されました")
            print(f"  HLS URL: http://localhost:{args.port}/video_feed_hls")
        else:
            print("✗ FFmpegストリーミングの自動開始に失敗しました")
            print("  MJPEGストリーミングを使用します")
    
    # 開発サーバー起動（本番環境ではgunicorn等を使用）
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)