# TACO・追加データセット準備

## 目的

TACO由来データセットをベースに、必要に応じて追加データセットを確認し、最初のYOLO学習対象とする5種類のごみだけを抽出する。

## 学習用クラス

| 新クラスID | 学習用クラス名 | 主な意味 |
|---:|---|---|
| 0 | plastic_bottle | ペットボトル |
| 1 | drink_can | 飲料缶 |
| 2 | glass_bottle | ガラスびん |
| 3 | aerosol_can | スプレー缶 |
| 4 | dry_battery | 円筒形の乾電池 |

## 確認した元データセット

| データセット | 配置先 | 利用判断 |
|---|---|---|
| TACO | `data/raw/taco/` | 5クラスのベースとして利用する |
| Trash Detection | `data/raw/trash_detection/` | 大分類ラベルのため自動統合しない |
| Batteries.v3i.yolov8 | `data/raw/batteries/` | 乾電池と目視確認した画像だけ利用する |
| spray can.v3-02.yolov8 | `data/raw/spray_can/` | エアゾール缶と目視確認した画像だけ利用する |
| glass bottle.v5i.yolov8 | `data/raw/glass_bottle/` | 一般的なガラスびんとして使える画像だけ利用する |
| Plastic Bottles.v1i.yolov8 | `data/raw/plastic_bottles/` | 飲料用ペットボトルとして使える画像だけ利用する |

## データセット別の判断

### TACO

Roboflow YOLO形式の `data.yaml` に以下の対象クラスが存在するため、学習用クラスIDへ振り直して利用する。

| 元データのクラス名 | 学習用クラス名 |
|---|---|
| Clear plastic bottle | plastic_bottle |
| Drink can | drink_can |
| Glass bottle | glass_bottle |
| Aerosol | aerosol_can |
| Battery | dry_battery |

### Trash Detection

クラスは `Glass`、`Metal`、`Paper`、`Plastic`、`Waste` の大分類である。`Metal` には飲料缶、金属フタ、一般金属などが混ざり、`aerosol_can` や `drink_can` として一意に扱えない。

そのため、現段階では自動統合しない。必要な場合は、スプレー缶だけを再アノテーションする。

### Batteries.v3i.yolov8

元クラスは1種類だが、確認したサンプルには円筒形乾電池だけでなく、9V電池、ボタン電池、ノートPC用バッテリーやバッテリーパックと思われる画像が含まれていた。

今回の `dry_battery` はAA、AAAなどの円筒形乾電池を想定するため、全件を自動統合しない。乾電池と判断できる画像だけを手動確認し、allowlistに記載したものだけ統合する。

2026-07-21時点では、バウンディングボックス形状による候補抽出と一覧画像の目視確認により、4004枚中937枚を `dry_battery` 用として採用した。主な除外理由は、ボックス形状が円筒形乾電池に見えない画像、バッテリーパック混入リスクが高い `battery...` 系ファイル、9V角形電池混入、判別困難な小物、人物手持ちで対象が小さい画像である。

その後、`dry_battery` のtrain件数が他クラスより多くなりすぎたため、評価用の `val` と `test` は維持し、trainのみ見た目の多様性を保つ形で251物体へダウンサンプリングした。ダウンサンプリングでは、Roboflow拡張前の元画像名ごとに代表画像を選び、8x8 RGB特徴量の距離が離れる画像を優先している。

allowlistを使う場合は、画像パス、ファイル名、または拡張子なしのstemを1行ずつ書く。

```text
train/images/example.jpg
example.jpg
example
```

### spray can.v3-02.yolov8

元クラスは `1`、`LED`、`spray can`、`toilet cleaner` の4種類である。今回の `aerosol_can` には、自治体でスプレー缶として分別される金属製の加圧式エアゾール缶だけを採用する。

2026-07-21時点では、全画像レビューHTMLとバウンディングボックス付きサムネイルを確認し、283枚中67枚を `aerosol_can` 用として採用した。LED管、トリガー式スプレーボトル、ポンプ式ボトル、通常ボトル、洗剤ボトル、スプレー缶か判別しにくい画像は除外した。

元データでは `spray can` 候補がtrainに偏っていたため、採用画像のみ決定的ハッシュで `train`、`val`、`test` に再分割する。これにより、同じ画像が複数分割へ入らないようにする。

