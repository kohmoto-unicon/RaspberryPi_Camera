#!/bin/bash
# ラズパイカメラストリーミング起動スクリプト（オフライン版）

cd "$(dirname "$0")"

# 仮想環境をアクティベート
source venv/bin/activate

# アプリケーションを起動
python app.py
