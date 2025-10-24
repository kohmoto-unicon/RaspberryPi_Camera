#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
コマンド生成ユーティリティ
"""


def calc_checksum(data_bytes):
    """
    チェックサムを計算
    
    Args:
        data_bytes: コマンドバイト列
        
    Returns:
        int: チェックサム値
    """
    checksum = 0
    for b in data_bytes[1:9]:
        checksum ^= b
    return checksum


def build_pump_command(pump_no, action, value="000000"):
    """
    ポンプ制御コマンドを生成
    
    Args:
        pump_no: ポンプ番号（1-6）
        action: アクション文字（'M', 'S', 'X'等）
        value: 値（6桁の文字列）
        
    Returns:
        bytearray: 生成されたコマンドバイト列
    """
    value_str = value.zfill(6)
    cmd = bytearray(11)
    cmd[0] = 0x02  # STX
    cmd[1] = ord(str(pump_no))
    cmd[2] = ord(action)
    for i, c in enumerate(value_str):
        cmd[3 + i] = ord(c)
    cmd[9] = calc_checksum(cmd)
    cmd[10] = 0x03  # ETX
    return cmd


def format_command_bytes(bytes_data, pump_no):
    """
    コマンドバイトを16進数とASCII文字の混合形式でフォーマット
    
    Args:
        bytes_data: バイト列
        pump_no: ポンプ番号（1-6）
        
    Returns:
        str: フォーマットされた文字列
    """
    # ポンプ番号に応じてポート名を決定
    if 1 <= pump_no <= 3:
        port_name = 'ACM0'
    elif 4 <= pump_no <= 6:
        port_name = 'ACM1'
    else:
        port_name = 'UNKNOWN'
    
    result = [port_name + '→']
    for i in range(len(bytes_data)):
        if i == 0:
            # STX (0x02)
            result.append('STX')
        elif i == 10:
            # ETX (0x03)
            result.append('ETX')
        elif i == 9:
            # チェックサムは16進数で表示
            result.append('0x' + bytes_data[i].toString(16).upper().zfill(2))
        else:
            # その他はASCII文字で表示
            if 32 <= bytes_data[i] <= 126:
                result.append(chr(bytes_data[i]))
            else:
                result.append('0x' + hex(bytes_data[i])[2:].upper().zfill(2))
    
    return ' '.join(result)
