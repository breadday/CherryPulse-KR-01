"use strict";

const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const {DraftImportError, exportActiveSymbolsCsv, parseSymbolImport} = require("./draft-import.js");
const {
  BoardBackupError,
  parseBoardBackup,
  serializeBoardBackup,
} = require("./board-backup.js");

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
  reportValidity() { return true; }
  focus() { this.focused = true; }
  reset() { this.value = ""; }
  click() { this.clicked = true; this.dispatch("click"); }
  remove() {
    if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((item) => item !== this);
  }
}

function descendants(element) {
  return element.children.flatMap((child) => [child, ...descendants(child)]);
}

function boardWithDraft(draft, options = {}) {
  const ids = [
    "notice", "symbol-count", "active-filter", "archived-filter", "symbol-search", "symbol-list",
    "bulk-import-form", "symbol-import-file", "export-symbols-json", "export-symbols-csv",
    "export-board-backup", "restore-board-backup-form", "board-backup-file",
    "restore-confirmation", "restore-summary", "confirm-board-restore", "cancel-board-restore",
    "pattern-list", "symbol-form", "pattern-kind", "pattern-order-type", "threshold-label",
    "threshold-hint", "pattern-threshold", "pattern-name", "pattern-form",
    "symbol-input", "symbol-name", "symbol-source", "symbol-note",
    "buy-pattern-form", "buy-pattern-name", "buy-target-price", "buy-pattern-list",
  ];
  const elements = new Map(ids.map((id) => [id, new Element("div", id)]));
  const stored = new Map([["cherrypulse-board-draft-v1", JSON.stringify(draft)]]);
  const downloads = [];
  const revokedUrls = [];
  let failStorageWrites = false;
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
      const dynamic = [...elements.values()].flatMap((element) => descendants(element)).find((element) => element.id === id);
      if (dynamic) return dynamic;
      if (!elements.has(id)) elements.set(id, new Element("div", id));
      return elements.get(id);
    },
    createElement(tagName) { return new Element(tagName); },
  };
  let sequence = 0;
  const context = {
    document,
    ...(options.cloud ? {CherryPulseCloud: {createClient: () => options.cloud}, fetch: async () => {}} : {}),
    localStorage: {
      getItem(key) { return stored.get(key) ?? null; },
      setItem(key, value) {
        if (failStorageWrites) throw new Error("QUOTA_EXCEEDED");
        stored.set(key, value);
      },
    },
    crypto: options.withoutCrypto ? undefined : {randomUUID: () => `generated-${++sequence}`},
    CherryPulseDraftImport: require("./draft-import.js"),
    CherryPulseBoardBackup: require("./board-backup.js"),
    CherryPulseBuyPreview: require("./buy-preview.js"),
    URL: TestURL,
    Blob: class {
      constructor(parts, options) {
        this.content = parts.join("");
        this.type = options.type;
        this.size = Buffer.byteLength(this.content, "utf8");
      }
    },
    setTimeout(callback) { callback(); return 0; },
    Event: class { constructor(type) { this.type = type; } },
  };
  const source = readFileSync(path.join(__dirname, "board.js"), "utf8");
  vm.runInNewContext(source, context, {filename: "board.js"});
  return {
    getElement: (id) => elements.get(id),
    getDraft: () => JSON.parse(stored.get("cherrypulse-board-draft-v1")),
    setExternalDraft: (draft) => stored.set("cherrypulse-board-draft-v1", JSON.stringify(draft)),
    getDownloads: () => downloads,
    getRevokedUrls: () => revokedUrls,
    setStorageFailure: (value) => { failStorageWrites = value; },
  };
}

