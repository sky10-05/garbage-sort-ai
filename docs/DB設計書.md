# DB設計書

## 1. 概要

本システムでは、カメラで認識したごみに対して、選択された自治体の分別ルールを参照し、画面表示とTTSによる音声案内を行う。

使用DBはSQLiteを想定する。

## 2. 設計方針

- 一度に認識するごみは1個のみとする
- 信頼度が70%未満の場合は再撮影を促す
- 再撮影しても認識できない場合は候補を最大3つ表示する
- 市区町村は初回起動時に選択し、選択した自治体IDをローカル環境に保存する
- 次回以降は保存済み自治体を使ってトップ画面から開始する
- 未対応ごみは判定不可として表示し、意見箱に登録できるようにする
- 条件分岐質問は最大2問までとする
- 追加情報質問は条件分岐質問とは別管理にする
- 判定履歴は詳細に保存する
- 画像は同意した場合のみ保存する
- 画像本体はDBに保存せず、画像パスのみ保存する
- 音声案内はTTSで案内文を読み上げる

## 3. テーブル一覧

| テーブル名 | 役割 |
|---|---|
| prefecture | 都道府県情報を管理する |
| municipality | 市区町村情報を管理する |
| garbage_master | AIが認識するごみ自体を管理する |
| garbage_type | 可燃ごみ・資源ごみなどの分類を管理する |
| garbage_rule | 自治体ごとの分別ルールを管理する |
| question_type | 分別結果を決めるための条件分岐質問を管理する |
| question_answer | 条件分岐質問の回答ごとの案内結果を管理する |
| info_question_type | 利用者が追加で知りたい情報の質問を管理する |
| info_answer | 追加情報質問への回答を管理する |
| history | 判定履歴の基本情報を管理する |
| history_question_answer | 判定時の質問回答履歴を管理する |
| feedback | 未対応ごみや判定不可時の意見箱を管理する |

## 4. テーブル定義

### 4.1 prefecture

都道府県情報を管理する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| prefecture_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 都道府県ID |
| prefecture_name | TEXT | NOT NULL UNIQUE | 都道府県名 |

### 4.2 municipality

市区町村情報を管理する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| municipality_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 市区町村ID |
| prefecture_id | INTEGER | NOT NULL, FOREIGN KEY | 都道府県ID |
| municipality_name | TEXT | NOT NULL | 市区町村名 |

制約:

- `FOREIGN KEY(prefecture_id) REFERENCES prefecture(prefecture_id)`
- `UNIQUE(prefecture_id, municipality_name)`

### 4.3 garbage_master

AIが認識するごみ自体を管理する。YOLOなどの画像認識モデルのラベル名と、画面表示用のごみ名を対応させる。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| garbage_id | INTEGER | PRIMARY KEY AUTOINCREMENT | ごみID |
| garbage_name | TEXT | NOT NULL | 表示用のごみ名 |
| yolo_label | TEXT | NOT NULL UNIQUE | AIモデルが出力するラベル名 |
| description | TEXT | | 補足説明 |

### 4.4 garbage_type

ごみ分類を管理する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| garbage_type_id | INTEGER | PRIMARY KEY AUTOINCREMENT | ごみ分類ID |
| type_name | TEXT | NOT NULL UNIQUE | ごみ分類名 |
| description | TEXT | | 説明 |

例:

- 可燃ごみ
- 不燃ごみ
- 資源ごみ
- 粗大ごみ
- 有害ごみ

### 4.5 garbage_rule

自治体ごとのごみ分別ルールを管理する。ごみ名は直接持たず、`garbage_master` の `garbage_id` を参照する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| rule_id | INTEGER | PRIMARY KEY AUTOINCREMENT | ルールID |
| municipality_id | INTEGER | NOT NULL, FOREIGN KEY | 市区町村ID |
| garbage_id | INTEGER | NOT NULL, FOREIGN KEY | ごみID |
| garbage_type_id | INTEGER | NOT NULL, FOREIGN KEY | 基本のごみ分類ID |
| guide_text | TEXT | NOT NULL | 基本の案内文 |
| note | TEXT | | 補足情報 |
| need_question | INTEGER | NOT NULL DEFAULT 0 CHECK(need_question IN (0, 1)) | 条件分岐質問が必要か |

