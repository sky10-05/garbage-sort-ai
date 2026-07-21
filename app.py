from pathlib import Path
import logging
import os
import uuid

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from ai import model as yolo_model
from database import repository


CONFIDENCE_THRESHOLD = 0.70
MAX_RETRY_COUNT = 3
MAX_CANDIDATES = 3
HISTORY_DISPLAY_LIMIT = 2
MAX_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "sample_images"

MOCK_RESULT = {
    "label": "plastic_bottle",
    "display_name": "ペットボトル",
    "confidence": 0.92,
}
USE_MOCK_INFERENCE = os.environ.get("USE_MOCK_INFERENCE", "0") == "1"


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-session-key")
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE
logging.basicConfig(level=logging.INFO)


@app.before_request
def prepare_database() -> None:
    repository.ensure_seed_data()


@app.route("/")
def root():
    return redirect(url_for("select_municipality"))


@app.route("/municipality", methods=["GET", "POST"])
def select_municipality():
    if request.method == "POST":
        municipality_id = request.form.get("municipality_id", type=int)
        if municipality_id is None:
            return render_error("自治体を選択してください。", "municipality_not_selected")

        municipality = repository.get_municipality(municipality_id)
        if municipality is None:
            app.logger.warning("Unknown municipality_id: %s", municipality_id)
            return render_error("選択した自治体が見つかりません。", "municipality_not_found")

        session["municipality_id"] = municipality_id
        session["voice_enabled"] = request.form.get("voice_enabled") == "on"
        session["retry_count"] = 0
        return redirect(url_for("capture"))

    municipalities = repository.fetch_municipalities()
    return render_template("select_municipality.html", municipalities=municipalities)


