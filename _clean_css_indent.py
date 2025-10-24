#!/usr/bin/env python3
"""
CSSファイルのインデントを整形
"""

def clean_css():
    input_file = 'static/css/pump_control.css'
    output_file = 'static/css/pump_control.css'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 各行の先頭の4つのスペースを削除
    cleaned_lines = []
    for line in lines:
        if line.startswith('    '):
            cleaned_lines.append(line[4:])
        else:
            cleaned_lines.append(line)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(cleaned_lines)
    
    print(f"✓ CSSインデントを整形しました: {len(cleaned_lines)}行")

if __name__ == '__main__':
    clean_css()
