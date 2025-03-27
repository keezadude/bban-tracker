# beysion-tracker
beysion-trackerはBeysionに使用されているPythonプログラムです。
Realsence（赤外線カメラ）の映像からコマの検出、軌跡の割り出し、衝突判定を行い、結果をUnityに送信します。


## Beysion
Beysionはベイブレードの対戦に合わせて軌跡などのエフェクトを投影するシステムです。タッチテーブルの技術を応用しています。 
詳しくは以下のサイトをご覧ください。<br>
[紹介ページ](https://protopedia.net/prototype/4813)<br>
[プロモーション動画](https://youtu.be/p2AFd2a-vNg?si=FVmgyI9OplT2cY_B)<br>
[解説動画](https://youtu.be/wpbPGy0BBu8?si=w4hq-_JuJQdVVCqS)<br>
<br>
ヒーローズ・リーグ 2023でルーキーヒーロー賞、XUI賞、KOSEN賞をいただきました。
<br>
第29回日本バーチャルリアリティ学会大会で発表しました。
[VR学会講演論文](https://conference.vrsj.org/ac2024/program/doc/2G-10.pdf)


## 実行方法
python 3.11 で動作確認済みです。
1. 以下のコマンドでクローン
    ```bash
    git clone https://github.com/rowest4x/beysion-tracker.git
    ```
1. クローンしたディレクトリに移動
    ```bash
    cd beysion-tracker
    ```
1. 必要なら仮想環境を作成して起動
    ```bash
    python -m venv env
    .\env\Scripts\activate
    ```
1. ライブラリをインストール
    ```bash
    pip install -r requirements.txt
    ```
1. 実行
    ```bash
    python main.py
    ```
    

## カメラの設定
実行にはRealsenceが必要ですが、main関数内のカメラの初期化を以下のように変更することでWebカメラでも実行できます。
これはBeysionの実機に接続できない環境で開発するための設定で、実機で撮影した録画を仮想カメラに流すなどして使用します。
`dev_mode=True`でWebカメラ、`dev_mode=False`でRealsenceに接続します。
`src`はカメラのインデックスです。
```main.py
149:    camera = initializeCamera(dev_mode=True, src=0)
```


## ファイル構成
各ファイルの役割は以下の通りです。
- **main.py**<br>
    メインのプログラムです。
    - カメラ、ネットワーク、検出器、レジストリの初期化
    - 各フレームごとの画像取得、物体検出、結果の描画
    - UDP/TCP通信によるUnityとの連携
    - キーボード操作（終了、再キャリブレーション、しきい値調整）の処理

- **camera.py**<br>
    カメラストリームのクラスを定義しています。カメラからのフレームの読み込みを別スレッドで行うことで遅延を回避しています。
    - `RealsenseStream`：Intel RealSenseを利用したストリーム取得のためのクラス
    - `WebcamVideoStream`：通常のWebカメラを利用する場合のクラス
    - `FPS`：FPS計測クラス（デバッグ用にFPS表示も可能）

- **objects.py**<br>
    検出対象の情報を保存するオブジェクトを定義しています。コマの速度や加速度は一応計算してありますが使ってはいません。
    - `Contour`：OpenCVの輪郭情報を元に、位置や領域情報を取得するクラス
    - `Bey`：コマを表現するクラス。位置、サイズ、速度、加速度、IDなどを管理
    - `Hit`：コマ同士の衝突（ヒット）を表現するクラス
      
- **detector.py**<br>
    画像からコマや衝突箇所を検出するための処理が記述されています。
    - `calibrate()`：一定フレームの画像を取得し、背景の各画素について平均・標準偏差を計算（背景差分による検出のため）
    - `detect()`：背景との差分を利用して閾値処理、モルフォロジー変換でノイズを除去し、`__getObjects()`でコマ、衝突箇所の座標を取得（正確には`calibrate()`で計算した平均・標準偏差を用いて各画素の値を標準化してから閾値処理をしています）
    - `__getObjects()`：`cv2.findContours()`で輪郭抽出を行い、輪郭の面積によりコマとそれ以外を選別。コマ同士の距離が近い場合は衝突として検出。

- **registry.py**<br>
    検出結果の時系列管理およびIDの引き継ぎを行うモジュールです。
    - 各フレームで検出された`Bey`および`Hit`をリストに記録
    - 直近数フレームとの比較により、新規検出されたコマに対して、既存のIDを引き継ぐか新たなIDを割り当てる
    - Unityへの送信用メッセージを生成