@app.route("/capture")
def capture():
    municipality = current_municipality()
    if municipality is None:
        return redirect(url_for("select_municipality"))
    return render_template(
        "index.html",
        mode="capture",
        municipality=municipality,
        voice_enabled=session.get("voice_enabled", True),
        threshold=CONFIDENCE_THRESHOLD,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings():
    municipality = current_municipality()
    if municipality is None:
        return redirect(url_for("select_municipality"))
    if request.method == "POST":
        session["voice_enabled"] = request.form.get("voice_enabled") == "on"
        return redirect(url_for("capture"))
    return render_template(
        "index.html",
        mode="settings",
        municipality=municipality,
        voice_enabled=session.get("voice_enabled", True),
    )


@app.route("/analyze", methods=["POST"])
def analyze():
    municipality = current_municipality()
    if municipality is None:
        return jsonify({"ok": False, "message": "自治体を選択してください。"}), 400

    uploaded_file = request.files.get("image")
    if uploaded_file is None:
        app.logger.warning("No image was uploaded.")
        return jsonify({"ok": False, "message": "画像が送信されていません。"}), 400

    validation_error = validate_image(uploaded_file)
    if validation_error:
        app.logger.warning("Image validation failed: %s", validation_error)
        return jsonify({"ok": False, "message": validation_error}), 400

    image_save_consent = request.form.get("image_save_consent") == "true"
    confidence = request.form.get("confidence", type=float)
    retry_count = request.form.get("retry_count", type=int)
    if retry_count is None:
        retry_count = session.get("retry_count", 0)

    image_path = save_temp_image(uploaded_file)
    try:
        detection_result = get_detection_result(image_path, confidence)
    except yolo_model.ModelLoadError:
        app.logger.exception("YOLO model could not be loaded.")
        cleanup_temp_image(image_path, image_save_consent)
        return jsonify({"ok": False, "message": "AI判定モデルを読み込めませんでした。"}), 500
    except yolo_model.InferenceError:
        app.logger.exception("YOLO inference failed.")
        cleanup_temp_image(image_path, image_save_consent)
        return jsonify({"ok": False, "message": "AI判定に失敗しました。もう一度撮影してください。"}), 500

    if detection_result["confidence"] < CONFIDENCE_THRESHOLD:
        retry_count += 1
        session["retry_count"] = retry_count
        cleanup_temp_image(image_path, image_save_consent)
        if retry_count >= MAX_RETRY_COUNT:
            candidates = [dict(row) for row in repository.fetch_candidates(MAX_CANDIDATES)]
            repository.save_feedback(
                municipality["municipality_id"],
                detection_result["label"],
                "信頼度不足により候補表示へ遷移しました。",
            )
            return jsonify(
                {
                    "ok": True,
                    "status": "candidates",
                    "message": "判定に必要な情報が不足しています。候補から選択してください。",
                    "candidates": candidates,
                    "retry_count": retry_count,
                }
            )
        return jsonify(
            {
                "ok": True,
                "status": "retry",
                "message": "判定に必要な情報が不足しています。もう一度撮影してください。",
                "retry_count": retry_count,
            }
        )

    session["retry_count"] = 0
    garbage = repository.get_garbage_by_label(detection_result["label"])
    if garbage is None:
        cleanup_temp_image(image_path, image_save_consent)
        repository.save_feedback(municipality["municipality_id"], detection_result["label"], "DBに存在しないAIラベルです。")
        return jsonify({"ok": False, "message": "このごみは現在対応していません。"}), 404

    rule = repository.get_rule(municipality["municipality_id"], garbage["garbage_id"])
    if rule is None:
        cleanup_temp_image(image_path, image_save_consent)
        repository.save_feedback(municipality["municipality_id"], garbage["garbage_name"], "分別ルールが登録されていません。")
        return jsonify({"ok": False, "message": "選択中の自治体では分別ルールが登録されていません。"}), 404

    stored_image_path = str(image_path) if image_save_consent else None
    cleanup_temp_image(image_path, image_save_consent)
    question = repository.get_first_question(rule["rule_id"]) if rule["need_question"] else None

    if question:
        session["pending_result"] = build_pending_result(municipality, garbage, rule, detection_result, stored_image_path, image_save_consent)
        return jsonify({"ok": True, "status": "question", "url": url_for("question")})

    history_id = save_success_history(municipality, garbage, rule, detection_result, stored_image_path, image_save_consent)
    return jsonify({"ok": True, "status": "result", "url": url_for("result", history_id=history_id)})


@app.route("/question", methods=["GET", "POST"])
def question():
    municipality = current_municipality()
    pending = session.get("pending_result")
    if municipality is None or pending is None:
        return redirect(url_for("capture"))

    question_data = repository.get_first_question(pending["rule_id"])
    if question_data is None:
        app.logger.warning("No question data for rule_id=%s", pending["rule_id"])
        return render_error("質問データが登録されていません。", "question_not_found")

    if request.method == "POST":
        answer_id = request.form.get("answer_id", type=int)
        answer = repository.get_answer_for_rule(answer_id, pending["rule_id"]) if answer_id else None
        if answer is None:
            return render_error("回答を選択してください。", "answer_not_selected")

        pending["result_garbage_type_id"] = answer["result_garbage_type_id"]
        pending["result_guide_text"] = answer["result_guide_text"]
        pending["type_name"] = answer["type_name"]
        history_id = repository.save_history(pending)
        session.pop("pending_result", None)
        return redirect(url_for("result", history_id=history_id))

    return render_template(
        "index.html",
        mode="question",
        municipality=municipality,
        question=question_data,
        voice_enabled=session.get("voice_enabled", True),
    )


@app.route("/candidate/select", methods=["POST"])
def select_candidate():
    municipality = current_municipality()
    if municipality is None:
        return jsonify({"ok": False, "message": "自治体を選択してください。"}), 400

    garbage_id = request.form.get("garbage_id", type=int)
    garbage = repository.get_garbage(garbage_id) if garbage_id else None
    if garbage is None:
        return jsonify({"ok": False, "message": "候補のごみ情報が見つかりません。"}), 404

    rule = repository.get_rule(municipality["municipality_id"], garbage["garbage_id"])
    if rule is None:
        repository.save_feedback(municipality["municipality_id"], garbage["garbage_name"], "候補選択後の分別ルールが未登録です。")
        return jsonify({"ok": False, "message": "選択した候補の分別ルールが登録されていません。"}), 404

    result = {
        "label": garbage["yolo_label"],
        "display_name": garbage["garbage_name"],
        "confidence": None,
    }
    question_data = repository.get_first_question(rule["rule_id"]) if rule["need_question"] else None
    if question_data:
        session["pending_result"] = build_pending_result(
            municipality,
            garbage,
            rule,
            result,
            None,
            False,
            result_status="candidate_selected",
        )
        return jsonify({"ok": True, "status": "question", "url": url_for("question")})

    history_id = save_success_history(
        municipality,
        garbage,
        rule,
        result,
        None,
        False,
        result_status="candidate_selected",
    )
    return jsonify({"ok": True, "status": "result", "url": url_for("result", history_id=history_id)})


@app.route("/result/<int:history_id>")
def result(history_id: int):
    municipality = current_municipality()
    if municipality is None:
        return redirect(url_for("select_municipality"))
    history_item = repository.get_history(history_id)
    if history_item is None:
        return render_error("判定履歴が見つかりません。", "history_not_found")
    return render_template(
        "index.html",
        mode="result",
        municipality=municipality,
        result=history_item,
        voice_enabled=session.get("voice_enabled", True),
    )


@app.route("/detail/<int:history_id>")
def detail(history_id: int):
    municipality = current_municipality()
    if municipality is None:
        return redirect(url_for("select_municipality"))
    history_item = repository.get_history(history_id)
    if history_item is None:
        return render_error("判定履歴が見つかりません。", "history_not_found")
    info_answers = repository.fetch_info_answers(history_item["rule_id"]) if history_item["rule_id"] else []
    return render_template(
        "index.html",
        mode="detail",
        municipality=municipality,
        result=history_item,
        info_answers=info_answers,
        voice_enabled=session.get("voice_enabled", True),
    )


@app.route("/history")
def history():
    municipality = current_municipality()
    if municipality is None:
        return redirect(url_for("select_municipality"))
    histories = repository.fetch_latest_history(HISTORY_DISPLAY_LIMIT)
    return render_template("history.html", municipality=municipality, histories=histories)


def current_municipality():
    municipality_id = session.get("municipality_id")
    if municipality_id is None:
        return None
    return repository.get_municipality(municipality_id)


def validate_image(uploaded_file) -> str | None:
    if uploaded_file.mimetype not in ALLOWED_MIME_TYPES:
        return "対応していない画像形式です。JPEG、PNG、WebPを使用してください。"
    uploaded_file.stream.seek(0, 2)
    size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)
    if size > MAX_IMAGE_SIZE:
        return "画像サイズが大きすぎます。5MB以下の画像を使用してください。"
    return None


