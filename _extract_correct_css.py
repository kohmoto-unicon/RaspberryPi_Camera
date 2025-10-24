#!/usr/bin/env python3
"""
バックアップファイルから正しいCSSを抽出
"""

def extract_css():
    backup_file = 'templates/pump_control.html.backup'
    output_css = 'static/css/pump_control.css'
    
    with open(backup_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 8行目(index 7)の<style>から637行目(index 636)の</style>まで
    css_lines = []
    in_style = False
    
    for i, line in enumerate(lines):
        if '<style>' in line:
            in_style = True
            # <style>行は含めない
            continue
        elif '</style>' in line:
            # </style>行も含めない
            break
        elif in_style:
            css_lines.append(line)
    
    # CSSファイルに書き込み
    with open(output_css, 'w', encoding='utf-8') as f:
        f.writelines(css_lines)
    
    print(f"✓ CSSを抽出しました: {len(css_lines)}行")
    print(f"✓ 出力先: {output_css}")

if __name__ == '__main__':
    extract_css()
