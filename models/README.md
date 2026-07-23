# 学習済みモデル

## 同梱モデル

`garbage-sort-yolo11n.pt` は、プロトタイプ動作用の試験学習済みYOLOモデルです。

対象クラスは以下の5種類です。

| ID | ラベル | 表示名 |
|---|---|---|
| 0 | plastic_bottle | ペットボトル |
| 1 | drink_can | 飲料缶 |
| 2 | glass_bottle | ガラスびん |
| 3 | aerosol_can | スプレー缶 |
| 4 | dry_battery | 乾電池 |

## 更新方法

再学習後にモデルを差し替える場合は、検証済みの `best.pt` を以下へコピーします。

```bash
cp runs/detect/train-11/weights/best.pt models/garbage-sort-yolo11n.pt
```

## 注意

- このモデルは発表用プロトタイプの試験モデルです。
- 元データセット、ZIP、学習用画像、`runs/` 配下の学習結果はGit管理しません。
- 別モデルを使う場合は `YOLO_MODEL_PATH` 環境変数で指定できます。
