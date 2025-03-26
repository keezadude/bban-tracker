import cv2
import numpy as np
import socket
from detector import Detector
from registry import Registry
from camera import RealsenseStream, WebcamVideoStream

# 定数設定
HOST = '127.0.0.1'
UDP_PORT = 50007
TCP_PORT = 50008
CROP_SIZE = [(150, 15), (500, 350)]
BEY_COLORS = [(255, 0, 255), (0, 0, 255), (255, 0, 0)]
HIT_COLOR = (0, 255, 0)

def initializeCamera(dev_mode: bool = False):
    """
    カメラの初期化を行う．
    通常はRealsenseStreamを使用する．
    通常のWebカメラ，仮想カメラなどを使用する際はWebcamVideoStreamを使用する．
    あらかじめ撮影した赤外線カメラの映像をOBSなどの仮想カメラで流すことで，
    Beysionの実機に接続できない環境でも開発できる．
    """
    if dev_mode:
        return WebcamVideoStream(src=1).start()
    else:
        return RealsenseStream().start()

def initializeNetwork():
    """
    UDPクライアントと非同期TCPサーバの初期化を行う。
    """
    udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind((HOST, TCP_PORT))
    tcp_server.listen(1)
    tcp_server.setblocking(False)
    
    return udp_client, tcp_server

def getImage(camera) -> np.ndarray:
    """
    カメラから1フレームを読み込み、定義されたサイズでクロップした画像を返す。
    """
    ir_frame = camera.readNext()
    (x1, y1), (x2, y2) = CROP_SIZE
    return ir_frame[y1:y2, x1:x2].copy()

def processNetwork(tcp_server, tcp_client_socket, detector, image_getter):
    """
    TCP接続の処理を行い、Unityからの要求（キャリブレーションやしきい値調整）に応じる。
    新規接続の受け付けや、接続済みクライアントからのメッセージ処理を行う。
    """
    if tcp_client_socket is None:
        try:
            tcp_client_socket, addr = tcp_server.accept()
            tcp_client_socket.setblocking(False)
            print(f"Connected to Unity: {addr}")
        except BlockingIOError:
            return None
    else:
        try:
            data = tcp_client_socket.recv(1024)
            if not data:
                print("Unity disconnected.")
                tcp_client_socket.close()
                return None
            else:
                message = data.decode()
                if message == "calibrate":
                    detector.calibrate(image_getter)
                    response = "calibrated"
                    tcp_client_socket.send(response.encode('utf-8'))
                elif message == "threshold_up":
                    detector.threshold += 1
                    response = f"threshold:{detector.threshold}"
                    tcp_client_socket.send(response.encode('utf-8'))
                elif message == "threshold_down":
                    detector.threshold -= 1
                    response = f"threshold:{detector.threshold}"
                    tcp_client_socket.send(response.encode('utf-8'))
        except BlockingIOError:
            pass
        except ConnectionResetError:
            print("Unity reset.")
            tcp_client_socket.close()
            return None
    return tcp_client_socket

def drawResults(ir_img: np.ndarray, beys: list, hits: list, registry: Registry):
    """
    検出されたコマ（Bey）や衝突（Hit）の情報を画像上に描画する。
    複数の描画用ウィンドウ（result, result2）を生成する。
    """
    result = cv2.cvtColor(ir_img, cv2.COLOR_GRAY2BGR)
    result2 = np.zeros_like(result)
    result2[:, :, 0] = 255
    result2[5:-5, 5:-5, 0] = 0

    # コマの矩形描画
    for bey in beys:
        pos1, pos2 = bey.getRect()
        color = BEY_COLORS[bey.getId() % len(BEY_COLORS)]
        cv2.rectangle(result, pos1, pos2, color, 2)
    
    # 軌跡描画（直近フレームからの履歴を利用）
    pre_poses: dict[int, tuple[int, int]] = {}
    for beys_frame in registry.getBeyList():
        for bey in beys_frame:
            pos = bey.getPos()
            id = bey.getId()
            if id in pre_poses:
                cv2.line(result, pre_poses[id], pos, BEY_COLORS[id % len(BEY_COLORS)], thickness=2)
                cv2.line(result2, pre_poses[id], pos, BEY_COLORS[id % len(BEY_COLORS)], thickness=2)
            pre_poses[id] = pos

    # 衝突部分の描画
    for hit in hits:
        pos1, pos2 = hit.getRect()
        cv2.rectangle(result, pos1, pos2, HIT_COLOR, 2)
    for hits_frame in registry.getHitList()[-5:]:
        for hit in hits_frame:
            pos = hit.getPos()
            cv2.circle(result, pos, 8, HIT_COLOR, thickness=-1)
            cv2.circle(result2, pos, 8, HIT_COLOR, thickness=-1)
    
    return result, result2

def handleKeyboard(detector, image_getter):
    """
    キーボード入力に応じた処理を実行する。
    ESC で終了、's' で再キャリブレーション、't' でしきい値調整を行う。
    """
    key = cv2.waitKey(1)
    if key == 27:
        return False
    elif key == ord('s'):
        detector.calibrate(image_getter)
    elif key == ord('t'):
        print("default threshold is 15.")
        detector.threshold = int(input("threshold = "))
        print("successful")
    return True

def main():
    # カメラ初期化
    camera = initializeCamera(dev_mode=True)

    # 事前に複数フレーム読み込んでカメラの安定を図る
    for _ in range(20):
        getImage(camera)
    
    # 検出器とレジストリの初期化
    detector = Detector()
    detector.calibrate(lambda: getImage(camera))
    registry = Registry()

    # ネットワーク初期化
    udp_client, tcp_server = initializeNetwork()
    tcp_client_socket = None

    # メインループ
    while True:
        # カメラから画像を取得
        ir_img = getImage(camera)
        
        # コマと衝突箇所の検出
        beys, hits = detector.detect(ir_img)
        registry.register(beys, hits)
        
        # Unity へ UDP で結果を送信
        message = registry.getMessage()
        udp_client.sendto(message.encode('utf-8'), (HOST, UDP_PORT))
        
        # 検出結果を描画
        result, result2 = drawResults(ir_img, beys, hits, registry)
        cv2.imshow('result', result)
        cv2.imshow('result2', result2)
        
        # キーボード入力処理
        if not handleKeyboard(detector, lambda: getImage(camera)):
            break
        
        # TCP 通信処理（Unity からの要求への対応）
        tcp_client_socket = processNetwork(tcp_server, tcp_client_socket, detector, lambda: getImage(camera))
        
        # 次フレームへ進む
        registry.nextFrame()

    # 終了処理：リソースの解放
    camera.close()
    udp_client.close()
    if tcp_client_socket is not None:
        try:
            tcp_client_socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        tcp_client_socket.close()
    tcp_server.close()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
