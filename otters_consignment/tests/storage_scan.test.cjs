const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const sourcePath = path.join(__dirname, "..", "static", "src", "js", "storage_scan.js");
const source = fs.readFileSync(sourcePath, "utf8")
    .replace(/^import publicWidget from .*;\r?\n/m, "");
const publicWidget = {
    registry: {},
    Widget: {
        extend: (definition) => definition,
    },
};
const browserWindow = {};
const sandbox = { publicWidget, window: browserWindow };

vm.runInNewContext(source, sandbox);

const scan = publicWidget.registry.StorageBagScan;
const extractCode = scan._extractCode.bind(scan);

test("joins an OCR-split product code", () => {
    assert.equal(extractCode("ESTE 002", true), "ESTE002");
    assert.equal(extractCode("IBU 199", true), "IBU199");
    assert.equal(extractCode("CVE 104", true), "CVE104");
    assert.equal(extractCode("I BU199", true), "IBU199");
    assert.equal(extractCode("I\nBU199", true), "IBU199");
});

test("normalizes an OCR-confused code and excludes the price", () => {
    assert.equal(extractCode("ESTEFOOZ 12.50", true), "ESTE002");
    assert.equal(extractCode("ESTEFOOZ 12,50", true), "ESTE002");
    assert.equal(extractCode("ESTEFOOZ 7250", true), "ESTE002");
    assert.equal(extractCode("ESTEFOOZ7250", true), "ESTE002");
});

test("preserves ordinary product codes", () => {
    assert.equal(extractCode("THO-1234 12.50", true), "THO-1234");
    assert.equal(extractCode("SKU123", true), "SKU123");
});

test("prefers a plausible product code over rotation OCR noise", () => {
    assert.equal(
        scan._selectProductCode(["R8", "N7W", "J9WJ1YS-12311", "IBU199"]),
        "IBU199"
    );
    assert.equal(
        scan._selectProductCode(["91T1-1EN", "IBU199", "IBU199"]),
        "IBU199"
    );
    assert.equal(scan._selectProductCode(["R8"]), "R8");
    assert.equal(scan._isStrongProductCode("IBU199", 15), true);
    assert.equal(scan._isStrongProductCode("FE911", 100), false);
    assert.equal(scan._isStrongProductCode("91T1-1EN", 100), false);
});

test("returns a confident crop result without OCRing the full photo", async () => {
    const previousCreateImageBitmap = browserWindow.createImageBitmap;
    browserWindow.createImageBitmap = async () => {};
    const recognized = [];
    const instance = {
        _getOcrWorker: async () => ({
            recognize: async (image) => {
                recognized.push(image);
                return { data: { text: "CVE104", confidence: 21 } };
            },
        }),
        _createProductLabelCrops: async () => ["first crop", "second crop"],
        _extractCode: scan._extractCode.bind(scan),
        _isStrongProductCode: scan._isStrongProductCode.bind(scan),
        _selectProductCode: scan._selectProductCode.bind(scan),
    };

    try {
        assert.equal(await scan._readCode.call(instance, "photo", true), "CVE104");
        assert.deepEqual(recognized, ["first crop"]);
    } finally {
        browserWindow.createImageBitmap = previousCreateImageBitmap;
    }
});

test("configures Tesseract for sparse product-label text", async () => {
    let parameters;
    const worker = {
        setParameters: async (value) => {
            parameters = value;
        },
    };
    browserWindow.Tesseract = {
        createWorker: async () => worker,
    };

    const instance = { workerPromise: null };
    assert.equal(await scan._getOcrWorker.call(instance), worker);
    assert.equal(parameters.tessedit_pageseg_mode, "11");
});

