import serial
import time

class SyringePumpController:
    def __init__(self, pump_number: int, serial_port: serial.Serial):
        self.pump_number = pump_number
        self.serial_port = serial_port
        self.address = 1  # プレースホルダー、pump_numberから派生するか渡す必要があります
        self.status = "Stop"
        
    def create_command(self, command: str, address: int) -> bytes:
        """コマンドフレームを作成（チェックサム付き）"""
        # Frame: STX(0x02) + [ADDR ASCII] + [0x31] + [COMMAND ASCII] + ETX(0x03) + [CS(1byte XOR)]
        # アドレスは1文字のASCII、その後に0x31、そしてコマンド文字列
        body_bytes = bytes([ord(str(address))]) + bytes([0x31]) + command.encode('ascii')
        frame_without_cs = bytes([0x02]) + body_bytes + bytes([0x03])
        # STXからETXまで含めた全バイトのXORチェックサム
        checksum = 0
        for byte in frame_without_cs:
            checksum ^= byte
        frame = frame_without_cs + bytes([checksum])
        return frame
    
    def send_command(self, command: str, address: int) -> tuple[bool, bytes]:
        """コマンドを送信"""
        try:
            full_command = self.create_command(command, address)
            self.serial_port.write(full_command)
            print(f"[Pump {self.pump_number}] 送信: {full_command.hex()}")
            return True, full_command
        except Exception as e:
            print(f"シリンジポンプ送信エラー: {e}")
            # Always return the command bytes even if serial communication fails
            full_command = self.create_command(command, address)
            return False, full_command
