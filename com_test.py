from flask import Flask, request
import serial

SERIAL_PORT = "COM18"
BAUD_RATE = 9600
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

app = Flask(__name__)

def calc_checksum(data_bytes):
    checksum = 0
    for b in data_bytes[1:9]:
        checksum ^= b
    return checksum

def send_serial_command(pump_no, action, value="000000"):
    value_str = value.zfill(6)
    cmd = bytearray(11)
    cmd[0] = 0x02
    cmd[1] = ord(str(pump_no))
    cmd[2] = ord(action)
    for i, c in enumerate(value_str):
        cmd[3 + i] = ord(c)
    cmd[9] = calc_checksum(cmd)
    cmd[10] = 0x03
    ser.write(cmd)
    print(f"[Pump {pump_no}] 送信: {' '.join(f'{b:02X}' for b in cmd)}")

HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>ポンプ制御</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .pump-box { border: 1px solid #ccc; padding: 15px; margin: 10px; border-radius: 10px; width: 250px; display: inline-block; vertical-align: top; }
    h2 { margin: 0 0 10px; }
    .switch { position: relative; display: inline-block; width: 60px; height: 34px; }
    .switch input { display: none; }
    .slider {
      position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
      background-color: #ccc; transition: .4s; border-radius: 34px;
    }
    .slider:before {
      position: absolute; content: ""; height: 26px; width: 26px;
      left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%;
    }
    input:checked + .slider { background-color: #2196F3; }
    input:checked + .slider:before { transform: translateX(26px); }
    button { padding: 5px 10px; margin: 5px; }
  </style>
</head>
<body>
  <h1>ポンプ制御ページ</h1>
  {% for pump in range(1,7) %}
  <div class="pump-box">
    <h2>ポンプ{{ pump }}</h2>
    <p>正逆切替:
      <label class="switch">
        <input type="checkbox" onchange="toggleDirection({{ pump }}, this.checked)">
        <span class="slider"></span>
      </label>
      <span id="dirLabel{{ pump }}">正転</span>
    </p>
    <p>
      ステップ数: <input type="number" id="steps{{ pump }}" value="000000" min="0" max="999999">
    </p>
    <p>
      <button onclick="sendSteps({{ pump }})">送信</button>
      <button onclick="sendStop({{ pump }})" style="background-color:red;color:white;">停止</button>
    </p>
  </div>
  {% endfor %}
  <script>
    function toggleDirection(pump, isReverse){
      const dir = isReverse ? 'R' : 'F';
      document.getElementById('dirLabel' + pump).innerText = isReverse ? '逆転' : '正転';
      fetch(`/control?pump=${pump}&action=${dir}`);
    }
    function sendSteps(pump){
      const steps = document.getElementById('steps' + pump).value;
      fetch(`/control?pump=${pump}&action=M&value=${steps}`);
    }
    function sendStop(pump){
      fetch(`/control?pump=${pump}&action=S`);
    }
  </script>
</body>
</html>
"""

from flask import render_template_string

@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/control")
def control():
    pump = request.args.get("pump", "1")
    action = request.args.get("action", "M")
    value = request.args.get("value", "000000")
    send_serial_command(pump, action, value)
    return f"送信完了: pump={pump}, action={action}, value={value}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