test("opens the rear camera and releases it when the preview closes", async () => {
    const previousNavigator = browserWindow.navigator;
    let constraints;
    let trackStopped = false;
    let modalVisible = false;
    let loadingVisible = false;
    let focused = false;
    let torchVisible = false;
    let torchPressed = "false";
    let torchText = "Lamp aan";
    let torchStatusVisible = false;
    const torchConstraints = [];
    const video = {
        srcObject: null,
        play: async () => {},
        pause: () => {},
    };
    const track = {
        stop: () => { trackStopped = true; },
        getCapabilities: () => ({ torch: true }),
        applyConstraints: async (value) => { torchConstraints.push(value); },
    };
    const stream = {
        getTracks: () => [track],
        getVideoTracks: () => [track],
    };
    const modal = {
        classList: {
            remove: () => { modalVisible = true; },
            add: () => { modalVisible = false; },
        },
    };
    const loading = {
        textContent: "",
        classList: {
            remove: () => { loadingVisible = true; },
            add: () => { loadingVisible = false; },
        },
    };
    const torchButton = {
        classList: {
            add: () => { torchVisible = false; },
            remove: () => { torchVisible = true; },
        },
        get textContent() {
            return torchText;
        },
        set textContent(value) {
            torchText = value;
        },
        setAttribute: (name, value) => {
            if (name === "aria-pressed") {
                torchPressed = value;
            }
        },
    };
    const torchStatus = {
        textContent: "",
        classList: {
            add: () => { torchStatusVisible = false; },
            remove: () => { torchStatusVisible = true; },
        },
    };
    const instance = {
        cameraRequestId: 0,
        cameraStream: null,
        cameraTrack: null,
        cameraTorchEnabled: false,
        cameraReturnFocus: { focus: () => { focused = true; } },
        el: {
            querySelector: (selector) => ({
                "#storage_scan_camera_modal": modal,
                "#storage_scan_camera_video": video,
                "#storage_scan_camera_loading": loading,
                ".o_storage_scan_camera_torch": torchButton,
                "#storage_scan_camera_torch_status": torchStatus,
                ".o_storage_scan_camera_capture": { focus: () => {} },
            })[selector],
        },
    };
    instance._configureCameraTorch = scan._configureCameraTorch.bind(instance);
    instance._stopCamera = scan._stopCamera.bind(instance);
    browserWindow.navigator = {
        mediaDevices: {
            getUserMedia: async (value) => {
                constraints = value;
                return stream;
            },
        },
    };

    try {
        await scan._openCamera.call(instance);
        assert.equal(constraints.video.facingMode.ideal, "environment");
        assert.equal(constraints.audio, false);
        assert.equal(video.srcObject, stream);
        assert.equal(modalVisible, true);
        assert.equal(loadingVisible, false);
        assert.equal(torchVisible, true);

        await scan._onCameraTorch.call(instance);
        assert.equal(torchConstraints.length, 1);
        assert.equal(torchConstraints[0].advanced[0].torch, true);
        assert.equal(torchText, "Lamp uit");
        assert.equal(torchPressed, "true");
        assert.equal(torchStatusVisible, false);

        await scan._onCameraTorch.call(instance);
        assert.equal(torchConstraints.length, 2);
        assert.equal(torchConstraints[1].advanced[0].torch, false);
        assert.equal(torchText, "Lamp aan");
        assert.equal(torchPressed, "false");

        scan._closeCamera.call(instance);
        assert.equal(trackStopped, true);
        assert.equal(torchVisible, false);
        assert.equal(video.srcObject, null);
        assert.equal(modalVisible, false);
        assert.equal(focused, true);
    } finally {
        browserWindow.navigator = previousNavigator;
    }
});

test("keeps the torch control hidden when the camera does not support it", () => {
    let torchVisible = false;
    const torchButton = {
        textContent: "",
        classList: {
            add: () => { torchVisible = false; },
            remove: () => { torchVisible = true; },
        },
        setAttribute: () => {},
    };
    const torchStatus = {
        textContent: "",
        classList: { add: () => {}, remove: () => {} },
    };
    const instance = {
        cameraTrack: null,
        cameraTorchEnabled: false,
        el: {
            querySelector: (selector) => ({
                ".o_storage_scan_camera_torch": torchButton,
                "#storage_scan_camera_torch_status": torchStatus,
            })[selector],
        },
    };

    scan._configureCameraTorch.call(instance, { getCapabilities: () => ({}) });

    assert.equal(torchVisible, false);
    assert.equal(instance.cameraTrack, null);
});

test("creates enhanced crops in upright and rotated orientations", async () => {
    const rotations = [];
    const cropBounds = [];
    let bitmapClosed = false;
    browserWindow.createImageBitmap = async () => ({
        width: 800,
        height: 1000,
        close: () => {
            bitmapClosed = true;
        },
    });
    sandbox.document = {
        createElement: (tagName) => {
            assert.equal(tagName, "canvas");
            return {
                width: 0,
                height: 0,
                getContext: () => ({
                    translate: () => {},
                    rotate: (degrees) => rotations.push(degrees),
                    drawImage: (...args) => {
                        if (args.length === 9) {
                            cropBounds.push(args.slice(1, 5));
                        }
                    },
                }),
            };
        },
    };

    const crops = await scan._createProductLabelCrops({});

    assert.equal(crops.length, 5);
    assert.deepEqual(rotations, [(3 * Math.PI) / 2, 0, Math.PI / 2]);
    assert.deepEqual([cropBounds[1], cropBounds[4]], [[0, 80, 1000, 640], [0, 80, 1000, 640]]);
    assert.equal(bitmapClosed, true);
});
