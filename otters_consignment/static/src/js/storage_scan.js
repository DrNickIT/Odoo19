/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.StorageBagScan = publicWidget.Widget.extend({
    selector: ".o_storage_scan",

    events: {
        "click .o_storage_scan_camera": "_onCameraClick",
        "click .o_storage_scan_camera_capture": "_onCameraCapture",
        "click .o_storage_scan_camera_torch": "_onCameraTorch",
        "click .o_storage_scan_camera_cancel": "_onCameraCancel",
        "click .o_storage_scan_camera_choose": "_onCameraChoose",
        "keydown .o_storage_scan_camera_modal": "_onCameraModalKeydown",
        "change #storage_scan_image": "_onImageSelected",
        "click #storage_scan_confirm_move": "_onConfirmMove",
        "click #storage_scan_cancel_move": "_onCancelMove",
        "submit #storage_scan_form": "_onSubmit",
    },

    start: function () {
        this.scanTarget = null;
        this.workerPromise = null;
        this.cameraStream = null;
        this.cameraTrack = null;
        this.cameraTorchEnabled = false;
        this.cameraRequestId = 0;
        this.cameraReturnFocus = null;
        return this._super.apply(this, arguments);
    },

    destroy: function () {
        this.cameraRequestId++;
        this._stopCamera();
        return this._super.apply(this, arguments);
    },

    _onCameraClick: function (event) {
        this.scanTarget = event.currentTarget.dataset.target;
        this.cameraReturnFocus = event.currentTarget;
        const mediaDevices = window.navigator && window.navigator.mediaDevices;
        if (!mediaDevices || !mediaDevices.getUserMedia) {
            this._openImagePicker();
            return;
        }
        this._openCamera();
    },

    _openCamera: async function () {
        const modal = this.el.querySelector("#storage_scan_camera_modal");
        const video = this.el.querySelector("#storage_scan_camera_video");
        const loading = this.el.querySelector("#storage_scan_camera_loading");
        const requestId = ++this.cameraRequestId;
        loading.textContent = "Camera starten…";
        modal.classList.remove("d-none");
        loading.classList.remove("d-none");

        try {
            const stream = await window.navigator.mediaDevices.getUserMedia({
                video: { facingMode: { ideal: "environment" } },
                audio: false,
            });
            if (requestId !== this.cameraRequestId) {
                stream.getTracks().forEach((track) => track.stop());
                return;
            }
            this.cameraStream = stream;
            this._configureCameraTorch(stream.getVideoTracks()[0]);
            video.srcObject = stream;
            await video.play();
            loading.classList.add("d-none");
            this.el.querySelector(".o_storage_scan_camera_capture").focus();
        } catch (error) {
            if (requestId !== this.cameraRequestId) {
                return;
            }
            console.debug("Live camera niet beschikbaar; foto kiezen blijft mogelijk.", error);
            this._stopCamera();
            loading.textContent = "Camera niet beschikbaar. Geef cameratoegang of kies een foto.";
            loading.classList.remove("d-none");
            this.el.querySelector(".o_storage_scan_camera_choose").focus();
        }
    },

    _openImagePicker: function () {
        this.el.querySelector("#storage_scan_image").click();
    },

    _configureCameraTorch: function (track) {
        const button = this.el.querySelector(".o_storage_scan_camera_torch");
        const status = this.el.querySelector("#storage_scan_camera_torch_status");
        const capabilities = track && track.getCapabilities ? track.getCapabilities() : {};
        this.cameraTrack =
            capabilities.torch && typeof track.applyConstraints === "function" ? track : null;
        this.cameraTorchEnabled = false;
        button.textContent = "Lamp aan";
        button.setAttribute("aria-pressed", "false");
        button.classList.add("d-none");
        status.textContent = "";
        status.classList.add("d-none");
        if (this.cameraTrack) {
            button.classList.remove("d-none");
        }
    },

    _onCameraTorch: async function () {
        if (!this.cameraTrack) {
            return;
        }
        const button = this.el.querySelector(".o_storage_scan_camera_torch");
        const status = this.el.querySelector("#storage_scan_camera_torch_status");
        const enabled = !this.cameraTorchEnabled;
        try {
            await this.cameraTrack.applyConstraints({ advanced: [{ torch: enabled }] });
        } catch (error) {
            console.warn("Cameralamp kon niet worden gewijzigd.", error);
            status.textContent = "De cameralamp kon niet worden bediend. Gebruik extra licht.";
            status.classList.remove("d-none");
            return;
        }
        this.cameraTorchEnabled = enabled;
        button.textContent = enabled ? "Lamp uit" : "Lamp aan";
        button.setAttribute("aria-pressed", String(enabled));
        status.textContent = "";
        status.classList.add("d-none");
    },

    _stopCamera: function () {
        if (this.cameraStream) {
            this.cameraStream.getTracks().forEach((track) => track.stop());
            this.cameraStream = null;
        }
        this.cameraTrack = null;
        this.cameraTorchEnabled = false;
        const torchButton = this.el.querySelector(".o_storage_scan_camera_torch");
        if (torchButton) {
            torchButton.textContent = "Lamp aan";
            torchButton.setAttribute("aria-pressed", "false");
            torchButton.classList.add("d-none");
        }
        const torchStatus = this.el.querySelector("#storage_scan_camera_torch_status");
        if (torchStatus) {
            torchStatus.textContent = "";
            torchStatus.classList.add("d-none");
        }
        const video = this.el.querySelector("#storage_scan_camera_video");
        if (video) {
            video.pause();
            video.srcObject = null;
        }
    },

    _closeCamera: function () {
        this.cameraRequestId++;
        this._stopCamera();
        this.el.querySelector("#storage_scan_camera_loading").textContent = "Camera starten…";
        this.el.querySelector("#storage_scan_camera_modal").classList.add("d-none");
        if (this.cameraReturnFocus) {
            this.cameraReturnFocus.focus();
        }
    },

    _onCameraCapture: async function () {
        const video = this.el.querySelector("#storage_scan_camera_video");
        if (!video.videoWidth || !video.videoHeight) {
            this._showStatus("Wacht tot de camera klaar is en probeer opnieuw.", "info");
            return;
        }

        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext("2d");
        if (!context) {
            this._showStatus("De camerafoto kon niet worden verwerkt. Kies een foto.", "danger");
            return;
        }
        let blob;
        try {
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
        } catch (error) {
            console.error("Camerafoto maken is mislukt:", error);
            this._showStatus("De foto kon niet worden vastgelegd. Probeer opnieuw.", "danger");
            return;
        }
        if (!blob) {
            this._showStatus("De camerafoto kon niet worden opgeslagen. Probeer opnieuw.", "danger");
            return;
        }

        const file = new File([blob], `storage-scan-${Date.now()}.jpg`, { type: "image/jpeg" });
        this._closeCamera();
        this._processImage(file);
    },

    _onCameraCancel: function () {
        this._closeCamera();
    },

    _onCameraChoose: function () {
        this._closeCamera();
        this._openImagePicker();
    },

    _onCameraModalKeydown: function (event) {
        if (event.key === "Escape") {
            event.preventDefault();
            this._closeCamera();
        }
    },

    _onImageSelected: async function () {
        const imageInput = this.el.querySelector("#storage_scan_image");
        const file = imageInput.files[0];
        if (!file || !this.scanTarget) {
            return;
        }

        try {
            await this._processImage(file);
        } finally {
            imageInput.value = "";
        }
    },

    _processImage: async function (file) {
        if (!file || !this.scanTarget) {
            return;
        }
        this._showStatus("Code herkennen…", "info");
        try {
            const value = await this._readCode(file, this.scanTarget === "storage_product_code");
            if (!value) {
                this._showStatus("Geen code herkend. Probeer opnieuw of typ de code zelf.", "warning");
                return;
            }
            const input = this.el.querySelector(`#${this.scanTarget}`);
            input.value = value;
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.focus();
            this._showStatus(`Herkende code: ${value}. Controleer de code en koppel daarna.`, "info");
        } catch (error) {
            console.error("Codeherkenning is mislukt:", error);
            this._showStatus("De code kon niet worden gelezen. Probeer opnieuw of typ de code zelf.", "danger");
        }
    },

    _readCode: async function (file, isProduct) {
        if (window.BarcodeDetector && window.createImageBitmap) {
            try {
                const detector = new window.BarcodeDetector();
                const bitmap = await window.createImageBitmap(file);
                const results = await detector.detect(bitmap);
                bitmap.close();
                if (results.length) {
                    return results[0].rawValue.trim().toUpperCase();
                }
            } catch (error) {
                console.debug("Barcodescanner niet beschikbaar voor deze foto; OCR wordt geprobeerd.", error);
            }
        }

        const worker = await this._getOcrWorker();
        if (!isProduct || !window.createImageBitmap) {
            const result = await worker.recognize(file);
            return this._extractCode(result.data.text, isProduct) || "";
        }

        const candidates = [];
        try {
            const crops = await this._createProductLabelCrops(file);
            for (const crop of crops) {
                const croppedResult = await worker.recognize(crop);
                const cropValue = this._extractCode(croppedResult.data.text, true);
                if (cropValue) {
                    candidates.push(cropValue);
                    if (this._isStrongProductCode(cropValue, croppedResult.data.confidence)) {
                        return cropValue;
                    }
                }
            }
        } catch (error) {
            console.debug("Label-crops konden niet worden herkend; gebruik de volledige foto.", error);
        }

        const result = await worker.recognize(file);
        const value = this._extractCode(result.data.text, true);
        if (value) {
            candidates.push(value);
        }
        return this._selectProductCode(candidates);
    },

    _extractCode: function (text, isProduct) {
        const normalizedText = text.toUpperCase().replace(
            /\b([IL])\s+(?=[A-Z]{1,4}\d{2,}\b)/g,
            "$1"
        );
        const tokenize = (line) => (line.match(/[A-Z0-9][A-Z0-9_-]*/g) || [])
            .map((token) => token.replace(/^[-_]+|[-_]+$/g, ""));
        if (!isProduct) {
            const candidates = tokenize(normalizedText);
            return candidates.find((token) => /^\d+$/.test(token)) || candidates[0] || "";
        }

        const pricePattern = /\b\d{1,4}[.,]\d{2}\b/g;
        const lines = normalizedText.split(/\r?\n/);
        for (const line of lines) {
            const mergedCodeAndPrice = line.match(/\b([A-Z]{2,}[FOZ]{3,})(\d{4})\b/);
            if (mergedCodeAndPrice) {
                const normalizedCode = this._normalizeOcrAlphaCode(mergedCodeAndPrice[1]);
                if (normalizedCode) {
                    return normalizedCode;
                }
            }

            const hasDecimalPrice = /\b\d{1,4}[.,]\d{2}\b/.test(line);
            const codeLine = line.replace(pricePattern, " ");
            const parts = tokenize(codeLine);
            const plainPriceIndex = parts.findIndex((part, index) => (
                /^\d{4}$/.test(part)
                && index > 0
                && this._normalizeOcrAlphaCode(parts[index - 1])
            ));
            const hasPrice = hasDecimalPrice || plainPriceIndex >= 0;
            const candidates = plainPriceIndex >= 0 ? parts.slice(0, plainPriceIndex) : parts;

            const exactCode = candidates.find((token) => /[A-Z]/.test(token) && /[0-9]/.test(token));
            if (exactCode) {
                return exactCode;
            }

            for (let index = 0; index < candidates.length - 1; index++) {
                const prefix = candidates[index];
                const suffix = candidates[index + 1];
                if (/^[A-Z][A-Z_-]*$/.test(prefix) && /^\d{1,3}$/.test(suffix)) {
                    return prefix + suffix;
                }
            }

            if (hasPrice) {
                const normalizedCode = this._normalizeOcrAlphaCode(candidates[0] || "");
                if (normalizedCode) {
                    return normalizedCode;
                }
            }

            const numericCode = candidates.find((token) => /^\d{6,}$/.test(token));
            if (numericCode) {
                return numericCode;
            }
        }
        return "";
    },

    _selectProductCode: function (candidates) {
        let bestCode = "";
        let bestScore = -Infinity;
        const candidateCounts = new Map();
        for (const candidate of candidates) {
            candidateCounts.set(candidate, (candidateCounts.get(candidate) || 0) + 1);
        }
        for (const [candidate, count] of candidateCounts) {
            const compact = candidate.replace(/[^A-Z0-9]/g, "");
            const letterCount = (compact.match(/[A-Z]/g) || []).length;
            const digitCount = (compact.match(/[0-9]/g) || []).length;
            const lengthScore = Math.max(0, 60 - Math.abs(compact.length - 7) * 6);
            const mixedCodeScore = letterCount && digitCount
                ? 10 + Math.min(letterCount, 3) + Math.min(digitCount, 3)
                : 0;
            const skuShapeScore = /^[A-Z]{2,}\d{2,}$/.test(compact) ? 12 : 0;
            const repeatScore = (count - 1) * 12;
            const score = lengthScore + mixedCodeScore + skuShapeScore + repeatScore;
            if (score > bestScore) {
                bestCode = candidate;
                bestScore = score;
            }
        }
        return bestCode;
    },

    _isStrongProductCode: function (candidate, confidence) {
        const compact = candidate.replace(/[^A-Z0-9]/g, "");
        return /^[A-Z]{2,}\d{2,}$/.test(compact)
            && compact.length >= 6
            && confidence >= 15;
    },

    _normalizeOcrAlphaCode: function (token) {
        const match = token.match(/^([A-Z]{2,}?)([FOZ]{3,})$/);
        if (!match) {
            return "";
        }
        // OCR can add an extra zero-like glyph to an all-letter digit suffix.
        const digitSuffix = match[2].replace(/[FO]/g, "0").replace(/Z/g, "2").replace(/0{3,}/g, "00");
        return match[1] + digitSuffix;
    },

    _createProductLabelCrops: async function (file) {
        const bitmap = await window.createImageBitmap(file);
        try {
            const rotations = bitmap.height > bitmap.width ? [270, 0, 90] : [0, 90, 270];
            return rotations.flatMap((degrees) => {
                const rotatedWidth = degrees % 180 ? bitmap.height : bitmap.width;
                const rotatedHeight = degrees % 180 ? bitmap.width : bitmap.height;
                const rotated = document.createElement("canvas");
                rotated.width = rotatedWidth;
                rotated.height = rotatedHeight;
                const rotatedContext = rotated.getContext("2d");
                if (!rotatedContext) {
                    return null;
                }
                rotatedContext.translate(rotatedWidth / 2, rotatedHeight / 2);
                rotatedContext.rotate(degrees * Math.PI / 180);
                rotatedContext.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);

                const createCrop = (sourceX, sourceY, sourceWidth, sourceHeight) => {
                    const scale = Math.min(1.5, 2400 / Math.max(sourceWidth, sourceHeight));
                    const crop = document.createElement("canvas");
                    crop.width = Math.round(sourceWidth * scale);
                    crop.height = Math.round(sourceHeight * scale);
                    const context = crop.getContext("2d");
                    if (!context) {
                        return null;
                    }
                    context.filter = "grayscale(1) contrast(1.4)";
                    context.drawImage(
                        rotated,
                        sourceX,
                        sourceY,
                        sourceWidth,
                        sourceHeight,
                        0,
                        0,
                        crop.width,
                        crop.height
                    );
                    return crop;
                };
                const crops = [
                    createCrop(
                        0,
                        0,
                        Math.round(rotatedWidth * 0.9),
                        Math.round(rotatedHeight * 0.7)
                    ),
                ].filter(Boolean);
                if (degrees === 90 || degrees === 270) {
                    const bandHeight = Math.round(rotatedHeight * 0.8);
                    const band = createCrop(
                        0,
                        Math.round(rotatedHeight * 0.1),
                        rotatedWidth,
                        bandHeight
                    );
                    if (band) {
                        crops.push(band);
                    }
                }
                return crops;
            }).filter(Boolean);
        } finally {
            bitmap.close();
        }
    },

    _getOcrWorker: function () {
        if (!this.workerPromise) {
            const base = "/otters_consignment/static/lib/tesseract/";
            this.workerPromise = window.Tesseract.createWorker("eng", 1, {
                workerPath: `${base}worker.min.js`,
                corePath: `${base}tesseract-core-simd-lstm.wasm.js`,
                langPath: `${base}tessdata/`,
                gzip: true,
                workerBlobURL: false,
            }).then(async (worker) => {
                await worker.setParameters({
                    tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.,",
                    tessedit_pageseg_mode: "11",
                });
                return worker;
            });
        }
        return this.workerPromise;
    },

    _onSubmit: function (event) {
        event.preventDefault();
        const form = event.currentTarget;
        if (!form.reportValidity()) {
            return;
        }
        this._submitForm(form);
    },

    _onConfirmMove: function (event) {
        event.preventDefault();
        this._submitForm(this.el.querySelector("#storage_scan_form"), true);
    },

    _onCancelMove: function (event) {
        event.preventDefault();
        this._showStatus("Verplaatsen geannuleerd.", "info");
    },

    _submitForm: async function (form, confirmMove = false) {
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        this._showStatus("Product opzoeken en koppelen…", "info");
        try {
            const formData = new FormData(form);
            formData.delete("confirm_move");
            if (confirmMove) {
                formData.set("confirm_move", "1");
            }
            const response = await fetch("/otters/storage/assign", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
                body: new URLSearchParams(formData),
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                if (result.needs_confirmation) {
                    this._showMoveConfirmation(result.message);
                    return;
                }
                this._showStatus(result.message || "Koppelen is mislukt.", "danger");
                return;
            }

            form.querySelector("#storage_product_code").value = "";
            this._showStatus(result.message, "success");
            form.querySelector("#storage_product_code").focus();
        } catch (error) {
            console.error("Product koppelen is mislukt:", error);
            this._showStatus("Odoo kon de koppeling niet opslaan. Controleer je verbinding en probeer opnieuw.", "danger");
        } finally {
            submitButton.disabled = false;
        }
    },

    _showMoveConfirmation: function (message) {
        const status = this.el.querySelector("#storage_scan_status");
        status.className = "alert alert-warning mt-3";
        status.replaceChildren(document.createTextNode(`${message} `));

        const confirmButton = document.createElement("button");
        confirmButton.id = "storage_scan_confirm_move";
        confirmButton.type = "button";
        confirmButton.className = "btn btn-warning btn-sm ms-2";
        confirmButton.textContent = "Ja, verplaatsen";

        const cancelButton = document.createElement("button");
        cancelButton.id = "storage_scan_cancel_move";
        cancelButton.type = "button";
        cancelButton.className = "btn btn-outline-secondary btn-sm ms-2";
        cancelButton.textContent = "Annuleren";

        status.append(confirmButton, cancelButton);
    },

    _showStatus: function (message, type) {
        const status = this.el.querySelector("#storage_scan_status");
        status.className = `alert alert-${type} mt-3`;
        status.textContent = message;
    },
});
