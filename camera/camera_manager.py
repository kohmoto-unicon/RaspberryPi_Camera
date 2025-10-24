#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
カメラ管理クラス
"""

import cv2
import time
import io
import threading
from config import (
    CAM_WIDTH, CAM_HEIGHT, CAM_FPS,
    PICAMERA_AVAILABLE, IS_WINDOWS, IS_RASPBERRY_PI,
    DEBUG_STREAM_LOG
)

# Raspberry Pi専用ライブラリのインポート
if PICAMERA_AVAILABLE:
    from picamera2 import Picamera2
    from picamera2.encoders import JpegEncoder
    from picamera2.outputs import FileOutput


class _JpegBuffer(io.BufferedIOBase):
    """JPEG バッファクラス（Picamera2用）"""
    
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
        return len(b)
    
    def flush(self):
        return None
    
    def get(self):
        with self.lock:
            return self._data


class CameraManager:
    """カメラ管理クラス"""
    
    def __init__(self):
        """初期化"""
        self.camera = None
        self.is_initialized = False
        self.is_raspberry_pi = IS_RASPBERRY_PI
        self.use_picamera = PICAMERA_AVAILABLE and IS_RASPBERRY_PI
        
        # Picamera2用
        self.jpeg_buffer = None
        self.jpeg_encoder = None
        self.jpeg_output = None
        
        # 設定
        self.width = CAM_WIDTH
        self.height = CAM_HEIGHT
        self.fps = CAM_FPS
    
    def initialize(self):
        """カメラを初期化"""
        try:
            if self.use_picamera:
                return self._initialize_picamera()
            else:
                return self._initialize_opencv()
        except Exception as e:
            print(f"カメラ初期化エラー: {e}")
            import traceback
            traceback.print_exc()
            self.is_initialized = False
            return False
    
    def _initialize_picamera(self):
        """Picamera2を初期化"""
        print("Picamera2でカメラを初期化中...")
        
        # カメラモジュールの状態確認
        try:
            import subprocess
            result = subprocess.run(['vcgencmd', 'get_camera'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"カメラモジュール状態: {result.stdout.strip()}")
        except Exception as e:
            print(f"カメラモジュール状態確認エラー: {e}")
        
        # カメラデバイスの確認
        try:
            import os
            video_devices = [f for f in os.listdir('/dev') if f.startswith('video')]
            print(f"利用可能なビデオデバイス: {video_devices}")
        except Exception as e:
            print(f"ビデオデバイス確認エラー: {e}")
        
        self.camera = Picamera2()
        
        # カメラ設定
        print("カメラ設定を作成中...")
        config = self.camera.create_preview_configuration(
            main={"size": (self.width, self.height), "format": "RGB888"},
            encode="main",
            buffer_count=4
        )
        print("カメラ設定を適用中...")
        self.camera.configure(config)
        
        # ハードウェアJPEGエンコーダ準備
        try:
            self.jpeg_buffer = _JpegBuffer()
            try:
                self.jpeg_encoder = JpegEncoder(quality=85)
            except TypeError:
                self.jpeg_encoder = JpegEncoder(q=85)
            self.jpeg_output = FileOutput(self.jpeg_buffer)
            print("ハードウェアJPEGエンコーダを初期化しました")
        except Exception as e:
            print(f"ハードウェアJPEGエンコーダ初期化失敗: {e}")
            self.jpeg_buffer = None
            self.jpeg_encoder = None
            self.jpeg_output = None
        
        # フレームレート設定
        try:
            self.camera.set_controls({"FrameRate": self.fps})
            print(f"FrameRate を {self.fps}fps に設定しました")
        except Exception as e:
            print(f"FrameRate 設定に失敗しました: {e}")
        
        print("カメラを起動中...")
        self.camera.start()
        
        # ハードウェアエンコーダの録画開始
        started_hw = False
        if self.jpeg_encoder and self.jpeg_output:
            try:
                self.camera.start_recording(self.jpeg_encoder, self.jpeg_output)
                print("Picamera2: ハードウェアエンコード録画を開始しました")
                started_hw = True
            except Exception as e:
                print(f"Picamera2 ハードウェア録画開始エラー: {e}")
                self.jpeg_buffer = None
                self.jpeg_encoder = None
                self.jpeg_output = None
        
        self.is_initialized = True
        self.is_raspberry_pi = True
        print(f"Picamera2 カメラ初期化完了（ハードウェアエンコーダ: {'有効' if started_hw else '無効'}）")
        return True
    
    def _initialize_opencv(self):
        """OpenCVでカメラを初期化"""
        import platform
        is_raspberry_pi_hardware = platform.system() == "Linux" and "raspberry" in platform.machine().lower()
        
        if is_raspberry_pi_hardware:
            print("OpenCVでラズパイカメラモジュールを初期化中...")
            camera_devices = [0, 10, 11, 12]
        else:
            print("OpenCVでPCカメラを初期化中...")
            camera_devices = [0]
        
        camera_local = None
        for device_id in camera_devices:
            try:
                print(f"カメラデバイス {device_id} を試行中...")
                
                if IS_WINDOWS:
                    camera_local = cv2.VideoCapture(device_id, cv2.CAP_DSHOW)
                else:
                    camera_local = cv2.VideoCapture(device_id)
                
                if camera_local.isOpened():
                    camera_local.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    camera_local.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    camera_local.set(cv2.CAP_PROP_FPS, self.fps)
                    
                    actual_fps = camera_local.get(cv2.CAP_PROP_FPS)
                    print(f"要求FPS={self.fps} -> 実際FPS={actual_fps}")
                    
                    ret, test_frame = camera_local.read()
                    if ret and test_frame is not None:
                        print(f"カメラデバイス {device_id} でテストフレーム取得成功: サイズ={test_frame.shape}")
                        self.camera = camera_local
                        self.is_raspberry_pi = is_raspberry_pi_hardware
                        self.is_initialized = True
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
        self.is_initialized = False
        return False
    
    def get_frame(self):
        """カメラからフレームを取得"""
        if not self.is_initialized:
            return None
        
        try:
            if self.is_raspberry_pi and self.use_picamera:
                frame = self.camera.capture_array()
                
                if frame is None or frame.size == 0:
                    return None
                
                if frame.shape[0] == 0 or frame.shape[1] == 0:
                    return None
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame_rgb
            else:
                ret, frame = self.camera.read()
                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    return frame_rgb
                return None
        except Exception as e:
            print(f"フレーム取得エラー: {e}")
            return None
    
    def generate_mjpeg_stream(self):
        """MJPEGストリーミング用のフレーム生成"""
        frame_count = 0
        error_count = 0
        
        while True:
            try:
                if not self.is_initialized:
                    time.sleep(0.1)
                    continue
                
                # カメラが停止されている場合は終了
                if self.is_raspberry_pi and self.use_picamera and self.camera is None:
                    print("カメラが停止されました。フレーム生成を終了します。")
                    break
                
                # ハードウェアエンコード経路
                if self.is_raspberry_pi and self.use_picamera and self.jpeg_buffer is not None:
                    jpeg_bytes = self.jpeg_buffer.get()
                    if jpeg_bytes and len(jpeg_bytes) > 0:
                        frame_count += 1
                        if DEBUG_STREAM_LOG and frame_count % 1000 == 0:
                            print(f"ハードウェア経路で送信: {frame_count}フレーム")
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')
                        time.sleep(1.0 / max(1, self.fps))
                        continue
                
                # ソフトウェア経路
                frame = self.get_frame()
                if frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret:
                        frame_count += 1
                        if DEBUG_STREAM_LOG and frame_count % 1000 == 0:
                            print(f"ソフトウェア経路で送信: {frame_count}フレーム")
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                    else:
                        error_count += 1
                else:
                    error_count += 1
                    if error_count % 10 == 0:
                        print(f"フレーム取得エラー: {error_count}回目")
                
                time.sleep(1.0 / max(1, self.fps))
            
            except Exception as e:
                print(f"ストリーミング生成エラー: {e}")
                error_count += 1
                
                if self.is_raspberry_pi and self.use_picamera and self.camera is None:
                    break
                
                if error_count > 100:
                    print("エラーが多すぎます。フレーム生成を終了します。")
                    break
                
                time.sleep(1)
    
    def close(self):
        """カメラを停止"""
        try:
            if self.camera:
                print("カメラを停止中...")
                if self.is_raspberry_pi and self.use_picamera:
                    self.camera.stop()
                    self.camera.close()
                else:
                    self.camera.release()
                self.camera = None
            
            self.jpeg_encoder = None
            self.jpeg_output = None
            self.jpeg_buffer = None
            
            print("カメラのクリーンアップが完了しました")
        except Exception as e:
            print(f"カメラクリーンアップエラー: {e}")
    
    def restart(self):
        """カメラを再起動"""
        print("カメラ再起動を開始します...")
        self.close()
        time.sleep(1)
        success = self.initialize()
        if success:
            print("カメラ再起動が完了しました")
        else:
            print("カメラ再起動に失敗しました")
        return success
    
    def update_settings(self, width=None, height=None, fps=None):
        """カメラ設定を更新"""
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height
        if fps is not None:
            self.fps = fps
        
        # 設定を適用
        return self._apply_settings()
    
    def _apply_settings(self):
        """現在の設定をカメラに適用"""
        try:
            if self.camera is None:
                print("カメラ未初期化")
                return False
            
            if self.is_raspberry_pi and self.use_picamera:
                print(f"Picamera2 に設定を適用: {self.width}x{self.height}@{self.fps}fps")
                try:
                    self.camera.stop()
                except Exception:
                    pass
                
                config = self.camera.create_preview_configuration(
                    main={"size": (self.width, self.height), "format": "RGB888"},
                    buffer_count=4
                )
                self.camera.configure(config)
                
                try:
                    self.camera.set_controls({"FrameRate": self.fps})
                except Exception as e:
                    print(f"FrameRate設定エラー: {e}")
                
                self.camera.start()
            else:
                print(f"OpenCV カメラに設定を適用: {self.width}x{self.height}@{self.fps}fps")
                try:
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self.camera.set(cv2.CAP_PROP_FPS, self.fps)
                except Exception as e:
                    print(f"OpenCV設定エラー: {e}")
            
            return True
        except Exception as e:
            print(f"設定適用エラー: {e}")
            return False
