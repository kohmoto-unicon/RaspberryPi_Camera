# クイックリファレンス

## 🚀 よく使うコマンド一覧

### サービス管理（推奨：短縮コマンド）

```bash
app start      # サービスを起動
app stop       # サービスを停止
app restart    # サービスを再起動（コード変更後など）
app status     # 状態を確認
app log        # リアルタイムログを表示（Ctrl+Cで終了）
app enable     # 自動起動を有効化
app disable    # 自動起動を無効化
```

### サービス管理（従来の方法）

```bash
sudo systemctl start raspi-camera-streaming.service
sudo systemctl stop raspi-camera-streaming.service
sudo systemctl restart raspi-camera-streaming.service
sudo systemctl status raspi-camera-streaming.service
sudo systemctl enable raspi-camera-streaming.service
sudo systemctl disable raspi-camera-streaming.service
```

### ログ確認

```bash
app log                                                    # リアルタイムログ
sudo journalctl -u raspi-camera-streaming.service -n 50   # 最新50行
sudo journalctl -u raspi-camera-streaming.service --since today  # 今日のログ
```

### 手動実行（デバッグ用）

```bash
cd /home/kohmoto/projects/RaspberryPi_Camera
source venv/bin/activate
python app.py --debug
```

### Webアクセス

```
http://localhost:5000              # メインページ
http://localhost:5000/pump_control # ポンプ制御
http://localhost:5000/syringe_pump # シリンジポンプ
```

### トラブルシューティング

```bash
# カメラ確認
vcgencmd get_camera
ls -la /dev/video*

# シリアルポート確認
ls -la /dev/ttyACM*
ls -la /dev/ttyUSB*

# ポート使用状況確認
sudo lsof -i :5000

# IPアドレス確認
hostname -I
```

---

📘 詳細は [SERVICE_GUIDE.md](SERVICE_GUIDE.md) をご覧ください

