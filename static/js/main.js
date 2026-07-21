const cameraPreview = document.getElementById("cameraPreview");
const captureCanvas = document.getElementById("captureCanvas");
const startCameraButton = document.getElementById("startCameraButton");
const captureForm = document.getElementById("captureForm");
const uploadImageInput = document.getElementById("uploadImageInput");
const uploadAnalyzeButton = document.getElementById("uploadAnalyzeButton");
const messageArea = document.getElementById("messageArea");
const candidateArea = document.getElementById("candidateArea");
const speakButton = document.getElementById("speakButton");

let mediaStream = null;
let retryCount = 0;

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
    }
}

async function submitUpload() {
    const file = uploadImageInput?.files?.[0];
    if (!file) {
        showMessage("判定する画像を選択してください。", true);
        return;
    }
    await submitImage(file, file.name);
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
        const item = document.createElement("div");
        item.className = "candidate-item";
        item.textContent = `${candidate.garbage_name} (${candidate.yolo_label})`;
        candidateArea.appendChild(item);
    });
}

function speakText(text) {
    const voiceEnabled = document.body.dataset.voiceEnabled === "true";
    if (!window.speechSynthesis) return;
    if (!voiceEnabled) {
        window.speechSynthesis.cancel();
        return;
    }
    try {
        window.speechSynthesis.cancel();
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
    if (speechText) {
        speakText(speechText);
    }
} else if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
}
