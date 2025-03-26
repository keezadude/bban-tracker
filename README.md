# beysion-tracker
beysion-trackerはBeysionに使用されているPythonプログラムです。
Realsence（赤外線カメラ）の映像からコマの検出、軌跡の割り出し、衝突判定を行い、結果をUnityに送信します。

### Beysion
Beysionはベイブレードの対戦に合わせて軌跡などのエフェクトを投影するシステムです。タッチテーブルの技術を応用しています。 
詳しくは以下のサイトをご覧ください。<br>
[紹介ページ](https://protopedia.net/prototype/4813)<br>
[プロモーション動画](https://youtu.be/p2AFd2a-vNg?si=FVmgyI9OplT2cY_B)<br>
[解説動画](https://youtu.be/wpbPGy0BBu8?si=w4hq-_JuJQdVVCqS)<br>
<br>
ヒーローズ・リーグ 2023でルーキーヒーロー賞，XUI賞，KOSEN賞をいただきました．
<br>
第29回日本バーチャルリアリティ学会大会で発表しました。
[VR学会講演論文](https://conference.vrsj.org/ac2024/program/doc/2G-10.pdf)

### 実行方法
python 3.11 で動作確認済みです。
1. 必要なライブラリをインストール
```bash
pip install -r requirements.txt
```

2. 実行
```bash
python main.py
```

### カメラの設定
実行にはRealsenceが必要ですが、main関数内のカメラの初期化を以下のように変更することでWebカメラでも実行できます。
これはBeysionの実機に接続できない環境で開発するための設定で、実機で撮影した録画を仮想カメラに流すなどして使用します。
```dev_mode=True```でWebカメラ、```dev_mode=False```でRealsenceに接続します。
```main.py
149:    camera = initializeCamera(dev_mode=True)
```