function sampleBoardBackup() {
  return {
    format: "cherrypulse-board-draft",
    schemaVersion: 1,
    symbols: [
      {
        code: "005930", name: "삼성전자", source: "https://example.com/stock",
        note: "active", patternId: "stop-v2", archived: false,
      },
      {
        code: "000660", name: "하이닉스", source: "", note: "archived",
        patternId: "stop-v1", archived: true,
      },
    ],
    patterns: [
      {
        id: "stop-v1", patternId: "stop-family", version: 1, active: false,
        name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800", orderType: "MARKET",
      },
      {
        id: "stop-v2", patternId: "stop-family", version: 2, active: true,
        name: "손절 조정", kind: "AVERAGE_COST_DROP", threshold: "0.02", orderType: "LIMIT",
      },
      {id: "legacy-pattern", name: "구버전", kind: "PRICE_AT_OR_BELOW", threshold: "9000"},
    ],
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

test("failed draft writes do not leak unsaved edits into a later successful write", () => {
  const original = {
    symbols: [{code: "005930", name: "삼성전자", patternId: "pattern-a", archived: false}],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"}],
  };
  const fixture = boardWithDraft(original);
  fixture.setStorageFailure(true);
  const symbolCard = fixture.getElement("symbol-list").children[0];
  const select = descendants(symbolCard).find((item) => item.tagName === "select");
  select.value = "";
  select.dispatch("change");
  assert.equal(select.value, "pattern-a");
  descendants(symbolCard).find((item) => item.className === "archive-button").click();
  descendants(fixture.getElement("pattern-list").children[0])
    .find((item) => item.className === "pattern-toggle").click();
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /기존 초안은 유지/);

  fixture.setStorageFailure(false);
  fixture.getElement("symbol-name").value = "SK하이닉스";
  fixture.getElement("symbol-input").value = "000660";
  fixture.getElement("symbol-form").dispatch("submit");
  const saved = fixture.getDraft();
  assert.equal(saved.symbols.length, 2);
  assert.deepEqual(saved.symbols[0], original.symbols[0]);
  assert.deepEqual(saved.patterns[0], original.patterns[0]);
});

test("a stale tab refuses to overwrite a draft saved by another tab", () => {
  const original = {symbols: [], patterns: []};
  const fixture = boardWithDraft(original);
  const updated = {
    symbols: [{code: "005930", name: "삼성전자", patternId: ""}], patterns: [],
  };
  fixture.setExternalDraft(updated);
  fixture.getElement("symbol-name").value = "SK하이닉스";
  fixture.getElement("symbol-input").value = "000660";
  fixture.getElement("symbol-form").dispatch("submit");
  assert.deepEqual(fixture.getDraft(), updated);
  assert.match(fixture.getElement("notice").textContent, /다른 탭.*새로고침/);
  assert.equal(fixture.getElement("symbol-list").children[0].textContent,
    "등록한 종목이 없습니다. 종목명을 검색해 추가하세요.");
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

test("symbol search covers code, name, link, and note while respecting active/archive filters", () => {
  const fixture = boardWithDraft({
    symbols: [
      {code: "005930", name: "삼성전자", source: "https://example.com/semiconductor", note: "메모리", archived: false},
      {code: "000660", name: "하이닉스", source: "", note: "HBM", archived: false},
      {code: "035420", name: "보관종목", source: "https://example.com/archive", note: "보관메모", archived: true},
    ],
    patterns: [],
  });
  const search = fixture.getElement("symbol-search");
  const visibleCodes = () => fixture.getElement("symbol-list").children
    .filter((item) => item.className === "card")
    .map((card) => descendants(card).find((item) => item.className === "symbol-code").textContent);

  for (const [query, expected] of [["005930", ["005930"]], ["하이닉스", ["000660"]], ["example.com/semiconductor", ["005930"]], ["hbm", ["000660"]]]) {
    search.value = query;
    search.dispatch("input");
    assert.deepEqual(visibleCodes(), expected);
  }

  search.value = "보관메모";
  search.dispatch("input");
  assert.deepEqual(visibleCodes(), []);
  fixture.getElement("archived-filter").dispatch("click");
  assert.deepEqual(visibleCodes(), ["035420"]);
  assert.match(fixture.getElement("symbol-count").textContent, /1개 표시/);
  search.value = "찾을수없음";
  search.dispatch("input");
  assert.match(fixture.getElement("symbol-list").children[0].textContent, /검색 결과가 없습니다/);
});

test("full backup serialization preserves archived symbols, all pattern revisions, and legacy fields", () => {
  const legacy = {
    format: "cherrypulse-board-draft",
    schemaVersion: 1,
    symbols: [{code: "123456", name: "legacy"}],
    patterns: [{id: "legacy", name: "legacy", kind: "PRICE_AT_OR_BELOW", threshold: "1"}],
  };
  const restored = parseBoardBackup(serializeBoardBackup(legacy));
  assert.deepEqual(restored, legacy);

  const modern = sampleBoardBackup();
  assert.deepEqual(parseBoardBackup(serializeBoardBackup({symbols: modern.symbols, patterns: modern.patterns})), modern);
});

test("full backup validation rejects unsupported versions, duplicate identities, invalid rules, and broken links", () => {
  const cases = [
    ["not json", "BACKUP_JSON_INVALID"],
    [JSON.stringify({...sampleBoardBackup(), format: "other"}), "BACKUP_FORMAT_UNSUPPORTED"],
    [JSON.stringify({...sampleBoardBackup(), schemaVersion: 2}), "BACKUP_SCHEMA_UNSUPPORTED"],
    [JSON.stringify({...sampleBoardBackup(), symbols: [...sampleBoardBackup().symbols, sampleBoardBackup().symbols[0]]}), "BACKUP_DUPLICATE_SYMBOL"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [...sampleBoardBackup().patterns, sampleBoardBackup().patterns[0]]}), "BACKUP_DUPLICATE_PATTERN_ID"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      ...sampleBoardBackup().patterns,
      {...sampleBoardBackup().patterns[1], id: "duplicate-revision"},
    ]}), "BACKUP_DUPLICATE_PATTERN_VERSION"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      {id: "legacy-family", name: "legacy", kind: "PRICE_AT_OR_BELOW", threshold: "9000"},
      {id: "new-revision", patternId: "legacy-family", version: 1, name: "v1", kind: "PRICE_AT_OR_BELOW", threshold: "9000"},
    ], symbols: []}), "BACKUP_DUPLICATE_PATTERN_VERSION"],
    [JSON.stringify({...sampleBoardBackup(), symbols: [
      {...sampleBoardBackup().symbols[0], patternId: "missing-pattern"},
    ]}), "BACKUP_PATTERN_LINK_MISSING"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      {...sampleBoardBackup().patterns[0], threshold: "0"},
    ], symbols: []}), "BACKUP_THRESHOLD_INVALID"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      {...sampleBoardBackup().patterns[0], orderType: "UNKNOWN"},
    ], symbols: []}), "BACKUP_ORDER_TYPE_INVALID"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      {...sampleBoardBackup().patterns[0], version: 1.5},
    ], symbols: []}), "BACKUP_PATTERN_REVISION_INVALID"],
    [JSON.stringify({...sampleBoardBackup(), patterns: [
      {...sampleBoardBackup().patterns[0], kind: "AVERAGE_COST_DROP", threshold: "1"},
    ], symbols: []}), "BACKUP_THRESHOLD_INVALID"],
  ];
  for (const [text, code] of cases) {
    assert.throws(
      () => parseBoardBackup(text),
      (error) => error instanceof BoardBackupError && error.code === code,
      code,
    );
  }
});

test("full backup restore requires confirmation, cancellation preserves state, and confirmed data survives reload", async () => {
  const oldDraft = {
    symbols: [{code: "111111", name: "현재 초안", patternId: "", archived: false}],
    patterns: [],
  };
  const expected = sampleBoardBackup();
  const fixture = boardWithDraft(oldDraft);
  fixture.getElement("export-board-backup").click();
  const downloaded = fixture.getDownloads()[0];
  assert.equal(downloaded.type, "application/json;charset=utf-8");
  assert.deepEqual(JSON.parse(downloaded.content), {
    ...expected,
    // The exporter serializes the supplied current draft; the UI fixture's state is used below.
    symbols: oldDraft.symbols,
    patterns: oldDraft.patterns,
  });

  const input = fixture.getElement("board-backup-file");
  input.files = [{name: "full-board.json", size: 1024, async text() { return JSON.stringify(expected); }}];
  await fixture.getElement("restore-board-backup-form").dispatchAsync("submit");
  assert.deepEqual(fixture.getDraft(), oldDraft);
  assert.equal(fixture.getElement("restore-confirmation").hidden, false);
  assert.match(fixture.getElement("restore-summary").textContent, /2개 종목.*손절 패턴 3개/);

  fixture.getElement("cancel-board-restore").click();
  assert.deepEqual(fixture.getDraft(), oldDraft);
  assert.equal(fixture.getElement("restore-confirmation").hidden, true);

  await fixture.getElement("restore-board-backup-form").dispatchAsync("submit");
  fixture.getElement("confirm-board-restore").click();
  assert.deepEqual(fixture.getDraft(), expected);
  assert.match(fixture.getElement("notice").textContent, /복원했습니다/);
  const reloaded = boardWithDraft(fixture.getDraft());
  assert.deepEqual(reloaded.getDraft(), expected);
});

test("invalid full backup and storage failure leave the existing draft untouched", async () => {
  const oldDraft = {
    symbols: [{code: "111111", name: "현재 초안", patternId: "", archived: false}],
    patterns: [],
  };
  const fixture = boardWithDraft(oldDraft);
  const input = fixture.getElement("board-backup-file");
  const restoreForm = fixture.getElement("restore-board-backup-form");
  input.files = [{name: "broken.json", size: 10, async text() { return "{}"; }}];
  await restoreForm.dispatchAsync("submit");
  assert.deepEqual(fixture.getDraft(), oldDraft);
  assert.equal(fixture.getElement("restore-confirmation").hidden, true);

  const invalidBackups = [
    {...sampleBoardBackup(), schemaVersion: 77},
    {
      ...sampleBoardBackup(),
      symbols: [...sampleBoardBackup().symbols, sampleBoardBackup().symbols[0]],
    },
    {
      ...sampleBoardBackup(),
      symbols: [{...sampleBoardBackup().symbols[0], patternId: "missing-pattern"}],
    },
  ];
  for (const invalidBackup of invalidBackups) {
    const text = JSON.stringify(invalidBackup);
    input.files = [{name: "invalid.json", size: Buffer.byteLength(text), async text() { return text; }}];
    await restoreForm.dispatchAsync("submit");
    assert.deepEqual(fixture.getDraft(), oldDraft);
    assert.equal(fixture.getElement("restore-confirmation").hidden, true);
    assert.equal(
      descendants(fixture.getElement("symbol-list").children[0])
        .find((item) => item.className === "symbol-code").textContent,
      "111111",
    );
  }

  input.files = [{
    name: "large.json", size: 10 * 1024 * 1024 + 1,
    async text() { assert.fail("oversized backup must not be read"); },
  }];
  await restoreForm.dispatchAsync("submit");
  assert.deepEqual(fixture.getDraft(), oldDraft);
  assert.match(fixture.getElement("notice").textContent, /10 MiB 이하/);

  input.files = [{name: "valid.json", size: 100, async text() { return JSON.stringify(sampleBoardBackup()); }}];
  await restoreForm.dispatchAsync("submit");
  fixture.setStorageFailure(true);
  fixture.getElement("confirm-board-restore").click();
  assert.deepEqual(fixture.getDraft(), oldDraft);
  assert.equal(
    descendants(fixture.getElement("symbol-list").children[0])
      .find((item) => item.className === "symbol-code").textContent,
    "111111",
  );
  assert.equal(fixture.getElement("restore-confirmation").hidden, false);
  assert.match(fixture.getElement("notice").textContent, /저장에 실패/);
  assert.doesNotMatch(fixture.getElement("notice").textContent, /복원했습니다/);
});

test("symbol forms reject overlong fields without changing the draft", () => {
  const original = {
    symbols: [{code: "005930", name: "삼성전자", source: "", note: "", patternId: "", archived: false}],
    patterns: [],
  };
  const fixture = boardWithDraft(structuredClone(original));
  const form = fixture.getElement("symbol-form");

  fixture.getElement("symbol-input").value = "000660";
  fixture.getElement("symbol-name").value = "가".repeat(101);
  fixture.getElement("symbol-source").value = "";
  fixture.getElement("symbol-note").value = "";
  form.dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /100자 이내/);

  fixture.getElement("symbol-name").value = "하이닉스";
  fixture.getElement("symbol-source").value = `https://example.com/${"p".repeat(2048)}`;
  form.dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /2048자 이내/);

  fixture.getElement("symbol-source").value = "";
  fixture.getElement("symbol-note").value = "메".repeat(1001);
  form.dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /1000자 이내/);

  const symbolCard = fixture.getElement("symbol-list").children[0];
  const editForm = descendants(symbolCard)
    .find((item) => item.className === "stack-form symbol-edit-form");
  const editFields = descendants(editForm);
  editFields.find((item) => item.name === "name").value = "나".repeat(101);
  editForm.dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /100자 이내/);
});

test("pattern forms reject overlong names without changing the draft", () => {
  const original = {
    symbols: [],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800", orderType: "MARKET"}],
  };
  const fixture = boardWithDraft(structuredClone(original));

  fixture.getElement("pattern-name").value = "패".repeat(101);
  fixture.getElement("pattern-kind").value = "PRICE_AT_OR_BELOW";
  fixture.getElement("pattern-threshold").value = "9700";
  fixture.getElement("pattern-order-type").value = "MARKET";
  fixture.getElement("pattern-form").dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /100자 이내/);

  const patternCard = fixture.getElement("pattern-list").children[0];
  const versionForm = descendants(patternCard)
    .find((item) => item.className === "stack-form pattern-version-form");
  const versionFields = descendants(versionForm);
  versionFields.find((item) => item.name === "name").value = "버".repeat(101);
  versionFields.find((item) => item.name === "threshold").value = "9700";
  versionFields.find((item) => item.name === "orderType").value = "MARKET";
  versionForm.dispatch("submit");
  assert.deepEqual(fixture.getDraft(), original);
  assert.match(fixture.getElement("notice").textContent, /100자 이내/);
});
test("restore refuses to overwrite a draft changed in another tab after validation", async () => {
  const oldDraft = {symbols: [{code: "111111", name: "기존"}], patterns: []};
  const newDraft = {symbols: [{code: "222222", name: "다른 탭 변경"}], patterns: []};
  const fixture = boardWithDraft(oldDraft);
  fixture.getElement("board-backup-file").files = [{
    size: 100, async text() { return JSON.stringify(sampleBoardBackup()); },
  }];
  await fixture.getElement("restore-board-backup-form").dispatchAsync("submit");
  fixture.setExternalDraft(newDraft);
  fixture.getElement("confirm-board-restore").click();
  assert.deepEqual(fixture.getDraft(), newDraft);
  assert.equal(fixture.getElement("restore-confirmation").hidden, true);
  assert.match(fixture.getElement("notice").textContent, /다시 검사/);
});

test("buy pattern form saves a fixed-spec local draft", () => {
  const fixture = boardWithDraft({symbols: [], patterns: []});
  fixture.getElement("buy-pattern-name").value = "돌파 매수";
  fixture.getElement("buy-target-price").value = "70000";
  fixture.getElement("buy-pattern-form").dispatch("submit");
  const draft = fixture.getDraft();
  assert.equal(draft.patterns.length, 1);
  assert.deepEqual(
    {...draft.patterns[0]},
    {
      id: "generated-1", patternId: "generated-1", version: 1, active: true,
      name: "돌파 매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "70000", orderType: "LIMIT",
    },
  );
  assert.match(fixture.getElement("notice").textContent, /엔진에는 적용되지 않습니다/);
  const buyCard = fixture.getElement("buy-pattern-list").children[0];
  assert.match(
    descendants(buyCard).find((item) => item.className === "pattern-detail").textContent,
    /70000원 이하 매수/,
  );
});

test("buy pattern form rejects invalid targets and names without mutation", () => {
  const original = {symbols: [], patterns: []};
  const fixture = boardWithDraft(structuredClone(original));
  const form = fixture.getElement("buy-pattern-form");
  const cases = [
    ["", "70000", /100자 이내/],
    ["나".repeat(101), "70000", /100자 이내/],
    ["돌파 매수", "", /0보다 큰 숫자/],
    ["돌파 매수", "0", /0보다 큰 숫자/],
    ["돌파 매수", "-100", /0보다 큰 숫자/],
    ["돌파 매수", "abc", /0보다 큰 숫자/],
    ["돌파 매수", "100001", /10만원/],
  ];
  for (const [name, target, expected] of cases) {
    fixture.getElement("buy-pattern-name").value = name;
    fixture.getElement("buy-target-price").value = target;
    form.dispatch("submit");
    assert.deepEqual(fixture.getDraft(), original);
    assert.match(fixture.getElement("notice").textContent, expected);
  }
});

test("buy patterns stay out of sell linkage and support the active toggle", () => {
  const fixture = boardWithDraft({
    symbols: [{code: "005930", name: "삼성전자", patternId: "", archived: false}],
    patterns: [
      {id: "buy-a", patternId: "buy-a", version: 1, active: true, name: "매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "70000", orderType: "LIMIT"},
      {id: "stop-a", patternId: "stop-a", version: 1, active: true, name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800", orderType: "MARKET"},
    ],
  });
  const symbolCard = fixture.getElement("symbol-list").children[0];
  const select = descendants(symbolCard).find((item) => item.tagName === "select");
  assert.deepEqual(
    select.children.map((option) => option.value),
    ["", "stop-a"],
  );
  const buyCard = fixture.getElement("buy-pattern-list").children[0];
  descendants(buyCard).find((item) => item.className === "pattern-toggle").dispatch("click");
  assert.equal(fixture.getDraft().patterns[0].active, false);
  assert.equal(fixture.getDraft().symbols[0].patternId, "");
});

test("pattern saves fall back to a local id without crypto.randomUUID", () => {
  const fixture = boardWithDraft({
    symbols: [],
    patterns: [{id: "pattern-a", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: "9800"}],
  }, {withoutCrypto: true});
  fixture.getElement("buy-pattern-name").value = "돌파 매수";
  fixture.getElement("buy-target-price").value = "70000";
  fixture.getElement("buy-pattern-form").dispatch("submit");

  const patternCard = fixture.getElement("pattern-list").children[0];
  const versionForm = descendants(patternCard)
    .find((item) => item.className === "stack-form pattern-version-form");
  const versionFields = descendants(versionForm);
  versionFields.find((item) => item.name === "name").value = "손절 조정";
  versionFields.find((item) => item.name === "threshold").value = "9700";
  versionFields.find((item) => item.name === "orderType").value = "MARKET";
  versionForm.dispatch("submit");

  const draft = fixture.getDraft();
  assert.equal(draft.patterns.length, 3);
  const shape = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  assert.match(draft.patterns[1].id, shape);
  assert.match(draft.patterns[2].id, shape);
  assert.notEqual(draft.patterns[1].id, draft.patterns[2].id);
  assert.equal(draft.patterns[1].patternId, draft.patterns[1].id);
});

test("full backup round-trips buy patterns with price thresholds", () => {
  const backup = {
    format: "cherrypulse-board-draft",
    schemaVersion: 1,
    symbols: [],
    patterns: [
      {id: "buy-a", patternId: "buy-a", version: 1, active: true, name: "매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "70000", orderType: "LIMIT"},
    ],
  };
  assert.deepEqual(parseBoardBackup(serializeBoardBackup(backup)), backup);
});

test("overview counts draft bindings independently of list filters and updates on archive", () => {
  const board = boardWithDraft({symbols: [
    {code: "005930", name: "삼성전자", patternId: "stop"},
    {code: "000660", name: "SK하이닉스", patternId: "missing"},
    {code: "005935", name: "삼성전자우", archived: true},
  ], patterns: [{id: "stop", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: 100, orderType: "MARKET"}]});
  assert.equal(board.getElement("overview-active").textContent, "2");
  assert.equal(board.getElement("overview-linked").textContent, "1");
  assert.equal(board.getElement("overview-unlinked").textContent, "1");
  assert.equal(board.getElement("overview-archived").textContent, "1");
  board.getElement("archived-filter").click();
  assert.equal(board.getElement("overview-active").textContent, "2");
  const restore = descendants(board.getElement("symbol-list")).find((item) => item.textContent === "관심 목록으로 복원");
  restore.click();
  assert.equal(board.getElement("overview-active").textContent, "3");
  assert.equal(board.getElement("overview-unlinked").textContent, "2");
});

test("detail panel preserves its open state after saving and closes with keyboard focus restored", () => {
  const board = boardWithDraft({symbols: [{code: "005930", name: "삼성전자", patternId: ""}], patterns: [
    {id: "stop", name: "손절", kind: "PRICE_AT_OR_BELOW", threshold: 100, orderType: "MARKET"},
  ]});
  const list = board.getElement("symbol-list");
  const drawer = descendants(list).find((element) => element.className === "symbol-drawer");
  drawer.open = true;
  const select = descendants(drawer).find((element) => element.tagName === "select");
  select.value = "stop";
  select.dispatch("change");
  assert.equal(board.getDraft().symbols[0].patternId, "stop");
  const next = descendants(list).find((element) => element.className === "symbol-drawer");
  assert.equal(next.open, true);
  assert.ok(descendants(list).some((element) => element.className === "card-rule" && element.textContent.includes("손절: 손절")));
  next.dispatch("keydown", {key: "Escape"});
  assert.equal(next.open, false);
  assert.equal(next.children[0].focused, true);
});

test("symbol buy binding persists separately and preview evaluates only linked patterns without mutations", () => {
  const draft = {symbols: [{code: "005930", name: "삼성전자", patternId: "stop"}], patterns: [
    {id: "buy", name: "매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "50000", orderType: "LIMIT"},
    {id: "stop", name: "손절", kind: "AVERAGE_COST_DROP", threshold: "0.03", orderType: "MARKET"},
  ]};
  const board = boardWithDraft(draft);
  let all = descendants(board.getElement("symbol-list"));
  const buySelect = all.find((element) => element.id === "buy-link-005930");
  assert.equal(buySelect.children.length, 2);
  buySelect.value = "buy"; buySelect.dispatch("change");
  const saved = board.getDraft();
  assert.equal(saved.symbols[0].patternId, "stop");
  assert.equal(saved.symbols[0].buyPatternId, "buy");
  all = descendants(board.getElement("symbol-list"));
  all.find((element) => element.id === "preview-price-005930").value = "48000";
  all.find((element) => element.id === "preview-average-005930").value = "50000";
  all.find((element) => element.className === "stack-form symbol-preview").dispatch("submit");
  const result = all.find((element) => element.className === "symbol-preview-result").textContent;
  assert.ok(result.includes("매수: 조건 충족"));
  assert.ok(result.includes("손절: 조건 충족"));
  assert.ok(result.includes("주문 없음"));
  assert.deepEqual(board.getDraft(), saved);
  const reloaded = boardWithDraft(saved);
  assert.equal(descendants(reloaded.getElement("symbol-list")).find((element) => element.id === "buy-link-005930").value, "buy");
});

test("inactive buy patterns cannot gain new bindings and storage failures preserve old linkage", () => {
  const board = boardWithDraft({symbols: [{code: "005930", name: "삼성전자"}], patterns: [
    {id: "off", name: "꺼짐", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "100", orderType: "LIMIT", active: false},
    {id: "on", name: "켜짐", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "100", orderType: "LIMIT"},
  ]});
  const select = descendants(board.getElement("symbol-list")).find((element) => element.id === "buy-link-005930");
  select.value = "off"; select.dispatch("change");
  assert.equal(board.getDraft().symbols[0].buyPatternId, undefined);
  board.setStorageFailure(true); select.value = "on"; select.dispatch("change");
  assert.equal(board.getDraft().symbols[0].buyPatternId, undefined);
  assert.equal(select.value, "");
});

test("backup preserves optional buy linkage, reads legacy drafts and rejects dangling or swapped links", () => {
  const backup = sampleBoardBackup();
  assert.equal(parseBoardBackup(JSON.stringify(backup)).symbols[0].buyPatternId, undefined);
  backup.patterns.push({id: "buy", name: "매수", kind: "BUY_PRICE_AT_OR_BELOW", threshold: "100", orderType: "LIMIT"});
  backup.symbols[0].buyPatternId = "buy";
  const parsed = parseBoardBackup(serializeBoardBackup(backup));
  assert.equal(parsed.symbols[0].buyPatternId, "buy");
  for (const [key, value, code] of [
    ["buyPatternId", "missing", "BACKUP_PATTERN_LINK_MISSING"],
    ["buyPatternId", "stop-v1", "BACKUP_PATTERN_LINK_KIND"],
    ["patternId", "buy", "BACKUP_PATTERN_LINK_KIND"],
  ]) {
    const invalid = JSON.parse(JSON.stringify(backup)); invalid.symbols[0][key] = value;
    assert.throws(() => parseBoardBackup(JSON.stringify(invalid)), (error) => error.code === code);
  }
});

test('cloud load requires confirmation, preserves local edits and handles storage failure', async () => {
  let accepted = 0;
  const remote = {revision: 3, snapshot: sampleBoardBackup()};
  const cloud = {signedIn: () => true, load: async () => remote, acceptLoaded: () => accepted++};
  const original = {symbols: [], patterns: []};
  const board = boardWithDraft(original, {cloud});
  await board.getElement('cloud-load').dispatchAsync('click');
  assert.deepEqual(board.getDraft(), original);
  assert.equal(board.getElement('cloud-load-confirmation').hidden, false);
  board.setStorageFailure(true);
  await board.getElement('cloud-confirm-load').dispatchAsync('click');
  assert.deepEqual(board.getDraft(), original); assert.equal(accepted, 0);
  board.setStorageFailure(false);
  board.setExternalDraft({symbols: [{code: '000660', name: '다른 탭'}], patterns: []});
  await board.getElement('cloud-confirm-load').dispatchAsync('click');
  assert.equal(accepted, 0); assert.match(board.getElement('cloud-status').textContent, /바뀌었습니다/);
});
test('confirmed cloud load stores only draft fields and accepts the fetched version', async () => {
  let accepted;
  const remote = {revision: 3, snapshot: sampleBoardBackup()};
  const cloud = {signedIn: () => true, load: async () => remote, acceptLoaded: value => { accepted = value; }};
  const board = boardWithDraft({symbols: [], patterns: []}, {cloud});
  await board.getElement('cloud-load').dispatchAsync('click');
  await board.getElement('cloud-confirm-load').dispatchAsync('click');
  assert.equal(accepted.revision, 3);
  assert.deepEqual(board.getDraft(), {symbols: remote.snapshot.symbols, patterns: remote.snapshot.patterns});
  assert.match(board.getElement('cloud-status').textContent, /엔진 미적용/);
});

test('PIN validates before disabling controls and displays progress then success', async () => {
  let calls = 0, finish, signedIn = false;
  const cloud = {signedIn: () => signedIn, inspect: async () => ({revision: 0}), auth: async () => {
    calls++; return new Promise(resolve => { finish = () => { signedIn = true; resolve({signedIn: true}); }; });
  }};
  const board = boardWithDraft({symbols: [], patterns: []}, {cloud});
  for (const value of ['', '123', 'abcd', '12345']) {
    board.getElement('cloud-pin').value = value;
    await board.getElement('cloud-login-form').dispatchAsync('submit');
    assert.equal(calls, 0); assert.match(board.getElement('cloud-status').textContent, /숫자 4자리/);
  }
  board.getElement('cloud-pin').value = '0123';
  const work = board.getElement('cloud-login-form').dispatchAsync('submit');
  assert.equal(calls, 1); assert.equal(board.getElement('cloud-login').disabled, true);
  assert.match(board.getElement('cloud-status').textContent, /비밀번호 확인 중/);
  finish(); await work;
  assert.match(board.getElement('cloud-status').textContent, /보드 접속 완료/);
  assert.equal(board.getElement('cloud-pin').value, '');
  assert.equal(board.getElement('cloud-save').disabled, false);
});
test('incorrect PIN displays an actionable failure and unlocks the input', async () => {
  const cloud = {signedIn: () => false, auth: async () => { throw {code: 'PIN_INCORRECT'}; }};
  const board = boardWithDraft({symbols: [], patterns: []}, {cloud});
  board.getElement('cloud-pin').value = '0123';
  await board.getElement('cloud-login-form').dispatchAsync('submit');
  assert.match(board.getElement('cloud-status').textContent, /비밀번호가 일치하지 않습니다/);
  assert.equal(board.getElement('cloud-login').disabled, false);
});
