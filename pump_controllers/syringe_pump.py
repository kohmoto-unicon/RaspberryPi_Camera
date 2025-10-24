#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリンジポンプ制御ラッパー
"""

import serial
from .serial_manager import SerialManager
from command import SyringePumpController as OriginalSyringePumpController
from config import SYRINGE_SERIAL_PORT, SYRINGE_BAUD_RATE, DEBUG_SERIAL_LOG


class SyringePumpManager:
    """シリンジポンプ管理クラス"""
    
    def __init__(self):
        """初期化"""
        self.serial_port = SerialManager(
            SYRINGE_SERIAL_PORT,
            SYRINGE_BAUD_RATE,
            name="SyringePump"
        )
        self.pump_controllers = []
    
    def initialize(self):
        """シリアル通信を初期化"""
        if not self.serial_port.initialize():
            return False
        
        # 6個のポンプ制御インスタンスを作成
        self.pump_controllers.clear()
        for i in range(1, 7):
            controller = OriginalSyringePumpController(
                i, 
                self.serial_port.serial_connection
            )
            self.pump_controllers.append(controller)
        
        if DEBUG_SERIAL_LOG:
            print(f"✓ 6個のシリンジポンプ制御インスタンスを作成しました")
        
        return True
    
    def close(self):
        """シリアル接続を閉じる"""
        self.pump_controllers.clear()
        self.serial_port.close()
    
    def get_controller(self, pump_index):
        """
        指定したポンプのコントローラーを取得
        
        Args:
            pump_index: ポンプインデックス（0-5）
            
        Returns:
            SyringePumpController: コントローラー、範囲外の場合None
        """
        if 0 <= pump_index < len(self.pump_controllers):
            return self.pump_controllers[pump_index]
        return None
    
    def is_connected(self):
        """接続状態を確認"""
        return self.serial_port.is_connected()
