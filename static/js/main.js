const cameraPreview = document.getElementById("cameraPreview");
const captureCanvas = document.getElementById("captureCanvas");
const startCameraButton = document.getElementById("startCameraButton");
const captureForm = document.getElementById("captureForm");
const uploadImageInput = document.getElementById("uploadImageInput");
const uploadAnalyzeButton = document.getElementById("uploadAnalyzeButton");
const messageArea = document.getElementById("messageArea");
const candidateArea = document.getElementById("candidateArea");
const speakButton = document.getElementById("speakButton");
const actionButtons = [
    startCameraButton,
    captureForm?.querySelector("button[type='submit']"),
    uploadAnalyzeButton,
].filter(Boolean);

let mediaStream = null;
let retryCount = 0;
let isBusy = false;

function isVoiceEnabled() {
    return document.body.dataset.voiceEnabled === "true";
}

function stopSpeech() {
    if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
    }
}

async function startCamera() {
    if (!cameraPreview) return;
    try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        cameraPreview.srcObject = mediaStream;
        showMessage("カメラを起動しました。");
    } catch (error) {
        console.error("camera_denied", error);
        showMessage("カメラを使用できません。ブラウザの許可設定を確認してください。", true);
    }
}

function setBusy(nextBusy) {
    isBusy = nextBusy;
    actionButtons.forEach((button) => {
        button.disabled = nextBusy;
    });
    if (captureForm) {
        captureForm.setAttribute("aria-busy", nextBusy ? "true" : "false");
    }
}

function captureImage() {
    if (!cameraPreview || !captureCanvas || !cameraPreview.videoWidth) {
        throw new Error("カメラ映像がありません。");
    }
    captureCanvas.width = cameraPreview.videoWidth;
    captureCanvas.height = cameraPreview.videoHeight;
    const context = captureCanvas.getContext("2d");
    context.drawImage(cameraPreview, 0, 0, captureCanvas.width, captureCanvas.height);
    return new Promise((resolve) => {
        captureCanvas.toBlob((blob) => resolve(blob), "image/png");
    });
}

async function submitCapture(event) {
    event.preventDefault();
    if (isBusy) return;
    stopSpeech();
    setBusy(true);
    showMessage("判定中です。少しお待ちください。");
    try {
        const blob = await captureImage();
        if (!blob) {
            showMessage("画像を撮影できませんでした。", true);
            return;
        }

        await submitImage(blob, "capture.png");
    } catch (error) {
        console.error("capture_failed", error);
        showMessage(error.message || "画像送信に失敗しました。", true);
    } finally {
        setBusy(false);
    }
}

async function submitUpload() {
    if (isBusy) return;
    stopSpeech();
    const file = uploadImageInput?.files?.[0];
    if (!file) {
        showMessage("判定する画像を選択してください。", true);
        return;
    }
    setBusy(true);
    showMessage("選択した画像を判定中です。少しお待ちください。");
    try {
        await submitImage(file, file.name);
    } finally {
        setBusy(false);
    }
}

async function submitImage(image, filename) {
    const formData = new FormData();
    formData.append("image", image, filename);
    formData.append("retry_count", String(retryCount));
    formData.append("image_save_consent", document.getElementById("imageSaveConsent").checked ? "true" : "false");

    const response = await fetch("/analyze", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok || !data.ok) {
        showMessage(data.message || "判定処理に失敗しました。", true);
        return;
    }

    if (data.status === "retry") {
        retryCount = data.retry_count;
        showMessage(data.message, true);
        return;
    }
    if (data.status === "candidates") {
        retryCount = data.retry_count;
        showCandidates(data.candidates, data.message);
        return;
    }
    if (data.url) {
        window.location.href = data.url;
    }
}

function showMessage(message, isError = false) {
    if (!messageArea) return;
    messageArea.textContent = message;
    messageArea.className = isError ? "message-area error-text" : "message-area";
}

function showCandidates(candidates, message) {
    showMessage(message, true);
    if (!candidateArea) return;
    candidateArea.innerHTML = "";
    candidates.forEach((candidate) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "candidate-item";
        item.textContent = `${candidate.garbage_name} (${candidate.yolo_label})`;
        item.addEventListener("click", () => selectCandidate(candidate.garbage_id));
        candidateArea.appendChild(item);
    });
}

async function selectCandidate(garbageId) {
    if (isBusy) return;
    stopSpeech();
    setBusy(true);
    showMessage("選択した候補で案内を作成しています。");
    try {
        const formData = new FormData();
        formData.append("garbage_id", String(garbageId));
        const response = await fetch("/candidate/select", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showMessage(data.message || "候補の選択に失敗しました。", true);
            return;
        }
        if (data.url) {
            window.location.href = data.url;
        }
    } catch (error) {
        console.error("candidate_select_failed", error);
        showMessage("候補の選択に失敗しました。", true);
    } finally {
        setBusy(false);
    }
}

function speakText(text) {
    if (!window.speechSynthesis) return;
    if (!isVoiceEnabled()) {
        stopSpeech();
        return;
    }
    try {
        stopSpeech();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "ja-JP";
        window.speechSynthesis.speak(utterance);
    } catch (error) {
        console.error("speech_failed", error);
    }
}

if (startCameraButton) {
    startCameraButton.addEventListener("click", startCamera);
}

if (captureForm) {
    captureForm.addEventListener("submit", submitCapture);
}

if (uploadAnalyzeButton) {
    uploadAnalyzeButton.addEventListener("click", submitUpload);
}

if (speakButton) {
    const speechText = document.querySelector(".result-panel")?.dataset.speechText;
    speakButton.addEventListener("click", () => speakText(speechText || ""));
}

if (!isVoiceEnabled()) {
    stopSpeech();
}

window.addEventListener("pagehide", stopSpeech);
window.addEventListener("beforeunload", stopSpeech);
