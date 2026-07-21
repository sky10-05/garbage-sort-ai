from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "garbage_rules.db"
TARGET_YOLO_LABELS = (
    "plastic_bottle",
    "drink_can",
    "glass_bottle",
    "aerosol_can",
    "dry_battery",
)


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def ensure_seed_data() -> None:
    with get_connection() as connection:
        connection.execute("INSERT OR IGNORE INTO prefecture(prefecture_name) VALUES (?)", ("愛知県",))
        prefecture_id = connection.execute("SELECT prefecture_id FROM prefecture WHERE prefecture_name = ?", ("愛知県",)).fetchone()[0]
        connection.execute(
            "INSERT OR IGNORE INTO municipality(prefecture_id, municipality_name) VALUES (?, ?)",
            (prefecture_id, "名古屋市"),
        )
        municipality_id = connection.execute(
            "SELECT municipality_id FROM municipality WHERE municipality_name = ?",
            ("名古屋市",),
        ).fetchone()[0]

        garbage_types = [
            ("可燃ごみ", "燃えるごみ"),
            ("不燃ごみ", "燃えないごみ"),
            ("資源ごみ", "リサイクル可能なごみ"),
            ("有害ごみ", "電池・スプレー缶など注意が必要なごみ"),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO garbage_type(type_name, description) VALUES (?, ?)",
            garbage_types,
        )

        garbage_items = [
            ("ペットボトル", "plastic_bottle", "飲料用ペットボトル"),
            ("飲料缶", "drink_can", "アルミ缶・スチール缶などの飲料缶"),
            ("ガラスびん", "glass_bottle", "飲料・食品用のガラスびん"),
            ("スプレー缶", "aerosol_can", "金属製の加圧式エアゾール缶"),
            ("乾電池", "dry_battery", "単1形、単2形、単3形、単4形などの円筒形乾電池"),
            ("紙くず", "paper", "紙類のごみ"),
        ]
        connection.executemany(
            "INSERT OR IGNORE INTO garbage_master(garbage_name, yolo_label, description) VALUES (?, ?, ?)",
            garbage_items,
        )

        plastic_id = get_garbage_by_label("plastic_bottle", connection)["garbage_id"]
        can_id = get_garbage_by_label("drink_can", connection)["garbage_id"]
        glass_bottle_id = get_garbage_by_label("glass_bottle", connection)["garbage_id"]
        aerosol_id = get_garbage_by_label("aerosol_can", connection)["garbage_id"]
        battery_id = get_garbage_by_label("dry_battery", connection)["garbage_id"]
        paper_id = get_garbage_by_label("paper", connection)["garbage_id"]
        burnable_id = get_garbage_type_id("可燃ごみ", connection)
        resource_id = get_garbage_type_id("資源ごみ", connection)
        hazardous_id = get_garbage_type_id("有害ごみ", connection)

        connection.executemany(
            """
            INSERT OR IGNORE INTO garbage_rule(municipality_id, garbage_id, garbage_type_id, guide_text, note, need_question)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    municipality_id,
                    plastic_id,
                    resource_id,
                    "キャップとラベルを外し、中を軽くすすいで資源ごみに出してください。",
                    "汚れが落ちない場合は可燃ごみとして扱います。",
                    1,
                ),
                (
                    municipality_id,
                    can_id,
                    resource_id,
                    "中を空にして軽くすすぎ、資源ごみに出してください。",
                    "汚れが落ちない場合は不燃ごみとして扱う場合があります。",
                    0,
                ),
                (
                    municipality_id,
                    glass_bottle_id,
                    resource_id,
                    "キャップを外し、中を軽くすすいで資源ごみに出してください。",
                    "割れたびんは紙などで包み、不燃ごみとして扱う場合があります。",
                    0,
                ),
                (
                    municipality_id,
                    aerosol_id,
                    hazardous_id,
                    "中身を使い切り、自治体指定の方法でスプレー缶として出してください。",
                    "穴あけの要否は自治体の案内に従ってください。",
                    0,
                ),
                (
                    municipality_id,
                    battery_id,
                    hazardous_id,
                    "端子部分をテープで絶縁し、回収ボックスまたは有害ごみに出してください。",
                    "発火防止のため、端子を必ず絶縁してください。",
                    0,
                ),
                (
                    municipality_id,
                    paper_id,
                    burnable_id,
                    "可燃ごみとして出してください。",
                    "",
                    0,
                ),
            ],
        )

        connection.execute("INSERT OR IGNORE INTO question_type(question_text) VALUES (?)", ("汚れていますか？",))
        question_type_id = connection.execute(
            "SELECT question_type_id FROM question_type WHERE question_text = ?",
            ("汚れていますか？",),
        ).fetchone()[0]
        rule_id = get_rule(municipality_id, plastic_id, connection)["rule_id"]
        connection.executemany(
            """
            INSERT OR IGNORE INTO question_answer(
                rule_id, question_type_id, question_order, answer_value,
                result_garbage_type_id, result_guide_text, next_question_type_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (rule_id, question_type_id, 1, "はい", burnable_id, "汚れている場合は可燃ごみとして出してください。", None),
                (rule_id, question_type_id, 1, "いいえ", resource_id, "キャップとラベルを外して資源ごみに出してください。", None),
            ],
        )

        info_questions = ["注意事項はありますか？", "いつ出せますか？", "どこに出せますか？"]
        connection.executemany(
            "INSERT OR IGNORE INTO info_question_type(question_text) VALUES (?)",
            [(question,) for question in info_questions],
        )
        for question, answer in [
            ("注意事項はありますか？", "キャップとラベルを外し、中を軽くすすいでください。"),
            ("いつ出せますか？", "資源ごみの収集日に出してください。"),
            ("どこに出せますか？", "指定された資源ごみの回収場所に出してください。"),
        ]:
            info_question_type_id = connection.execute(
                "SELECT info_question_type_id FROM info_question_type WHERE question_text = ?",
                (question,),
            ).fetchone()[0]
            connection.execute(
                "INSERT OR IGNORE INTO info_answer(rule_id, info_question_type_id, answer_text) VALUES (?, ?, ?)",
                (rule_id, info_question_type_id, answer),
            )


