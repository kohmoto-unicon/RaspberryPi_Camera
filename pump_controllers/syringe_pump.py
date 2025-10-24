#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
シリンジポンプ制御ラッパー

このクラスは6台のシリンジポンプを1つのシリアルポート経由で制御します。
既存のSyringePumpControllerクラスをラップし、SerialManagerと統合します。

主な機能:
- 6台のシリンジポンプ制御
- 既存コントローラーとの互換性維持
- エラーハンドリング
- 統計情報管理
"""

import serial  # pyserial
import logging
from typing import Optional, Dict, List
from .serial_manager import SerialManager
from command import SyringePumpController as OriginalSyringePumpController
from config import SYRINGE_SERIAL_PORT, SYRINGE_BAUD_RATE, DEBUG_SERIAL_LOG

# ロガー設定
logger = logging.getLogger(__name__)
if DEBUG_SERIAL_LOG:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)


class SyringePumpManager:
    """
    シリンジポンプ管理クラス
    
    6台のシリンジポンプを管理し、既存のSyringePumpControllerを
    SerialManagerと統合します。
    
    Attributes:
        serial_port: シリアルマネージャー
        pump_controllers: 各ポンプのコントローラーリスト
    """
    
    def __init__(self):
        """初期化"""
        self.serial_port = SerialManager(
            SYRINGE_SERIAL_PORT,
            SYRINGE_BAUD_RATE,
            name="SyringePump",
            auto_reconnect=True
        )
        self.pump_controllers: List[OriginalSyringePumpController] = []
        
        logger.info("SyringePumpManager初期化")
    
    def initialize(self) -> bool:
        """
        シリアル通信を初期化
        
        Returns:
            bool: 初期化成功時True
        """
        logger.info("シリンジポンプの初期化を開始...")
        
        if not self.serial_port.initialize():
            logger.error("✗ シリアルポート初期化失敗")
            return False
        
        # 6個のポンプ制御インスタンスを作成
        self.pump_controllers.clear()
        for i in range(1, 7):
            try:
                controller = OriginalSyringePumpController(
                    i, 
                    self.serial_port.serial_connection
                )
                self.pump_controllers.append(controller)
            except Exception as e:
                logger.error(f"ポンプ{i}のコントローラー作成エラー: {e}")
                return False
        
        logger.info(f"✓ 6個のシリンジポンプ制御インスタンスを作成しました")
        
        return True
    
    def close(self):
        """シリアル接続を閉じる"""
        logger.info("シリンジポンプをクローズ中...")
        self.pump_controllers.clear()
        self.serial_port.close()
    
    def get_controller(self, pump_index: int) -> Optional[OriginalSyringePumpController]:
        """
        指定したポンプのコントローラーを取得
        
        Args:
            pump_index: ポンプインデックス（0-5）
            
        Returns:
            SyringePumpController: コントローラー、範囲外の場合None
        """
        if 0 <= pump_index < len(self.pump_controllers):
            return self.pump_controllers[pump_index]
        logger.warning(f"無効なポンプインデックス: {pump_index}（0-5の範囲で指定してください）")
        return None
    
    def get_controller_by_number(self, pump_number: int) -> Optional[OriginalSyringePumpController]:
        """
        ポンプ番号でコントローラーを取得（1-6）
        
        Args:
            pump_number: ポンプ番号（1-6）
            
        Returns:
            SyringePumpController: コントローラー、範囲外の場合None
        """
        if 1 <= pump_number <= 6:
            return self.pump_controllers[pump_number - 1]
        logger.warning(f"無効なポンプ番号: {pump_number}（1-6の範囲で指定してください）")
        return None
    
    def is_connected(self) -> bool:
        """接続状態を確認"""
        return self.serial_port.is_connected()
    
    def get_all_controllers(self) -> List[OriginalSyringePumpController]:
        """
        全コントローラーを取得
        
        Returns:
            list: コントローラーリスト
        """
        return self.pump_controllers.copy()
    
    def get_statistics(self) -> Dict:
        """
        統計情報を取得
        
        Returns:
            dict: 統計情報
        """
        return {
            'serial_port': self.serial_port.get_statistics(),
            'controller_count': len(self.pump_controllers),
            'is_connected': self.is_connected()
        }
