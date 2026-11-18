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

vm.runInNewContext(source, { publicWidget, window: {} });

const scan = publicWidget.registry.StorageBagScan;
const extractCode = scan._extractCode.bind(scan);

test("joins an OCR-split product code", () => {
    assert.equal(extractCode("ESTE 002", true), "ESTE002");
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
