# FFmpegストリーミング機能ガイド

## 概要

このアプリケーションは、従来のMJPEGストリーミングに加えて、FFmpegを使用したHLS（HTTP Live Streaming）ストリーミング機能を提供します。

## 主な機能

### 1. デュアルストリーミング対応
- **MJPEGストリーミング**: 従来のリアルタイム画像ストリーミング
- **HLSストリーミング**: FFmpegを使用した高品質動画ストリーミング

### 2. 動的切り替え
- Web UIからストリーミング方式を動的に切り替え可能
- FFmpegストリーミングの開始/停止をリアルタイムで制御

### 3. 高品質エンコーディング
- H.264エンコーディング
- 低遅延設定（ultrafast preset, zerolatency tune）
- 適応的ビットレート制御

## セットアップ

### 1. FFmpegのインストール

#### Windows
1. [FFmpeg公式サイト](https://ffmpeg.org/download.html)からダウンロード
2. 解凍してPATHに追加
3. コマンドプロンプトで `ffmpeg -version` を実行して確認

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install ffmpeg
```

#### macOS
```bash
brew install ffmpeg
```

### 2. アプリケーションの起動

#### 通常起動（MJPEGストリーミング）
```bash
python app.py
```

#### FFmpegストリーミング自動開始
```bash
python app.py --use-ffmpeg
```

## 使用方法

### 1. Web UIでの操作

1. ブラウザで `http://localhost:5000` にアクセス
2. 以下のボタンを使用してストリーミングを制御：
   - **🎬 FFmpeg開始**: FFmpegストリーミングを開始
   - **⏹️ FFmpeg停止**: FFmpegストリーミングを停止
   - **📺 HLS表示**: HLSストリーミングに切り替え
   - **🖼️ MJPEG表示**: MJPEGストリーミングに切り替え

### 2. API エンドポイント

#### FFmpegストリーミング開始
```
GET /api/start_ffmpeg_streaming
```

#### FFmpegストリーミング停止
```
GET /api/stop_ffmpeg_streaming
```

#### FFmpeg状態確認
```
GET /api/ffmpeg_status
```

#### HLSプレイリスト取得
```
GET /video_feed_hls
```

#### HLSセグメント取得
```
GET /hls_segment/<segment_name>
```

## 技術仕様

### FFmpeg設定
- **エンコーダ**: libx264
- **プリセット**: ultrafast
- **チューニング**: zerolatency
- **品質**: CRF 23
- **最大ビットレート**: 2Mbps
- **バッファサイズ**: 4MB
- **セグメント長**: 2秒
- **プレイリストサイズ**: 3セグメント

### 対応フォーマット
- **入力**: V4L2 (Linux), DirectShow (Windows)
- **出力**: HLS (m3u8 + ts)
- **コーデック**: H.264

## トラブルシューティング

### 1. FFmpegが見つからない
```
エラー: FFmpegストリーミングセットアップエラー: [Errno 2] No such file or directory: 'ffmpeg'
```
**解決方法**: FFmpegがインストールされていないか、PATHに追加されていません。

### 2. カメラデバイスにアクセスできない
```
エラー: FFmpegプロセス開始エラー: Cannot find a valid device for "video=0"
```
**解決方法**: 
- カメラが正しく接続されているか確認
- 他のアプリケーションがカメラを使用していないか確認
- デバイス権限を確認

### 3. HLSプレイリストが表示されない
**解決方法**:
1. FFmpegプロセスが正常に開始されているか確認
2. 一時ディレクトリが作成されているか確認
3. ブラウザの開発者ツールでネットワークエラーを確認

## パフォーマンス最適化

### 1. セグメント設定の調整
```python
hls_segment_duration = 2  # セグメント長（秒）
hls_playlist_size = 3     # プレイリストサイズ
```

### 2. エンコーディング設定の調整
```python
'-crf', '23',           # 品質（18-28推奨）
'-maxrate', '2M',       # 最大ビットレート
'-bufsize', '4M',       # バッファサイズ
```

## セキュリティ考慮事項

1. **一時ファイル**: FFmpegは一時ディレクトリにセグメントファイルを作成します
2. **プロセス管理**: FFmpegプロセスは適切に終了処理されます
3. **リソース制限**: 長時間実行時のメモリ使用量に注意

## 今後の拡張予定

- [ ] WebRTCストリーミング対応
- [ ] 複数解像度対応（アダプティブストリーミング）
- [ ] 録画機能
- [ ] ストリーミング品質監視
- [ ] カスタムFFmpegパラメータ設定

## サポート

問題が発生した場合は、以下を確認してください：
1. FFmpegのバージョンとインストール状況
2. カメラデバイスの接続状況
3. システムリソース（CPU、メモリ）の使用状況
4. ネットワーク接続状況
