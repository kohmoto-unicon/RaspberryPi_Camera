#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリアル通信管理基底クラス

このクラスはシリアル通信の基本機能を提供します。
スレッドセーフな読み書き、自動再接続、エラーハンドリングをサポートします。

主な機能:
- スレッドセーフなシリアル通信
- 自動再接続機能
- バッファ管理
- タイムアウト制御
- 詳細なログ出力
"""

import serial  # pyserial
import threading
import time
import logging
from typing import Optional
from config import DEBUG_SERIAL_LOG

# ロガー設定
logger = logging.getLogger(__name__)
if DEBUG_SERIAL_LOG:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


class SerialManager:
    """
    シリアル通信の基底クラス
    
    スレッドセーフなシリアル通信を提供します。
    自動再接続、エラーハンドリング、詳細なログ機能を備えています。
    
    Attributes:
        port: シリアルポート名
        baud_rate: ボーレート
        timeout: タイムアウト（秒）
        name: デバイス名
        serial_connection: シリアル接続インスタンス
        is_initialized: 初期化状態
        lock: スレッドロック
    """
    
    def __init__(self, port: str, baud_rate: int, timeout: float = 1.0, 
                 name: str = "SerialDevice", auto_reconnect: bool = True):
        """
        初期化
        
        Args:
            port: シリアルポート名
            baud_rate: ボーレート
            timeout: タイムアウト（秒）
            name: デバイス名（ログ用）
            auto_reconnect: 自動再接続を有効にするか
        """
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self.name = name
        self.auto_reconnect = auto_reconnect
        self.serial_connection = None
        self.is_initialized = False
        self.lock = threading.Lock()
        
        # 統計情報
        self._bytes_sent = 0
        self._bytes_received = 0
        self._error_count = 0
        self._last_error_time = 0
        
        logger.info(f"[{self.name}] SerialManager初期化: {port}@{baud_rate}bps")
    
    def initialize(self) -> bool:
        """
        シリアル接続を初期化
        
        Returns:
            bool: 初期化成功時True
        """
        try:
            logger.info(f"[{self.name}] ポート {self.port} を開こうとしています...")
            
            self.serial_connection = serial.Serial(
                self.port,
                self.baud_rate,
                timeout=self.timeout
            )
            self.is_initialized = True
            self._reset_statistics()
            
            logger.info(f"✓ [{self.name}] シリアル通信が正常に初期化されました: {self.port}")
            
            return True
        
        except Exception as e:
            logger.error(f"✗ [{self.name}] シリアル通信初期化エラー: {e}")
            self.is_initialized = False
            self._error_count += 1
            self._last_error_time = time.time()
            return False
    
    def _reset_statistics(self):
        """統計情報をリセット"""
        self._bytes_sent = 0
        self._bytes_received = 0
        self._error_count = 0
        self._last_error_time = 0
    
    def close(self):
        """シリアル接続を閉じる"""
        try:
            if self.serial_connection and self.serial_connection.is_open:
                logger.info(f"[{self.name}] シリアルポートを閉じ中...")
                logger.info(f"[{self.name}] 統計: 送信={self._bytes_sent}B, "
                          f"受信={self._bytes_received}B, エラー={self._error_count}回")
                self.serial_connection.close()
                self.is_initialized = False
        except Exception as e:
            logger.error(f"[{self.name}] シリアルポートクローズエラー: {e}")
    
    def is_connected(self) -> bool:
        """
        接続状態を確認
        
        Returns:
            bool: 接続中の場合True
        """
        return (self.is_initialized and 
                self.serial_connection is not None and 
                self.serial_connection.is_open)
    
    def reconnect(self) -> bool:
        """
        再接続を試行
        
        Returns:
            bool: 再接続成功時True
        """
        logger.info(f"[{self.name}] 再接続を試行中...")
        self.close()
        time.sleep(0.5)
        return self.initialize()
    
    def write(self, data: bytes) -> bool:
        """
        データを送信
        
        Args:
            data: 送信するバイト列
            
        Returns:
            bool: 送信成功時True
        """
        if not self.is_connected():
            logger.warning(f"[{self.name}] シリアル通信が初期化されていません")
            
            # 自動再接続を試行
            if self.auto_reconnect:
                if self.reconnect():
                    logger.info(f"[{self.name}] 自動再接続成功")
                else:
                    return False
            else:
                return False
        
        try:
            with self.lock:
                self.serial_connection.write(data)
                self._bytes_sent += len(data)
                
                if DEBUG_SERIAL_LOG:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    logger.debug(f"[{self.name}] 送信: {hex_str}")
            return True
            
        except Exception as e:
            logger.error(f"[{self.name}] 送信エラー: {e}")
            self._error_count += 1
            self._last_error_time = time.time()
            return False
    
    def read(self, size: int = 1) -> bytes:
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
                self._bytes_received += len(data)
                
                if data and DEBUG_SERIAL_LOG:
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    logger.debug(f"[{self.name}] 受信: {hex_str}")
                return data
                
        except Exception as e:
            logger.error(f"[{self.name}] 受信エラー: {e}")
            self._error_count += 1
            self._last_error_time = time.time()
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
                        logger.debug(f"[{self.name}] バッファクリア: {old_data.hex()} ({len(old_data)} bytes)")
        except Exception as e:
            logger.error(f"[{self.name}] バッファクリアエラー: {e}")
    
    def wait_for_response(self, expected_size: int, timeout: float = 1.0) -> Optional[bytes]:
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
        
        logger.warning(f"[{self.name}] 応答タイムアウト（期待: {expected_size}バイト）")
        return None
    
    def get_statistics(self) -> dict:
        """
        通信統計情報を取得
        
        Returns:
            dict: 統計情報
        """
        return {
            'name': self.name,
            'port': self.port,
            'baud_rate': self.baud_rate,
            'is_connected': self.is_connected(),
            'bytes_sent': self._bytes_sent,
            'bytes_received': self._bytes_received,
            'error_count': self._error_count,
            'last_error_time': self._last_error_time
        }