制約:

- `FOREIGN KEY(municipality_id) REFERENCES municipality(municipality_id)`
- `FOREIGN KEY(garbage_id) REFERENCES garbage_master(garbage_id)`
- `FOREIGN KEY(garbage_type_id) REFERENCES garbage_type(garbage_type_id)`
- `UNIQUE(municipality_id, garbage_id)`

補足:

- `need_question` は、条件分岐質問の有無をUIで判定しやすくするために保持する。
- 実装時は、`question_answer` の有無との不整合が起きないように初期データ作成時に確認する。

### 4.6 question_type

分別結果を決めるための条件分岐質問を管理する。

例:

- 汚れていますか？
- 電池は入っていますか？
- 中身は残っていますか？
- 大きさは30cm以上ですか？

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| question_type_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 質問種別ID |
| question_text | TEXT | NOT NULL UNIQUE | 質問文 |

### 4.7 question_answer

条件分岐質問の回答ごとの案内結果を管理する。質問数は最大2問までを想定する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| answer_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 回答ID |
| rule_id | INTEGER | NOT NULL, FOREIGN KEY | 対象の分別ルールID |
| question_type_id | INTEGER | NOT NULL, FOREIGN KEY | 質問種別ID |
| question_order | INTEGER | NOT NULL CHECK(question_order BETWEEN 1 AND 2) | 質問順 |
| answer_value | TEXT | NOT NULL | 回答内容 |
| result_garbage_type_id | INTEGER | FOREIGN KEY | 回答後のごみ分類ID |
| result_guide_text | TEXT | NOT NULL | 回答後の案内文 |
| next_question_type_id | INTEGER | FOREIGN KEY | 次の質問がある場合の質問種別ID |

制約:

- `FOREIGN KEY(rule_id) REFERENCES garbage_rule(rule_id)`
- `FOREIGN KEY(question_type_id) REFERENCES question_type(question_type_id)`
- `FOREIGN KEY(result_garbage_type_id) REFERENCES garbage_type(garbage_type_id)`
- `FOREIGN KEY(next_question_type_id) REFERENCES question_type(question_type_id)`
- `UNIQUE(rule_id, question_type_id, answer_value)`

### 4.8 info_question_type

利用者が追加で知りたい情報の質問を管理する。これは分別結果を変える質問ではなく、判定後に追加で確認するための質問である。

例:

- 注意事項はありますか？
- いつ出せますか？
- どこに出せますか？
- 他のごみとして捨てられますか？

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| info_question_type_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 追加情報質問ID |
| question_text | TEXT | NOT NULL UNIQUE | 追加情報の質問文 |

### 4.9 info_answer

追加情報質問に対する回答を管理する。自治体ごとの分別ルールに紐づけることで、同じ質問でも自治体やごみによって異なる回答を返せるようにする。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| info_answer_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 追加情報回答ID |
| rule_id | INTEGER | NOT NULL, FOREIGN KEY | 対象の分別ルールID |
| info_question_type_id | INTEGER | NOT NULL, FOREIGN KEY | 追加情報質問ID |
| answer_text | TEXT | NOT NULL | 回答文 |

制約:

- `FOREIGN KEY(rule_id) REFERENCES garbage_rule(rule_id)`
- `FOREIGN KEY(info_question_type_id) REFERENCES info_question_type(info_question_type_id)`
- `UNIQUE(rule_id, info_question_type_id)`

### 4.10 history