def save_temp_image(uploaded_file) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(secure_filename(uploaded_file.filename or "capture.png")).suffix or ".png"
    image_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    uploaded_file.save(image_path)
    return image_path


def cleanup_temp_image(image_path: Path, keep_image: bool) -> None:
    if keep_image:
        return
    try:
        image_path.unlink(missing_ok=True)
    except OSError:
        app.logger.exception("Failed to delete temporary image: %s", image_path)


def get_mock_result(confidence: float) -> dict:
    result = MOCK_RESULT.copy()
    result["confidence"] = confidence
    return result


def get_detection_result(image_path: Path, override_confidence: float | None = None) -> dict:
    if USE_MOCK_INFERENCE:
        return get_mock_result(override_confidence or MOCK_RESULT["confidence"])

    result = yolo_model.predict_image(image_path)
    if override_confidence is not None:
        result["confidence"] = override_confidence
    return result


def build_pending_result(municipality, garbage, rule, mock_result, image_path, image_save_consent, result_status="success"):
    return {
        "municipality_id": municipality["municipality_id"],
        "detected_garbage_id": garbage["garbage_id"],
        "detected_label": mock_result["label"],
        "confidence": mock_result["confidence"],
        "rule_id": rule["rule_id"],
        "result_garbage_type_id": rule["garbage_type_id"],
        "result_guide_text": rule["guide_text"],
        "image_save_consent": 1 if image_save_consent else 0,
        "image_saved": 1 if image_path else 0,
        "image_path": image_path,
        "result_status": result_status,
    }


def save_success_history(municipality, garbage, rule, mock_result, image_path, image_save_consent, result_status="success"):
    return repository.save_history(
        build_pending_result(municipality, garbage, rule, mock_result, image_path, image_save_consent, result_status)
    )


def render_error(message: str, code: str):
    app.logger.warning("%s: %s", code, message)
    return render_template("index.html", mode="error", message=message, error_code=code), 400


if __name__ == "__main__":
    app.run(debug=True)