def fetch_municipalities() -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT m.municipality_id, p.prefecture_name, m.municipality_name
            FROM municipality m
            JOIN prefecture p ON p.prefecture_id = m.prefecture_id
            ORDER BY p.prefecture_name, m.municipality_name
            """
        ).fetchall()


def get_municipality(municipality_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT m.municipality_id, p.prefecture_name, m.municipality_name
            FROM municipality m
            JOIN prefecture p ON p.prefecture_id = m.prefecture_id
            WHERE m.municipality_id = ?
            """,
            (municipality_id,),
        ).fetchone()


def get_garbage_by_label(label: str, connection: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    query = "SELECT * FROM garbage_master WHERE yolo_label = ?"
    if connection is not None:
        return connection.execute(query, (label,)).fetchone()
    with get_connection() as new_connection:
        return new_connection.execute(query, (label,)).fetchone()


def get_garbage(garbage_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM garbage_master WHERE garbage_id = ?",
            (garbage_id,),
        ).fetchone()


def get_garbage_type_id(type_name: str, connection: sqlite3.Connection) -> int:
    return connection.execute(
        "SELECT garbage_type_id FROM garbage_type WHERE type_name = ?",
        (type_name,),
    ).fetchone()[0]


def get_rule(municipality_id: int, garbage_id: int, connection: sqlite3.Connection | None = None) -> sqlite3.Row | None:
    query = """
        SELECT gr.*, gt.type_name
        FROM garbage_rule gr
        JOIN garbage_type gt ON gt.garbage_type_id = gr.garbage_type_id
        WHERE gr.municipality_id = ? AND gr.garbage_id = ?
    """
    params = (municipality_id, garbage_id)
    if connection is not None:
        return connection.execute(query, params).fetchone()
    with get_connection() as new_connection:
        return new_connection.execute(query, params).fetchone()


def get_first_question(rule_id: int) -> dict | None:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT qa.answer_id, qa.answer_value, qt.question_text, qa.question_order
            FROM question_answer qa
            JOIN question_type qt ON qt.question_type_id = qa.question_type_id
            WHERE qa.rule_id = ? AND qa.question_order = 1
            ORDER BY qa.answer_id
            """,
            (rule_id,),
        ).fetchall()
    if not rows:
        return None
    return {
        "question_text": rows[0]["question_text"],
        "question_order": rows[0]["question_order"],
        "total_questions": max(row["question_order"] for row in rows),
        "answers": rows,
    }


def get_answer(answer_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT qa.*, gt.type_name
            FROM question_answer qa
            LEFT JOIN garbage_type gt ON gt.garbage_type_id = qa.result_garbage_type_id
            WHERE qa.answer_id = ?
            """,
            (answer_id,),
        ).fetchone()


def get_answer_for_rule(answer_id: int, rule_id: int) -> sqlite3.Row | None:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT qa.*, gt.type_name
            FROM question_answer qa
            LEFT JOIN garbage_type gt ON gt.garbage_type_id = qa.result_garbage_type_id
            WHERE qa.answer_id = ? AND qa.rule_id = ?
            """,
            (answer_id, rule_id),
        ).fetchone()


def save_history(data: dict) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO history(
                municipality_id, detected_garbage_id, detected_label, confidence,
                rule_id, result_garbage_type_id, result_guide_text,
                image_save_consent, image_saved, image_path, result_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["municipality_id"],
                data.get("detected_garbage_id"),
                data["detected_label"],
                data.get("confidence"),
                data.get("rule_id"),
                data.get("result_garbage_type_id"),
                data.get("result_guide_text"),
                data.get("image_save_consent", 0),
                data.get("image_saved", 0),
                data.get("image_path"),
                data["result_status"],
            ),
        )
        return cursor.lastrowid


def save_feedback(municipality_id: int | None, input_garbage_name: str, comment: str, history_id: int | None = None) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO feedback(history_id, municipality_id, input_garbage_name, comment)
            VALUES (?, ?, ?, ?)
            """,
            (history_id, municipality_id, input_garbage_name, comment),
        )
        return cursor.lastrowid


def fetch_latest_history(limit: int = 2) -> list[sqlite3.Row]:
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT h.*, m.municipality_name, gm.garbage_name, gt.type_name
            FROM history h
            JOIN municipality m ON m.municipality_id = h.municipality_id
            LEFT JOIN garbage_master gm ON gm.garbage_id = h.detected_garbage_id
            LEFT JOIN garbage_type gt ON gt.garbage_type_id = h.result_garbage_type_id
            ORDER BY h.created_at DESC, h.history_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_candidates(limit: int = 3) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in TARGET_YOLO_LABELS)
    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT *
            FROM garbage_master
            WHERE yolo_label IN ({placeholders})
            ORDER BY garbage_id
            LIMIT ?
            """,
            (*TARGET_YOLO_LABELS, limit),
        ).fetchall()
