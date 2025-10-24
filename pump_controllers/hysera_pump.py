#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハイセラポンプ制御クラス
"""

import serial  # pyserial
import threading
from .serial_manager import SerialManager
from utils.command_builder import build_pump_command
from utils.response_parser import parse_pump_response, verify_checksum
from config import (
    SERIAL_PORT_1, SERIAL_PORT_2, BAUD_RATE,
    DEBUG_SERIAL_LOG, DEBUG_LEAK_LOG
)


class HyseraPumpController:
    """ハイセラポンプ制御クラス"""
    
    def __init__(self):
        """初期化"""
        # ポンプ1-3用のシリアルマネージャー
        self.serial_port1 = SerialManager(
            SERIAL_PORT_1,
            BAUD_RATE,
            name="HyseraPump1-3"
        )
        
        # ポンプ4-6用のシリアルマネージャー
        self.serial_port2 = SerialManager(
            SERIAL_PORT_2,
            BAUD_RATE,
            name="HyseraPump4-6"
        )
        
        # 漏液検出状態
        self.leak_detected = False
        self.leak_detection_lock = threading.Lock()
    
    def initialize(self):
        """シリアル通信を初期化"""
        port1_success = self.serial_port1.initialize()
        port2_success = self.serial_port2.initialize()
        
        return port1_success or port2_success
    
    def close(self):
        """シリアル接続を閉じる"""
        self.serial_port1.close()
        self.serial_port2.close()
    
    def _get_serial_port(self, pump_no):
        """
        ポンプ番号に応じたシリアルポートを取得
        
        Args:
            pump_no: ポンプ番号（1-6）
            
        Returns:
            tuple: (SerialManager, コマンド用ポンプ番号)
        """
        if 1 <= pump_no <= 3:
            return self.serial_port1, pump_no
        elif 4 <= pump_no <= 6:
            return self.serial_port2, pump_no - 3
        else:
            raise ValueError(f"無効なポンプ番号: {pump_no}")
    
    def send_command(self, pump_no, action, value="000000"):
        """
        ポンプにコマンドを送信
        
        Args:
            pump_no: ポンプ番号（1-6）
            action: アクション文字
            value: 値（6桁の文字列）
            
        Returns:
            tuple: (success, command_bytes, response_bytes)
        """
        try:
            serial_port, command_pump_no = self._get_serial_port(pump_no)
            
            if not serial_port.is_connected():
                return False, None, None
            
            # コマンド生成
            cmd = build_pump_command(command_pump_no, action, value)
            
            # バッファクリア
            serial_port.clear_buffer()
            
            # コマンド送信
            success = serial_port.write(cmd)
            
            return success, cmd, None
        
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"コマンド送信エラー: {e}")
            return False, None, None
    
    def send_command_with_response(self, pump_no, action, value="000000", 
                                   response_type='generic', timeout=1.0):
        """
        コマンドを送信してレスポンスを待機
        
        Args:
            pump_no: ポンプ番号（1-6）
            action: アクション文字
            value: 値（6桁の文字列）
            response_type: レスポンスタイプ
            timeout: タイムアウト（秒）
            
        Returns:
            dict: 解析されたレスポンス
        """
        try:
            serial_port, command_pump_no = self._get_serial_port(pump_no)
            
            if not serial_port.is_connected():
                return {
                    'success': False,
                    'message': 'シリアル通信が初期化されていません'
                }
            
            # コマンド生成
            cmd = build_pump_command(command_pump_no, action, value)
            
            # バッファクリア
            serial_port.clear_buffer()
            
            # コマンド送信
            if not serial_port.write(cmd):
                return {
                    'success': False,
                    'message': 'コマンド送信失敗',
                    'command_bytes': list(cmd)
                }
            
            # レスポンス待機
            response = serial_port.wait_for_response(10, timeout)
            
            if response is None:
                return {
                    'success': False,
                    'message': '応答タイムアウト',
                    'command_bytes': list(cmd)
                }
            
            # レスポンス解析
            result = parse_pump_response(response, response_type)
            result['command_bytes'] = list(cmd)
            
            return result
        
        except Exception as e:
            if DEBUG_SERIAL_LOG:
                print(f"コマンド送信・受信エラー: {e}")
            return {
                'success': False,
                'message': f'エラー: {str(e)}'
            }
    
    def check_leak_detection(self):
        """
        漏液検出コマンドをチェック
        
        Returns:
            bool: 漏液検出時True
        """
        leak_found = False
        
        # ポート1のチェック
        if self.serial_port1.is_connected():
            serial_conn = self.serial_port1.serial_connection
            if serial_conn.in_waiting >= 10:
                data = serial_conn.read(10)
                if DEBUG_LEAK_LOG:
                    print(f"[LEAK CHECK] ポート1 受信データ: {data.hex()} ({len(data)} bytes)")
                
                # 漏液検出コマンドのチェック
                if (len(data) >= 10 and data[0] == 0x02 and 
                    data[2] == ord('Z') and data[9] == 0x03):
                    if verify_checksum(data):
                        if DEBUG_LEAK_LOG:
                            print(f"[LEAK CHECK] 漏液検出コマンドを受信")
                        with self.leak_detection_lock:
                            self.leak_detected = True
                        leak_found = True
        
        # ポート2のチェック
        if self.serial_port2.is_connected():
            serial_conn = self.serial_port2.serial_connection
            if serial_conn.in_waiting >= 10:
                data = serial_conn.read(10)
                if DEBUG_LEAK_LOG:
                    print(f"[LEAK CHECK] ポート2 受信データ: {data.hex()} ({len(data)} bytes)")
                
                # 漏液検出コマンドのチェック
                if (len(data) >= 10 and data[0] == 0x02 and 
                    data[2] == ord('Z') and data[9] == 0x03):
                    if verify_checksum(data):
                        if DEBUG_LEAK_LOG:
                            print(f"[LEAK CHECK] 漏液検出コマンドを受信")
                        with self.leak_detection_lock:
                            self.leak_detected = True
                        leak_found = True
        
        return leak_found
    
    def reset_leak_detection(self):
        """漏液検出状態をリセット"""
        with self.leak_detection_lock:
            self.leak_detected = False
            if DEBUG_LEAK_LOG:
                print("漏液検出状態をリセットしました")
    
    def get_leak_status(self):
        """現在の漏液検出状態を取得"""
        with self.leak_detection_lock:
            return self.leak_detected
    
    def is_port1_connected(self):
        """ポート1の接続状態"""
        return self.serial_port1.is_connected()
    
    def is_port2_connected(self):
        """ポート2の接続状態"""
        return self.serial_port2.is_connected()
