# Arduinoのシリアルポート固定化手順 (udev設定)

Raspberry PiなどのLinux環境では、USBデバイスの認識順序によって `/dev/ttyACM0` と `/dev/ttyACM1` が入れ替わることがあります。
これを防ぐため、各Arduinoのシリアル番号に基づいて、常に固定のデバイス名（シンボリックリンク）を作成する設定を行います。

## 目標
- ポンプ1-3用のArduino → `/dev/ttyHysera1` としてアクセス可能にする
- ポンプ4-6用のArduino → `/dev/ttyHysera2` としてアクセス可能にする

## 手順

### 1. 各Arduinoのシリアル番号を確認する

まず、Arduinoを**1台ずつ**接続して、それぞれのシリアル番号（ID）を確認します。

1. **全てのArduinoを外します。**
2. **ポンプ1-3用**のArduinoだけを接続します。
3. 以下のコマンドを実行します。
   ```bash
   ls -l /dev/serial/by-id/
   ```
   表示される `usb-Arduino_...` の部分がIDです。
   例: `usb-Arduino_Mega_2560_85430353037351301141-if00`
   この中の `85430353037351301141` の部分（シリアル番号）をメモしてください。これが **ID1** です。

4. ポンプ1-3用を外し、**ポンプ4-6用**のArduinoだけを接続します。
5. 同様にコマンドを実行し、IDを確認します。
   ```bash
   ls -l /dev/serial/by-id/
   ```
   これを **ID2** としてメモしてください。

### 2. udevルールファイルを作成する

設定ファイルを作成します。

```bash
sudo nano /etc/udev/rules.d/99-hysera.rules
```

エディタが開いたら、以下の内容を記述します。
**`<ID1>` と `<ID2>` の部分は、先ほどメモした実際のシリアル番号に書き換えてください（カッコ `< >` は不要です）。**

例: IDが `8543...` の場合 → `ATTRS{serial}=="8543..."`

```udev
# Hysera Pump 1-3 (Arduino 1)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="0042", ATTRS{serial}=="<ID1>", SYMLINK+="ttyHysera1"

# Hysera Pump 4-6 (Arduino 2)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="0042", ATTRS{serial}=="<ID2>", SYMLINK+="ttyHysera2"
```

※ Arduino Mega 2560の場合、通常 `idVendor` は `2341`、`idProduct` は `0042` です。もし異なる場合は `lsusb` コマンドで確認してください。
※ `ATTRS{serial}` の値は、`ls -l /dev/serial/by-id/` で確認した文字列の一部（長い数字の列）です。

書き終わったら、`Ctrl+O` → `Enter` で保存し、`Ctrl+X` で終了します。

### 3. 設定を反映する

以下のコマンドで設定を再読み込みします。

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 4. 確認

両方のArduinoを接続した状態で、以下のコマンドを実行します。

```bash
ls -l /dev/ttyHysera*
```

以下のように表示されれば成功です。
```
lrwxrwxrwx 1 root root 7 ... /dev/ttyHysera1 -> ttyACM1
lrwxrwxrwx 1 root root 7 ... /dev/ttyHysera2 -> ttyACM0
```
（矢印の先が ttyACM0 か ttyACM1 かは接続順によりますが、`ttyHysera1` は常にポンプ1-3用のArduinoを指すようになります）

## アプリケーション側の対応

`app.py` は、`/dev/ttyHysera1` と `/dev/ttyHysera2` が存在する場合、それらを優先して使用するように修正されています。
この設定を行えば、起動オプションなしでも常に正しいポートが選択されます。