画像認識と判定結果の基本履歴を管理する。質問回答の詳細は `history_question_answer` に分けて保存する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| history_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 履歴ID |
| municipality_id | INTEGER | NOT NULL, FOREIGN KEY | 判定時に選択した市区町村ID |
| detected_garbage_id | INTEGER | FOREIGN KEY | AIが認識したごみID |
| detected_label | TEXT | NOT NULL | AIが出力したラベル名 |
| confidence | REAL | CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)) | AIの信頼度 |
| rule_id | INTEGER | FOREIGN KEY | 使用したルールID |
| result_garbage_type_id | INTEGER | FOREIGN KEY | 最終的なごみ分類ID |
| result_guide_text | TEXT | | 最終案内文 |
| image_save_consent | INTEGER | NOT NULL DEFAULT 0 CHECK(image_save_consent IN (0, 1)) | 画像保存への同意 |
| image_saved | INTEGER | NOT NULL DEFAULT 0 CHECK(image_saved IN (0, 1)) | 実際に画像保存できたか |
| image_path | TEXT | | 保存画像のパス |
| result_status | TEXT | NOT NULL CHECK(result_status IN ('success', 'low_confidence', 'unknown', 'no_rule', 'candidate_selected')) | 判定結果状態 |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP | 判定日時 |

制約:

- `FOREIGN KEY(municipality_id) REFERENCES municipality(municipality_id)`
- `FOREIGN KEY(detected_garbage_id) REFERENCES garbage_master(garbage_id)`
- `FOREIGN KEY(rule_id) REFERENCES garbage_rule(rule_id)`
- `FOREIGN KEY(result_garbage_type_id) REFERENCES garbage_type(garbage_type_id)`

画像保存状態の整合ルール:

- `image_save_consent = 0` の場合、`image_saved = 0` とし、`image_path = NULL` とする
- `image_saved = 1` の場合、`image_save_consent = 1` かつ `image_path IS NOT NULL` とする
- 上記の整合性はアプリ側の保存処理でも検証する

案内文の扱い:

- `success` や `candidate_selected` の場合は、アプリ側で `result_guide_text` を必須として扱う
- `unknown` や `low_confidence` の場合は、`result_guide_text` が `NULL` になる可能性を許容する

`result_status` の例:

| 値 | 意味 |
|---|---|
| success | 判定成功 |
| low_confidence | 信頼度不足 |
| unknown | 未対応ごみ |
| no_rule | 自治体ルール未登録 |
| candidate_selected | 候補から選択 |

### 4.11 history_question_answer

判定時に表示した条件分岐質問と、利用者の回答を履歴として保存する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| history_question_answer_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 質問回答履歴ID |
| history_id | INTEGER | NOT NULL, FOREIGN KEY | 履歴ID |
| question_order | INTEGER | NOT NULL CHECK(question_order BETWEEN 1 AND 2) | 質問順 |
| question_text | TEXT | NOT NULL | 判定時に表示した質問文 |
| answer_value | TEXT | NOT NULL | 利用者の回答 |

制約:

- `FOREIGN KEY(history_id) REFERENCES history(history_id)`
- `UNIQUE(history_id, question_order)`

### 4.12 feedback

判定できなかったごみや、未対応ごみに対する意見箱を管理する。後日、モデルや分別ルールを追加するための参考データとして利用する。

| カラム名 | 型 | 制約 | 説明 |
|---|---|---|---|
| feedback_id | INTEGER | PRIMARY KEY AUTOINCREMENT | 意見ID |
| history_id | INTEGER | FOREIGN KEY | 関連する履歴ID |
| municipality_id | INTEGER | FOREIGN KEY | 市区町村ID |
| input_garbage_name | TEXT | | ユーザーが入力したごみ名 |
| comment | TEXT | | ユーザーの補足コメント |
| image_path | TEXT | | 同意がある場合の画像パス |
| status | TEXT | NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'reviewed', 'added_to_dataset', 'closed')) | 対応状況 |
| admin_note | TEXT | | 管理者メモ |
| created_at | TEXT | NOT NULL DEFAULT CURRENT_TIMESTAMP | 登録日時 |

制約:

- `FOREIGN KEY(history_id) REFERENCES history(history_id)`
- `FOREIGN KEY(municipality_id) REFERENCES municipality(municipality_id)`

