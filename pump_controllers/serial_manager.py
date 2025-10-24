#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信管理基底クラス
"""

import serial  # pyserial
import threading
import time
from config import DEBUG_SERIAL_LOG


class SerialManager:
    """シリアル通信の基底クラス"""
    
    def __init__(self, port, baud_rate, timeout=1, name="SerialDevice"):
        """
        初期化
        
        Args:
            port: シリアルポート名
            baud_rate: ボーレート
            timeout: タイムアウト（秒）
            name: デバイス名（ログ用）
        """
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.name = name
        self.serial_connection = None
        self.is_initialized = False
        self.lock = threading.Lock()
    
    def initialize(self):
        """シリアル接続を初期化"""
        try:
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] ポート {self.port} を開こうとしています...")
            
            self.serial_connection = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=self.timeout
            )
            self.is_initialized = True
            
            if DEBUG_SERIAL_LOG:
                print(f"✓ [{self.name}] シリアル通信が正常に初期化されました: {self.port}")
            
            return True
        
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"✗ [{self.name}] シリアル通信初期化エラー: {e}")
            self.is_initialized = False
            return False
    
    def close(self):
        """シリアル接続を閉じる"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                if DEBUG_SERIAL_LOG:
                    print(f"[{self.name}] シリアルポートを閉じ中...")
                self.serial_connection.close()
                self.is_initialized = False
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] シリアルポートクローズエラー: {e}")
    
    def is_connected(self):
        """接続状態を確認"""
        return (self.is_initialized and 
                self.serial_connection is not None and 
                self.serial_connection.is_open)
    
    def write(self, data):
        """
        データを送信
        
        Args:
            data: 送信するバイト列
            
        Returns:
            bool: 送信成功時True
        """
        if not self.is_connected():
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] シリアル通信が初期化されていません")
            return False
        
        try:
            with self.lock:
                self.serial_connection.write(data)
                if DEBUG_SERIAL_LOG:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    print(f"[{self.name}] 送信: {hex_str}")
            return True
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] 送信エラー: {e}")
            return False
    
    def read(self, size=1):
        """
        データを受信
        
        Args:
            size: 読み取るバイト数
            
        Returns:
            bytes: 受信したデータ
        """
        if not self.is_connected():
            return b''
        
        try:
            with self.lock:
                data = self.serial_connection.read(size)
                if data and DEBUG_SERIAL_LOG:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    print(f"[{self.name}] 受信: {hex_str}")
                return data
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] 受信エラー: {e}")
            return b''
    
    def clear_buffer(self):
        """受信バッファをクリア"""
        if not self.is_connected():
            return
        
        try:
            with self.lock:
                if self.serial_connection.in_waiting > 0:
                    old_data = self.serial_connection.read(self.serial_connection.in_waiting)
                    if DEBUG_SERIAL_LOG:
                        print(f"[{self.name}] バッファクリア: {old_data.hex()} ({len(old_data)} bytes)")
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"[{self.name}] バッファクリアエラー: {e}")
    
    def wait_for_response(self, expected_size, timeout=1.0):
        """
        レスポンスを待機
        
        Args:
            expected_size: 期待するバイト数
            timeout: タイムアウト（秒）
            
        Returns:
            bytes: 受信したデータ、タイムアウト時はNone
        """
        if not self.is_connected():
            return None
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.serial_connection.in_waiting >= expected_size:
                return self.read(expected_size)
            time.sleep(0.01)
        
        if DEBUG_SERIAL_LOG:
            print(f"[{self.name}] 応答タイムアウト（期待: {expected_size}バイト）")
        return None
