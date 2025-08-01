#!/bin/bash

# ラズパイカメラストリーミング起動スクリプト
# 使用方法: ./start.sh

# スクリプトのディレクトリに移動
cd "$(dirname "$0")"

# 色付きの出力用関数
print_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

print_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

# ヘルプ表示
show_help() {
    echo "ラズパイカメラストリーミング起動スクリプト"
    echo ""
    echo "使用方法:"
    echo "  ./start.sh          # 通常起動"
    echo "  ./start.sh --help   # ヘルプ表示"
    echo "  ./start.sh --debug  # デバッグモードで起動"
    echo "  ./start.sh --check  # 環境チェックのみ"
    echo ""
    echo "オプション:"
    echo "  --help    このヘルプを表示"
    echo "  --debug   デバッグモードで起動"
    echo "  --check   環境チェックのみ実行"
    echo "  --port    ポート番号を指定（例: --port 8080）"
    echo ""
}

# 環境チェック
check_environment() {
    print_info "環境チェックを開始..."
    
    # 仮想環境の確認
    if [ ! -d "venv" ]; then
        print_error "仮想環境が見つかりません。setup.pyを実行してください。"
        return 1
    fi
    
    # Pythonの確認
    if [ ! -f "venv/bin/python" ]; then
        print_error "仮想環境内にPythonが見つかりません。"
        return 1
    fi
    
    # アプリケーションファイルの確認
    if [ ! -f "app.py" ]; then
        print_error "app.pyが見つかりません。"
        return 1
    fi
    
    # カメラデバイスの確認
    if [ ! -e "/dev/video0" ]; then
        print_warning "カメラデバイス (/dev/video0) が見つかりません。"
        print_warning "カメラモジュールが正しく接続されているか確認してください。"
    else
        print_success "カメラデバイスが見つかりました。"
    fi
    
    # カメラ情報の確認
    if command -v vcgencmd >/dev/null 2>&1; then
        camera_info=$(vcgencmd get_camera 2>/dev/null)
        if [ $? -eq 0 ]; then
            print_success "カメラ情報: $camera_info"
        else
            print_warning "カメラ情報の取得に失敗しました。"
        fi
    fi
    
    print_success "環境チェックが完了しました。"
    return 0
}

# 仮想環境のアクティベート
activate_venv() {
    print_info "仮想環境をアクティベート中..."
    
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_success "仮想環境がアクティベートされました。"
        return 0
    else
        print_error "仮想環境のアクティベートスクリプトが見つかりません。"
        return 1
    fi
}

# 依存関係の確認
check_dependencies() {
    print_info "依存関係を確認中..."
    
    # 仮想環境内でpip listを実行
    if source venv/bin/activate 2>/dev/null; then
        required_packages=("Flask" "opencv-python" "picamera2" "numpy" "Pillow")
        missing_packages=()
        
        for package in "${required_packages[@]}"; do
            if ! pip show "$package" >/dev/null 2>&1; then
                missing_packages+=("$package")
            fi
        done
        
        if [ ${#missing_packages[@]} -eq 0 ]; then
            print_success "すべての依存関係がインストールされています。"
            return 0
        else
            print_warning "以下のパッケージが不足しています:"
            for package in "${missing_packages[@]}"; do
                echo "  - $package"
            done
            print_info "setup.pyを再実行するか、手動でパッケージをインストールしてください。"
            return 1
        fi
    else
        print_error "仮想環境のアクティベートに失敗しました。"
        return 1
    fi
}

# アプリケーションの起動
start_application() {
    local port=${1:-5000}
    local debug_mode=${2:-false}
    
    print_info "アプリケーションを起動中..."
    print_info "ポート: $port"
    
    if [ "$debug_mode" = "true" ]; then
        print_info "デバッグモードで起動します。"
        python app.py --debug --port "$port"
    else
        print_info "本番モードで起動します。"
        python app.py --port "$port"
    fi
}

# メイン処理
main() {
    local check_only=false
    local debug_mode=false
    local port=5000
    
    # 引数の解析
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --check)
                check_only=true
                shift
                ;;
            --debug)
                debug_mode=true
                shift
                ;;
            --port)
                port="$2"
                shift 2
                ;;
            *)
                print_error "不明なオプション: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 環境チェック
    if ! check_environment; then
        print_error "環境チェックに失敗しました。"
        exit 1
    fi
    
    # チェックのみの場合は終了
    if [ "$check_only" = "true" ]; then
        print_success "環境チェックが完了しました。"
        exit 0
    fi
    
    # 依存関係の確認
    if ! check_dependencies; then
        print_warning "依存関係に問題がありますが、起動を続行します。"
    fi
    
    # 仮想環境のアクティベート
    if ! activate_venv; then
        print_error "仮想環境のアクティベートに失敗しました。"
        exit 1
    fi
    
    # 起動メッセージ
    echo ""
    print_success "ラズパイカメラストリーミングを起動します..."
    print_info "ブラウザで http://localhost:$port にアクセスしてください"
    print_info "停止するには Ctrl+C を押してください"
    echo ""
    
    # アプリケーションの起動
    start_application "$port" "$debug_mode"
}

# スクリプトが直接実行された場合のみmain関数を呼び出し
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi 