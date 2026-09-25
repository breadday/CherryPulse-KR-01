"use strict";

const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const {DraftImportError, exportActiveSymbolsCsv, parseSymbolImport} = require("./draft-import.js");

class Element {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.parentNode = null;
    this.value = "";
    this.textContent = "";
  }

  append(...children) {
    for (const child of children) child.parentNode = this;
    this.children.push(...children);
  }
  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }
  setAttribute(name, value) { this.attributes.set(name, value); }
  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }
  dispatch(name, event = {}) {
    for (const callback of this.listeners.get(name) || []) {
      callback({target: this, currentTarget: this, preventDefault() {}, ...event});
    }
  }
  async dispatchAsync(name, event = {}) {
    for (const callback of this.listeners.get(name) || []) {
      await callback({target: this, currentTarget: this, preventDefault() {}, ...event});
    }
  }
  reset() { this.value = ""; }
  click() { this.clicked = true; this.dispatch("click"); }
  remove() {
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((item) => item !== this);
  }
}

function descendants(element) {
  return element.children.flatMap((child) => [child, ...descendants(child)]);
}

function boardWithDraft(draft) {
  const ids = [
    "notice", "symbol-count", "active-filter", "archived-filter", "symbol-list",
    "bulk-import-form", "symbol-import-file", "export-symbols-json", "export-symbols-csv",
    "pattern-list", "symbol-form", "pattern-kind", "pattern-order-type", "threshold-label",
    "threshold-hint", "pattern-threshold", "pattern-name", "pattern-form",
    "symbol-input", "symbol-name", "symbol-source", "symbol-note",
  ];
  const elements = new Map(ids.map((id) => [id, new Element("div", id)]));
  const stored = new Map([["cherrypulse-board-draft-v1", JSON.stringify(draft)]]);
  const downloads = [];
  const revokedUrls = [];
  let downloadSequence = 0;
  class TestURL extends URL {}
  TestURL.createObjectURL = (blob) => {
    downloads.push(blob);
    return `blob:test-${++downloadSequence}`;
  };
  TestURL.revokeObjectURL = (url) => revokedUrls.push(url);
  const document = {
    body: new Element("body"),
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element("div", id));
      return elements.get(id);
    },
    createElement(tagName) { return new Element(tagName); },
  };
  let sequence = 0;
  const context = {
    document,
    localStorage: {
      getItem(key) { return stored.get(key) ?? null; },
      setItem(key, value) { stored.set(key, value); },
    },
    crypto: {randomUUID: () => `generated-${++sequence}`},
    CherryPulseDraftImport: require("./draft-import.js"),
    URL: TestURL,
    Blob: class {
      constructor(parts, options) { this.content = parts.join(""); this.type = options.type; }
    },
    setTimeout(callback) { callback(); return 0; },
    Event: class { constructor(type) { this.type = type; } },
  };
  const source = readFileSync(path.join(__dirname, "board.js"), "utf8");
  vm.runInNewContext(source, context, {filename: "board.js"});
  return {
    getElement: (id) => elements.get(id),
    getDraft: () => JSON.parse(stored.get("cherrypulse-board-draft-v1")),
    getDownloads: () => downloads,
    getRevokedUrls: () => revokedUrls,
  };
}

test("pattern edits append a new version and preserve existing symbol bindings", () => {
  const fixture = boardWithDraft({
    symbols: [
      {code: "005930", name: "삼성전자", patternId: "pattern-a"},
      {code: "000660", name: "SK하이닉스", patternId: ""},
    ],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"}],
  });
  const patternCard = fixture.getElement("pattern-list").children[0];
  const form = descendants(patternCard).find((item) => item.className === "stack-form pattern-version-form");
  const fields = descendants(form);
  fields.find((item) => item.name === "name").value = "손절 조정";
  fields.find((item) => item.name === "threshold").value = "9700";
  fields.find((item) => item.name === "orderType").value = "MARKET";
  form.dispatch("submit");

  const draft = fixture.getDraft();
  assert.equal(draft.patterns.length, 2);
  assert.deepEqual(
    {...draft.patterns[0]},
    {id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"},
  );
  assert.deepEqual(
    {...draft.patterns[1]},
    {
      id: "generated-1", patternId: "pattern-a", version: 2, active: true,
      name: "손절 조정", kind: "PRICE_AT_OR_BELOW", threshold: "9700", orderType: "MARKET",
    },
  );
  assert.equal(draft.symbols[0].patternId, "pattern-a");
});

test("deactivation blocks new bindings but keeps a currently linked version visible", () => {
  const fixture = boardWithDraft({
    symbols: [
      {code: "005930", name: "삼성전자", patternId: "pattern-a"},
      {code: "000660", name: "SK하이닉스", patternId: ""},
    ],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"}],
  });
  const toggle = descendants(fixture.getElement("pattern-list").children[0])
    .find((item) => item.className === "pattern-toggle");
  toggle.dispatch("click");

  const draft = fixture.getDraft();
  assert.equal(draft.patterns[0].active, false);
  assert.equal(draft.symbols[0].patternId, "pattern-a");
  const symbolCards = fixture.getElement("symbol-list").children;
  const linkedSelect = descendants(symbolCards[0]).find((item) => item.tagName === "select");
  const unlinkedSelect = descendants(symbolCards[1]).find((item) => item.tagName === "select");
  assert.equal(linkedSelect.value, "pattern-a");
  assert.equal(linkedSelect.children[1].disabled, false);
  assert.equal(unlinkedSelect.children[1].disabled, true);

  const inactiveCard = fixture.getElement("pattern-list").children[0];
  descendants(inactiveCard).find((item) => item.className === "pattern-toggle").dispatch("click");
  assert.equal(fixture.getDraft().patterns[0].active, true);
  const reactivatedSelect = descendants(fixture.getElement("symbol-list").children[1])
    .find((item) => item.tagName === "select");
  assert.equal(reactivatedSelect.children[1].disabled, false);
});

test("new versions require an explicit supported order type", () => {
  const fixture = boardWithDraft({
    symbols: [],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"}],
  });
  const form = descendants(fixture.getElement("pattern-list").children[0])
    .find((item) => item.className === "stack-form pattern-version-form");
  const fields = descendants(form);
  fields.find((item) => item.name === "name").value = "손절 조정";
  fields.find((item) => item.name === "threshold").value = "9700";
  const orderType = fields.find((item) => item.name === "orderType");
  form.dispatch("submit");
  assert.equal(fixture.getDraft().patterns.length, 1);
  assert.match(fixture.getElement("notice").textContent, /주문 방식을 확인/);

  orderType.value = "LIMIT";
  form.dispatch("submit");
  const draft = fixture.getDraft();
  assert.equal(draft.patterns.length, 2);
  assert.equal(draft.patterns[1].version, 2);
  assert.equal(draft.patterns[1].orderType, "LIMIT");
});

test("JSON and CSV imports normalize supported fields and preserve quoted CSV data", () => {
  const json = parseSymbolImport("watch.json", JSON.stringify([
    {code: "005930", name: " 삼성전자 ", source: "https://example.com/a", note: " memo "},
  ]));
  assert.deepEqual(json, [{
    code: "005930", name: "삼성전자", source: "https://example.com/a", note: "memo",
    patternId: "", archived: false,
  }]);

  const csv = parseSymbolImport(
    "watch.CSV",
    'name,note,code,source\r\n"SK, Inc.","line one\nline two",000660,https://example.com',
  );
  assert.deepEqual(csv, [{
    code: "000660", name: "SK, Inc.", source: "https://example.com/", note: "line one\nline two",
    patternId: "", archived: false,
  }]);

  const special = [{
    code: "000001", name: 'Name, "quoted"', source: "https://example.com", note: "first,\nsecond",
  }];
  const roundTrip = parseSymbolImport(
    "export.csv", exportActiveSymbolsCsv(special),
  );
  assert.equal(roundTrip[0].name, special[0].name);
  assert.equal(roundTrip[0].note, special[0].note);
});

test("bulk import applies all rows together and rejects duplicate codes without mutation", async () => {
  const fixture = boardWithDraft({
    symbols: [{code: "005930", name: "기존", patternId: "", archived: false}],
    patterns: [],
  });
  const fileInput = fixture.getElement("symbol-import-file");
  fileInput.files = [{
    name: "watch.csv", size: 64,
    async text() { return "code,name,source,note\n000660,SK하이닉스,,import\n035420,NAVER,,import"; },
  }];
  await fixture.getElement("bulk-import-form").dispatchAsync("submit");
  let draft = fixture.getDraft();
  assert.deepEqual(draft.symbols.map((item) => item.code), ["005930", "000660", "035420"]);
  assert.equal(fixture.getElement("notice").textContent.includes("2개 종목"), true);

  fileInput.files = [{
    name: "duplicate.json", size: 32,
    async text() { return '[{"code":"005930","name":"중복"}]'; },
  }];
  await fixture.getElement("bulk-import-form").dispatchAsync("submit");
  draft = fixture.getDraft();
  assert.deepEqual(draft.symbols.map((item) => item.code), ["005930", "000660", "035420"]);
  assert.match(fixture.getElement("notice").textContent, /중복된 종목코드/);
});

test("bulk import rejects unsupported fields, malformed CSV, and duplicate codes", () => {
  assert.throws(
    () => parseSymbolImport("bad.json", '[{"code":"005930","name":"A","patternId":"x"}]'),
    (error) => error instanceof DraftImportError && error.code === "IMPORT_FIELDS_INVALID",
  );
  assert.throws(
    () => parseSymbolImport("bad.csv", 'code,name\n005930,"unclosed'),
    (error) => error instanceof DraftImportError && error.code === "IMPORT_CSV_INVALID",
  );
  assert.throws(
    () => parseSymbolImport("dupe.json", '[{"code":"005930","name":"A"}]', [{code: "005930"}]),
    (error) => error instanceof DraftImportError && error.code === "IMPORT_DUPLICATE_SYMBOL",
  );
});

test("bulk import rejects oversized files before reading or changing the draft", async () => {
  const fixture = boardWithDraft({symbols: [], patterns: []});
  fixture.getElement("symbol-import-file").files = [{
    name: "large.json", size: 5 * 1024 * 1024 + 1,
    async text() { assert.fail("oversized file must not be read"); },
  }];
  await fixture.getElement("bulk-import-form").dispatchAsync("submit");
  assert.deepEqual(fixture.getDraft().symbols, []);
  assert.match(fixture.getElement("notice").textContent, /5 MiB 이하/);
});

test("symbol exports download only active symbol fields accepted by the import formats", () => {
  const fixture = boardWithDraft({
    symbols: [
      {code: "005930", name: "삼성전자", source: "https://example.com", note: "watch", patternId: "pattern-a"},
      {code: "000660", name: "보관", source: "", note: "archived", patternId: "", archived: true},
    ],
    patterns: [],
  });
  const jsonButton = fixture.getElement("export-symbols-json");
  const csvButton = fixture.getElement("export-symbols-csv");
  assert.equal(jsonButton.disabled, false);
  assert.equal(csvButton.disabled, false);
  jsonButton.click();

  assert.equal(fixture.getDownloads().length, 1);
  assert.equal(fixture.getDownloads()[0].type, "application/json;charset=utf-8");
  assert.deepEqual(JSON.parse(fixture.getDownloads()[0].content), [{
    code: "005930", name: "삼성전자", source: "https://example.com", note: "watch",
  }]);
  assert.equal(fixture.getRevokedUrls().length, 1);

  csvButton.click();
  assert.equal(fixture.getDownloads().length, 2);
  assert.equal(fixture.getDownloads()[1].type, "text/csv;charset=utf-8");
  assert.deepEqual(
    JSON.parse(JSON.stringify(parseSymbolImport("download.csv", fixture.getDownloads()[1].content))),
    [{code: "005930", name: "삼성전자", source: "https://example.com/", note: "watch", patternId: "", archived: false}],
  );
  assert.equal(fixture.getRevokedUrls().length, 2);

  const empty = boardWithDraft({symbols: [], patterns: []});
  assert.equal(empty.getElement("export-symbols-json").disabled, true);
  assert.equal(empty.getElement("export-symbols-csv").disabled, true);
});