## 5. テーブル同士の関係

```text
prefecture
  └── municipality
        ├── garbage_rule
        │     ├── garbage_master
        │     ├── garbage_type
        │     ├── question_answer
        │     │     ├── question_type
        │     │     └── garbage_type
        │     └── info_answer
        │           └── info_question_type
        │
        ├── history
        │     ├── garbage_master
        │     ├── garbage_rule
        │     ├── garbage_type
        │     └── history_question_answer
        │
        └── feedback
              └── history
```

## 6. 判定履歴に保存する内容

`history` には以下を保存する。

- 判定日時
- 選択した市区町村
- AIが認識したごみID
- AIが出力したラベル名
- AIの信頼度
- 使用した分別ルール
- 最終的なごみ分類
- 最終案内文
- 画像保存同意の有無
- 実際に画像保存できたか
- 判定画像の保存先
- 判定結果状態

`history_question_answer` には以下を保存する。

- 表示した質問文
- ユーザーの回答
- 質問順

## 7. 画像保存の方針

画像は、ユーザーが保存に同意した場合のみ保存する。

- 同意なし: `image_save_consent = 0`、`image_saved = 0`、`image_path = NULL`
- 同意あり・保存成功: `image_save_consent = 1`、`image_saved = 1`、`image_path` に保存先を登録
- 同意あり・保存失敗: `image_save_consent = 1`、`image_saved = 0`、`image_path = NULL`

画像そのものはDBに保存せず、画像ファイルの保存パスのみ保存する。保存した画像は、今後のAIモデル改善や誤判定分析に活用する。

## 8. 質問の設計方針

質問は2種類に分けて管理する。

### 8.1 条件分岐質問

分別結果を決めるための質問。`question_type` / `question_answer` で管理する。

例:

- 汚れていますか？
- 中身は残っていますか？
- 電池は入っていますか？

### 8.2 追加情報質問

分別結果が決まったあと、利用者が追加で知りたい情報。`info_question_type` / `info_answer` で管理する。

例:

- 注意事項はありますか？
- いつ出せますか？
- どこに出せますか？
- 他のごみとして捨てられますか？

## 9. garbage_master を追加する理由

`garbage_master` は、ごみ自体を管理するためのテーブルである。

`garbage_rule` に直接ごみ名を持たせると、自治体ごとに同じごみ名を何度も登録する必要がある。また、AIが出力するYOLOラベル名と、画面に表示する日本語名の対応も分かりにくくなる。

そのため、以下のように分けて管理する。

- ごみ自体の情報: `garbage_master`
- 自治体ごとの捨て方: `garbage_rule`

## 10. SQLite実装方針

SQLiteで実装する際は、以下の方針とする。

- アプリ起動時またはDB接続時に `PRAGMA foreign_keys = ON;` を実行する
- 真偽値は `INTEGER` の `0` / `1` で扱う
- 日時は `TEXT` に `CURRENT_TIMESTAMP` で保存する
- 初回選択した自治体IDは、DBではなく `localStorage`、Flaskセッション、またはローカル設定ファイルで管理する
- 初期版では利用者個人を管理するテーブルは作成しない
- マスタデータは基本的に物理削除せず、必要に応じて将来の論理削除を検討する
- 画像ファイル本体はDBに保存しない
- Publicリポジトリに学習画像や保存画像をコミットしない

主要index:

```sql
CREATE INDEX idx_municipality_prefecture ON municipality(prefecture_id);
CREATE INDEX idx_garbage_rule_municipality ON garbage_rule(municipality_id);
CREATE INDEX idx_garbage_rule_garbage ON garbage_rule(garbage_id);
CREATE INDEX idx_question_answer_rule ON question_answer(rule_id);
CREATE INDEX idx_info_answer_rule ON info_answer(rule_id);
CREATE INDEX idx_history_municipality ON history(municipality_id);
CREATE INDEX idx_history_created_at ON history(created_at);
CREATE INDEX idx_feedback_status ON feedback(status);
```

