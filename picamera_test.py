# PythonでOpenCVのテスト
import cv2
print(f'OpenCV version: {cv2.__version__}')
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print('カメラデバイス0を開けました')
    ret, frame = cap.read()
    if ret:
        print(f'フレーム取得成功: {frame.shape}')
    else:
        print('フレーム取得失敗')
    cap.release()
else:
    print('カメラデバイス0を開けませんでした')
