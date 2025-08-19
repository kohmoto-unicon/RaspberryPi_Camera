import serial

# COMポートのチェック
print("COMテスト")
try:
    ser = serial.Serial("COM18", 9600, timeout=1)
    print("COM18オープン成功")
    ser.close()
except Exception as e:
    print(f"COM18オープン失敗: {e}")