### glass bottle.v5i.yolov8

元クラスは `brown_glass_bottle`、`clear_glass_bottle`、`glass bottle` の3種類である。3クラスとも今回の `glass_bottle` に対応付ける。

2026-07-22時点では、全画像レビューHTMLを `data/review/glass_bottle_review.html` に作成し、一般的なガラス容器として使える候補から多様性優先でallowlistを作成した。追加しすぎるとクラスバランスが崩れるため、既存データを含めてtrainの `glass_bottle` が約200〜300物体になるように抑える。

採用allowlistは `data/config/glass_bottle_allowlist_balanced.txt` に保存する。画像ハッシュ重複確認により、trainとval/testにまたがる重複元画像はtrain側から除外した。

### Plastic Bottles.v1i.yolov8

元クラスは `plastic-bottle` の1種類である。今回の `plastic_bottle` に対応付ける。

2026-07-22時点では、全画像レビューHTMLを `data/review/plastic_bottles_review.html` に作成し、飲料用ペットボトルとして使える候補から多様性優先でallowlistを作成した。既存データを含めてtrainの `plastic_bottle` が約250〜350物体になるように抑える。

採用allowlistは `data/config/plastic_bottle_allowlist_balanced.txt` に保存する。

## 出力先

抽出後の学習用データセットは `data/yolo_dataset/` に作成する。

```text
data/yolo_dataset/
├── images/
│   ├── train/
│   ├── val/
│   └── test/
├── labels/
│   ├── train/
│   ├── val/
│   └── test/
└── data.yaml
```

Roboflowの `valid` は、学習用出力では `val` に統一する。

## 抽出方法

TACOのみで安全に抽出する場合は以下を実行する。

```bash
python3 ai/prepare_taco_dataset.py
```

Batteriesから目視確認済みの乾電池画像だけを追加する場合は以下を実行する。

```bash
python3 ai/prepare_taco_dataset.py \
  --battery-allowlist data/config/batteries_dry_battery_allowlist_balanced.txt \
  --spray-can-allowlist data/config/spray_can_aerosol_allowlist.txt \
  --glass-bottle-allowlist data/config/glass_bottle_allowlist_balanced.txt \
  --plastic-bottle-allowlist data/config/plastic_bottle_allowlist_balanced.txt
```

このスクリプトは、対象5クラス以外のアノテーションを削除し、対象クラスが1件も残らない画像は出力しない。複数物体が写っている画像では、対象5クラスのラベルだけを残す。

## 学習コマンド例

```bash
yolo detect train \
  model=yolo11n.pt \
  data=data/yolo_dataset/data.yaml \
  epochs=50 \
  imgsz=640 \
  batch=8
```

Python入口を使う場合は以下を実行する。

```bash
python3 ai/train.py --model yolo11n.pt --epochs 50 --imgsz 640 --batch 8
```

## 注意事項

- TACO、Trash Detection、BatteriesはいずれもRoboflow Universe由来の公開データセットである。
- 元データのライセンスはRoboflow表示上 `CC BY 4.0` だが、利用・公開前に必ず元データセット側の最新ライセンスを確認する。
- ZIPファイル、展開済み元データ、抽出後の大量画像は、容量とライセンスを確認するまでGitHubへ直接コミットしない。
- `data/raw/` と `data/yolo_dataset/` のデータ本体はGit管理対象外とする。
- クラス定義が合わないデータを無理に混ぜると、YOLOが誤った特徴を学習するため、件数よりラベル品質を優先する。

## 2026-07-22 統合結果

Glass Bottle系とPlastic Bottle系の追加後、統合後データセットは以下の件数になった。

| split | images | objects | plastic_bottle | drink_can | glass_bottle | aerosol_can | dry_battery |
|---|---:|---:|---:|---:|---:|---:|---:|
| train | 822 | 1060 | 308 | 162 | 278 | 59 | 253 |
| val | 311 | 467 | 121 | 42 | 118 | 9 | 177 |
| test | 164 | 272 | 76 | 27 | 46 | 16 | 107 |

検証結果は以下である。

- 空ラベルなし
- 不正クラスIDなし
- 画像とラベルの対応不一致なし
- splitまたぎ画像ハッシュ重複なし

この状態で30epoch再学習に進める。
