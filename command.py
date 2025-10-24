#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レガシーシリンジポンプコントローラー

このモジュールは後方互換性のために保持されています。
新しいコードではpump_controllers.SyringePumpManagerを使用してください。
"""

import serial
import time
import logging
from typing import Tuple

# ロガー設定
logger = logging.getLogger(__name__)

class SyringePumpController:
    """
    シリンジポンプコントローラー（レガシー版）
    
    単一のシリンジポンプを制御します。
    pump_controllers.SyringePumpManagerから使用されます。
    
    Attributes:
        pump_number: ポンプ番号
        serial_port: シリアルポートインスタンス
        address: ポンプアドレス
        status: ポンプ状態
    """
    
    def __init__(self, pump_number: int, serial_port: serial.Serial):
        """
        初期化
        
        Args:
            pump_number: ポンプ番号
            serial_port: シリアルポートインスタンス
        """
        self.pump_number = pump_number
        self.serial_port = serial_port
        self.address = 1  # プレースホルダー、pump_numberから派生するか渡す必要があります
        self.status = "Stop"
        
        logger.debug(f"SyringePumpController[{pump_number}]初期化")
    
    @staticmethod
    def _format_hex(data: bytes) -> str:
        """
        バイトデータを16進数文字列に変換
        
        Args:
            data: バイトデータ
            
        Returns:
            str: 空白区切りの16進数文字列
        """
        return ' '.join(f'{b:02x}' for b in data)
        
    def create_command(self, command: str, address: int) -> bytes:
        """
        コマンドフレームを作成（チェックサム付き）
        
        フレーム形式:
        STX(0x02) + [ADDR ASCII] + [0x31] + [COMMAND ASCII] + ETX(0x03) + [CS(1byte XOR)]
        
        Args:
            command: コマンド文字列
            address: ポンプアドレス
            
        Returns:
            bytes: コマンドフレーム
        """
        # アドレスは1文字のASCII、その後に0x31、そしてコマンド文字列
        body_bytes = bytes([ord(str(address))]) + bytes([0x31]) + command.encode('ascii')
        frame_without_cs = bytes([0x02]) + body_bytes + bytes([0x03])
        
        # STXからETXまで含めた全バイトのXORチェックサム
        checksum = 0
        for byte in frame_without_cs:
            checksum ^= byte
        
        frame = frame_without_cs + bytes([checksum])
        return frame
    
    def send_command(self, command: str, address: int) -> Tuple[bool, bytes, bytes]:
        """
        コマンドを送信し、応答を受信
        
        Args:
            command: コマンド文字列
            address: ポンプアドレス
            
        Returns:
            tuple: (成功フラグ, 送信コマンド, 受信レスポンス)
        """
        try:
            full_command = self.create_command(command, address)
            self.serial_port.write(full_command)
            logger.debug(f"[Pump {self.pump_number}] 送信: {self._format_hex(full_command)}")
            
            # 応答を受信（タイムアウト付き）
            self.serial_port.timeout = 1.0  # 1秒のタイムアウト
            response = self._read_response()
            
            if response:
                logger.debug(f"[Pump {self.pump_number}] 受信: {self._format_hex(response)}")
                return True, full_command, response
            else:
                logger.warning(f"[Pump {self.pump_number}] 応答なし")
                return True, full_command, b''
                
        except Exception as e:
            logger.error(f"[Pump {self.pump_number}] シリンジポンプ送信エラー: {e}")
            # 失敗時もコマンドバイトは返す
            full_command = self.create_command(command, address)
            return False, full_command, b''
    
    def _read_response(self) -> bytes:
        """
        応答を受信し、0x02(STX)から始まるコマンドを抽出
        0x02の前の0xFFゴミデータは無視する
        フォーマット: STX(0x02) + [DATA] + ETX(0x03) + [CHECKSUM]
        """
        buffer = bytearray()
        start_time = time.time()
        stx_found = False
        
        # STX(0x02)を探す（0xFFは無視）
        while (time.time() - start_time) < 1.0:  # 1秒タイムアウト
            byte = self.serial_port.read(1)
            if not byte:
                continue
                
            byte_val = byte[0]
            
            if not stx_found:
                # STXを探す（0xFFは無視）
                if byte_val == 0x02:
                    stx_found = True
                    buffer.append(byte_val)
                elif byte_val == 0xFF:
                    # 0xFFは無視して次のバイトへ
                    continue
                else:
                    # 予期しないバイトも無視
                    continue
            else:
                # STX以降のデータを収集
                buffer.append(byte_val)
                
                # ETX(0x03)を検出したら、その後のチェックサムを読んで終了
                if byte_val == 0x03:
                    # チェックサムを1バイト読む
                    checksum_byte = self.serial_port.read(1)
                    if checksum_byte:
                        buffer.append(checksum_byte[0])
                    break
        
        return bytes(buffer)
