#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ハイセラポンプ制御クラス

このクラスは6台のハイセラポンプを2つのシリアルポート経由で制御します。
各ポートは3台のポンプを管理し、漏液検出機能もサポートします。

主な機能:
- 6台のポンプ制御（2ポート × 3台）
- コマンド送受信とレスポンス解析
- 漏液検出監視
- エラーハンドリングとリトライ
- 詳細なログ出力
"""

import serial  # pyserial
import threading
import time
import logging
from typing import Optional, Dict, Tuple
from .serial_manager import SerialManager
from utils.command_builder import build_pump_command
from utils.response_parser import parse_pump_response, verify_checksum
from config import (
    SERIAL_PORT_1, SERIAL_PORT_2, BAUD_RATE,
    DEBUG_SERIAL_LOG, DEBUG_LEAK_LOG
)

# ロガー設定
logger = logging.getLogger(__name__)
if DEBUG_SERIAL_LOG:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


class HyseraPumpController:
    """
    ハイセラポンプ制御クラス
    
    6台のハイセラポンプを2つのシリアルポート経由で制御します。
    - ポート1: ポンプ1-3
    - ポート2: ポンプ4-6
    
    Attributes:
        serial_port1: ポンプ1-3用のシリアルマネージャー
        serial_port2: ポンプ4-6用のシリアルマネージャー
        leak_detected: 漏液検出状態
        leak_detection_lock: 漏液検出用のスレッドロック
    """
    
    def __init__(self, max_retries: int = 3):
        """
        初期化
        
        Args:
            max_retries: コマンド送信の最大リトライ回数
        """
        # ポンプ1-3用のシリアルマネージャー
        self.serial_port1 = SerialManager(
            SERIAL_PORT_1,
            BAUD_RATE,
            name="HyseraPump1-3",
            auto_reconnect=True
        )
        
        # ポンプ4-6用のシリアルマネージャー
        self.serial_port2 = SerialManager(
            SERIAL_PORT_2,
            BAUD_RATE,
            name="HyseraPump4-6",
            auto_reconnect=True
        )
        
        # 漏液検出状態
        self.leak_detected = False
        self.leak_detection_lock = threading.Lock()
        
        # リトライ設定
        self.max_retries = max_retries
        
        # ポンプ状態管理
        self._pump_status = {i: {'running': False, 'rpm': 0, 'last_command': None} 
                            for i in range(1, 7)}
        self._status_lock = threading.Lock()
        
        logger.info(f"HyseraPumpController初期化: max_retries={max_retries}")
    
    def initialize(self) -> bool:
        """
        シリアル通信を初期化
        
        Returns:
            bool: 少なくとも1つのポートが初期化成功した場合True
        """
        logger.info("ハイセラポンプの初期化を開始...")
        
        port1_success = self.serial_port1.initialize()
        port2_success = self.serial_port2.initialize()
        
        if port1_success and port2_success:
            logger.info("✓ 両ポートの初期化成功")
        elif port1_success:
            logger.warning("ポート1のみ初期化成功（ポンプ1-3のみ使用可能）")
        elif port2_success:
            logger.warning("ポート2のみ初期化成功（ポンプ4-6のみ使用可能）")
        else:
            logger.error("✗ 全ポートの初期化失敗")
        
        return port1_success or port2_success
    
    def close(self):
        """シリアル接続を閉じる"""
        self.serial_port1.close()
        self.serial_port2.close()
    
    def _get_serial_port(self, pump_no: int) -> Tuple[SerialManager, int]:
        """
        ポンプ番号に応じたシリアルポートを取得
        
        Args:
            pump_no: ポンプ番号（1-6）
            
        Returns:
            tuple: (SerialManager, コマンド用ポンプ番号)
            
        Raises:
            ValueError: ポンプ番号が範囲外の場合
        """
        if 1 <= pump_no <= 3:
            return self.serial_port1, pump_no
        elif 4 <= pump_no <= 6:
            return self.serial_port2, pump_no - 3
        else:
            raise ValueError(f"無効なポンプ番号: {pump_no}（1-6の範囲で指定してください）")
    
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
    
    def send_command_with_response(self, pump_no: int, action: str, value: str = "000000", 
                                   response_type: str = 'generic', timeout: float = 1.0,
                                   retry: bool = True) -> Dict:
        """
        コマンドを送信してレスポンスを待機（リトライ機能付き）
        
        Args:
            pump_no: ポンプ番号（1-6）
            action: アクション文字
            value: 値（6桁の文字列）
            response_type: レスポンスタイプ
            timeout: タイムアウト（秒）
            retry: リトライを有効にするか
            
        Returns:
            dict: 解析されたレスポンス
        """
        # リトライロジック
        attempts = self.max_retries if retry else 1
        
        for attempt in range(attempts):
            try:
                serial_port, command_pump_no = self._get_serial_port(pump_no)
                
                if not serial_port.is_connected():
                    if attempt < attempts - 1:
                        logger.warning(f"[ポンプ{pump_no}] 接続なし、リトライ {attempt + 1}/{attempts}")
                        time.sleep(0.5)
                        continue
                    return {
                        'success': False,
                        'message': 'シリアル通信が初期化されていません',
                        'pump_no': pump_no
                    }
                
                # コマンド生成
                cmd = build_pump_command(command_pump_no, action, value)
                
                # バッファクリア
                serial_port.clear_buffer()
                
                # コマンド送信
                if not serial_port.write(cmd):
                    if attempt < attempts - 1:
                        logger.warning(f"[ポンプ{pump_no}] 送信失敗、リトライ {attempt + 1}/{attempts}")
                        time.sleep(0.2)
                        continue
                    return {
                        'success': False,
                        'message': 'コマンド送信失敗',
                        'command_bytes': list(cmd),
                        'pump_no': pump_no
                    }
                
                # レスポンス待機
                response = serial_port.wait_for_response(10, timeout)
                
                if response is None:
                    if attempt < attempts - 1:
                        logger.warning(f"[ポンプ{pump_no}] 応答タイムアウト、リトライ {attempt + 1}/{attempts}")
                        time.sleep(0.2)
                        continue
                    return {
                        'success': False,
                        'message': '応答タイムアウト',
                        'command_bytes': list(cmd),
                        'pump_no': pump_no
                    }
                
                # レスポンス解析
                result = parse_pump_response(response, response_type)
                result['command_bytes'] = list(cmd)
                result['pump_no'] = pump_no
                result['attempts'] = attempt + 1
                
                # 成功時はポンプ状態を更新
                if result.get('success'):
                    self._update_pump_status(pump_no, action, value, result)
                
                return result
            
            except Exception as e:
                logger.error(f"[ポンプ{pump_no}] コマンド送信・受信エラー: {e}")
                if attempt < attempts - 1:
                    logger.warning(f"[ポンプ{pump_no}] 例外発生、リトライ {attempt + 1}/{attempts}")
                    time.sleep(0.2)
                    continue
                return {
                    'success': False,
                    'message': f'エラー: {str(e)}',
                    'pump_no': pump_no
                }
        
        return {
            'success': False,
            'message': f'最大リトライ回数（{attempts}回）に達しました',
            'pump_no': pump_no
        }
    
    def _update_pump_status(self, pump_no: int, action: str, value: str, result: Dict):
        """
        ポンプ状態を更新
        
        Args:
            pump_no: ポンプ番号
            action: アクション文字
            value: コマンド値
            result: レスポンス結果
        """
        with self._status_lock:
            if action in ['S', 'G']:  # 起動コマンド
                self._pump_status[pump_no]['running'] = True
                self._pump_status[pump_no]['last_command'] = action
                if 'rpm' in result:
                    self._pump_status[pump_no]['rpm'] = result['rpm']
            elif action == 'T':  # 停止コマンド
                self._pump_status[pump_no]['running'] = False
                self._pump_status[pump_no]['rpm'] = 0
                self._pump_status[pump_no]['last_command'] = action
    
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
    
    def is_port1_connected(self) -> bool:
        """ポート1の接続状態"""
        return self.serial_port1.is_connected()
    
    def is_port2_connected(self) -> bool:
        """ポート2の接続状態"""
        return self.serial_port2.is_connected()
    
    def get_pump_status(self, pump_no: int) -> Optional[Dict]:
        """
        指定ポンプの状態を取得
        
        Args:
            pump_no: ポンプ番号（1-6）
            
        Returns:
            dict: ポンプ状態、無効な番号の場合None
        """
        if 1 <= pump_no <= 6:
            with self._status_lock:
                return self._pump_status[pump_no].copy()
        return None
    
    def get_all_pump_status(self) -> Dict[int, Dict]:
        """
        全ポンプの状態を取得
        
        Returns:
            dict: 全ポンプの状態
        """
        with self._status_lock:
            return {k: v.copy() for k, v in self._pump_status.items()}
    
    def get_statistics(self) -> Dict:
        """
        制御統計情報を取得
        
        Returns:
            dict: 統計情報
        """
        return {
            'port1': self.serial_port1.get_statistics(),
            'port2': self.serial_port2.get_statistics(),
            'leak_detected': self.leak_detected,
            'pump_status': self.get_all_pump_status()
        }
