#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
レスポンス解析ユーティリティ
"""


def decode_rpm_from_status_byte(encoded_value):
    """
    Jコマンド応答の回転速度バイト値をRPMに変換
    
    値が0,1,2,3,4の場合: RPM = 値 * 10 (0, 10, 20, 30, 40)
    値が5以上の場合: RPM = 値 + 45
    
    例:
      0 → 0 rpm
      1 → 10 rpm
      2 → 20 rpm
      3 → 30 rpm
      4 → 40 rpm
      5 → 50 rpm (5 + 45)
      6 → 51 rpm (6 + 45)
      ...
      255 → 300 rpm (255 + 45)
    
    Args:
        encoded_value: エンコードされた値
        
    Returns:
        int: RPM値
    """
    try:
        value = int(encoded_value)
        if value <= 4:
            return value * 10
        else:
            return value + 45
    except (ValueError, TypeError):
        return 0


def verify_checksum(response):
    """
    レスポンスのチェックサムを検証
    
    Args:
        response: レスポンスバイト列（10バイト）
        
    Returns:
        bool: チェックサムが正しい場合True
    """
    if len(response) != 10:
        return False
    
    checksum = 0
    for i in range(1, 8):
        checksum ^= response[i]
    
    return checksum == response[8]


def parse_pump_response(response, response_type='generic'):
    """
    ポンプからのレスポンスを解析
    
    Args:
        response: レスポンスバイト列
        response_type: レスポンスタイプ ('rpm', 'current', 'total_revolutions', 'status', 'generic')
        
    Returns:
        dict: 解析結果
    """
    if not response or len(response) != 10:
        return {
            'success': False,
            'error': 'Invalid response length'
        }
    
    # STX/ETXチェック
    if response[0] != 0x02 or response[9] != 0x03:
        return {
            'success': False,
            'error': f'Invalid frame: STX={response[0]:02X}, ETX={response[9]:02X}'
        }
    
    # チェックサム検証
    if not verify_checksum(response):
        checksum = 0
        for i in range(1, 8):
            checksum ^= response[i]
        return {
            'success': False,
            'error': f'Checksum mismatch: expected={checksum:02X}, received={response[8]:02X}'
        }
    
    # レスポンスタイプに応じて解析
    if response_type == 'rpm':
        rpm_str = response[2:8].decode('ascii', errors='ignore')
        try:
            rpm = int(rpm_str)
            return {
                'success': True,
                'rpm': rpm,
                'message': f'回転数取得完了: {rpm}rpm'
            }
        except ValueError:
            return {
                'success': False,
                'error': f'Failed to parse RPM: {rpm_str}'
            }
    
    elif response_type == 'current':
        current_str = response[2:8].decode('ascii', errors='ignore')
        try:
            current = int(current_str)
            return {
                'success': True,
                'current': current,
                'message': f'電流値取得完了: {current}mA'
            }
        except ValueError:
            return {
                'success': False,
                'error': f'Failed to parse current: {current_str}'
            }
    
    elif response_type == 'total_revolutions':
        hex_str = response[2:8].decode('ascii', errors='ignore')
        try:
            total_revolutions = int(hex_str, 16)
            return {
                'success': True,
                'total_revolutions': total_revolutions,
                'hex_value': hex_str,
                'message': f'トータル回転数取得成功: {total_revolutions} 回転'
            }
        except ValueError:
            return {
                'success': False,
                'error': f'Failed to parse total revolutions: {hex_str}'
            }
    
    elif response_type == 'status':
        try:
            valve_bits = int(chr(response[2]))
            excitation_bits = int(chr(response[3]))
            trapezoid_bits = int(chr(response[4]))
            
            valve_status = [(valve_bits & (1 << i)) != 0 for i in range(3)]
            excitation_status = [(excitation_bits & (1 << i)) != 0 for i in range(3)]
            trapezoid_status = [(trapezoid_bits & (1 << i)) != 0 for i in range(3)]
            
            return {
                'success': True,
                'valve': valve_status,
                'excitation': excitation_status,
                'trapezoid': trapezoid_status,
                'valve_bits': valve_bits,
                'excitation_bits': excitation_bits,
                'trapezoid_bits': trapezoid_bits,
                'message': '制御状態取得完了'
            }
        except (ValueError, IndexError) as e:
            return {
                'success': False,
                'error': f'Failed to parse status: {str(e)}'
            }
    
    elif response_type == 'leak_status':
        try:
            leak_detected = (response[2] & 0x01) != 0
            rpm_pump1 = decode_rpm_from_status_byte(response[3])
            rpm_pump2 = decode_rpm_from_status_byte(response[4])
            rpm_pump3 = decode_rpm_from_status_byte(response[5])
            
            return {
                'success': True,
                'leak_detected': leak_detected,
                'rpm_pump1': rpm_pump1,
                'rpm_pump2': rpm_pump2,
                'rpm_pump3': rpm_pump3,
                'message': '状態確認完了 - ' + ('漏液検出' if leak_detected else '正常')
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to parse leak status: {str(e)}'
            }
    
    # デフォルト（genericレスポンス）
    return {
        'success': True,
        'raw_data': list(response),
        'message': 'Response received'
    }
