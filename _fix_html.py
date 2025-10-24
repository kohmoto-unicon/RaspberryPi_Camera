#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一時的なスクリプト: 重複HTMLコードを削除"""

html_file = r'c:\work\Hicera\raps\RaspberryPi_Camera\templates\pump_control.html'

with open(html_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

output_lines = []
skip_mode = False

for i, line in enumerate(lines):
    # 55行目から不要なコードが開始
    if i == 54 and '<span>📹 カメラ</span>' in line:
        skip_mode = True
        # scriptタグの行は保持
        output_lines.append('  <script>\n')
        continue
    
    # 重複したdivやcontainerが終わるところまでスキップ
    if skip_mode:
        # JavaScriptの開始を検出したらスキップモード終了
        if '<script>' in line and i > 100:
            skip_mode = False
            continue
        else:
            continue
    
    output_lines.append(line)

# ファイルに書き戻し
with open(html_file, 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print(f"重複削除完了: {len(lines)} -> {len(output_lines)} lines")
