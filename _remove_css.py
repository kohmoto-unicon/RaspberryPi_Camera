#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一時的なスクリプト: HTMLからインラインCSSを削除"""

import re

html_file = r'c:\work\Hicera\raps\RaspberryPi_Camera\templates\pump_control.html'

with open(html_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# CSSブロックを削除
# </style>タグを見つけて、その前のCSS行を全て削除
output_lines = []
in_css_block = False
css_start = -1

for i, line in enumerate(lines):
    # CSSブロックの開始を検出
    if '.control-group {' in line or '.header p {' in line or '@media' in line:
        if not in_css_block:
            in_css_block = True
            css_start = i
            continue
    
    # </style>タグを検出
    if '</style>' in line and in_css_block:
        in_css_block = False
        continue
    
    # </head>タグを検出して、次から<body>を開始
    if '</head>' in line and not in_css_block:
        output_lines.append(line)
        continue
    
    # CSSブロック内の行はスキップ
    if in_css_block:
        continue
    
    output_lines.append(line)

# ファイルに書き戻し
with open(html_file, 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print(f"CSS削除完了: {len(lines)} -> {len(output_lines)} lines")