## 11. 初期データ例

### prefecture

| prefecture_id | prefecture_name |
|---|---|
| 1 | 愛知県 |

### municipality

| municipality_id | prefecture_id | municipality_name |
|---|---|---|
| 1 | 1 | 名古屋市 |

### garbage_master

| garbage_id | garbage_name | yolo_label | description |
|---|---|---|---|
| 1 | ペットボトル | plastic_bottle | 飲料用ペットボトル |
| 2 | 乾電池 | battery | 乾電池 |
| 3 | 紙くず | paper | 紙類のごみ |

### garbage_type

| garbage_type_id | type_name | description |
|---|---|---|
| 1 | 可燃ごみ | 燃えるごみ |
| 2 | 不燃ごみ | 燃えないごみ |
| 3 | 資源ごみ | リサイクル可能なごみ |
| 4 | 粗大ごみ | 大型のごみ |
| 5 | 有害ごみ | 電池・スプレー缶など注意が必要なごみ |

### garbage_rule

| rule_id | municipality_id | garbage_id | garbage_type_id | guide_text | need_question |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 3 | キャップとラベルを外して、資源ごみとして出してください。 | 1 |
| 2 | 1 | 2 | 5 | 回収ボックスまたは有害ごみとして出してください。 | 0 |
| 3 | 1 | 3 | 1 | 可燃ごみとして出してください。 | 0 |

### question_type

| question_type_id | question_text |
|---|---|
| 1 | 汚れていますか？ |
| 2 | 中身は残っていますか？ |

### question_answer

| answer_id | rule_id | question_type_id | question_order | answer_value | result_garbage_type_id | result_guide_text |
|---|---|---|---|---|---|---|
| 1 | 1 | 1 | 1 | はい | 1 | 汚れている場合は、可燃ごみとして出してください。 |
| 2 | 1 | 1 | 1 | いいえ | 3 | キャップとラベルを外して、資源ごみとして出してください。 |

### info_question_type

| info_question_type_id | question_text |
|---|---|
| 1 | 注意事項はありますか？ |
| 2 | いつ出せますか？ |
| 3 | どこに出せますか？ |
| 4 | 他のごみとして捨てられますか？ |

### info_answer

| info_answer_id | rule_id | info_question_type_id | answer_text |
|---|---|---|---|
| 1 | 1 | 1 | キャップとラベルを外し、中を軽くすすいでください。 |
| 2 | 1 | 2 | 資源ごみの収集日に出してください。 |
| 3 | 1 | 3 | 指定された資源ごみの回収場所に出してください。 |
| 4 | 1 | 4 | 汚れがひどい場合は可燃ごみとして出してください。 |

### history

| history_id | municipality_id | detected_label | confidence | result_status | image_save_consent | image_saved | result_guide_text | created_at |
|---|---|---|---|---|---|---|---|---|
| 1 | 1 | plastic_bottle | 0.92 | success | 1 | 1 | キャップとラベルを外して、資源ごみとして出してください。 | 2026-07-03 13:00:00 |

### history_question_answer

| history_question_answer_id | history_id | question_order | question_text | answer_value |
|---|---|---|---|---|
| 1 | 1 | 1 | 汚れていますか？ | いいえ |

### feedback

| feedback_id | history_id | municipality_id | input_garbage_name | comment | status | created_at |
|---|---|---|---|---|---|---|
| 1 | 1 | 1 | ぬいぐるみ | 判定できなかったので追加してほしいです。 | open | 2026-07-03 13:05:00 |

## 12. 今後の拡張予定

将来的には、以下の拡張を検討する。

- 複数ごみの同時認識への対応
- 自治体ごとの収集曜日の管理
- ごみ分類ごとの色やアイコン管理
- 管理画面から分別ルールを編集する機能
- `feedback` をもとにした学習データ追加
- 判定結果画面の3段階フィードバックを保存する評価用テーブルの追加
- TTSの読み上げ速度や音量設定
