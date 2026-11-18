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

test("creates enhanced crops in upright and rotated orientations", async () => {
    const rotations = [];
    const cropBounds = [];
    let bitmapClosed = false;
    browserWindow.createImageBitmap = async () => ({
        width: 1000,
        height: 800,
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
    assert.deepEqual(rotations, [0, Math.PI / 2, (3 * Math.PI) / 2]);
    assert.deepEqual([cropBounds[2], cropBounds[4]], [[0, 100, 800, 800], [0, 100, 800, 800]]);
    assert.equal(bitmapClosed, true);
});
