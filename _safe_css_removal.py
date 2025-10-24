#!/usr/bin/env python3
"""
pump_control.htmlからCSSブロックを安全に削除し、外部CSSリンクに置き換える
8行目から637行目までの<style>...</style>ブロックを削除
"""

def remove_css_safely():
    input_file = 'templates/pump_control.html'
    output_file = 'templates/pump_control.html'
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    original_count = len(lines)
    print(f"元のファイル: {original_count}行")
    
    # 7行目(index 6)までと、638行目(index 637)以降を保持
    # 8行目(index 7)の<style>から637行目(index 636)の</style>まで削除
    new_lines = []
    
    # 1-7行目: ヘッダー部分を保持
    new_lines.extend(lines[0:7])
    
    # 8行目: 外部CSSリンクを追加
    new_lines.append('    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/pump_control.css\') }}">\n')
    
    # 638行目以降: HTMLボディ部分を保持
    new_lines.extend(lines[637:])
    
    # ファイルに書き込み
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    new_count = len(new_lines)
    removed = original_count - new_count
    print(f"新しいファイル: {new_count}行")
    print(f"削除された行数: {removed}行")
    print(f"✓ CSS分離完了!")
    
    # 検証: <style>タグが残っていないか確認
    style_found = any('<style>' in line for line in new_lines)
    if style_found:
        print("警告: <style>タグが残っています!")
    else:
        print("✓ <style>タグは正常に削除されました")
    
    # 検証: 外部CSSリンクが追加されているか確認
    css_link_found = any('pump_control.css' in line for line in new_lines)
    if css_link_found:
        print("✓ 外部CSSリンクが追加されました")
    else:
        print("警告: 外部CSSリンクが見つかりません!")

if __name__ == '__main__':
    remove_css_safely()
