"use strict";

const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.value = "";
    this.textContent = "";
  }

  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  setAttribute(name, value) { this.attributes.set(name, value); }
  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || [];
    callbacks.push(callback);
    this.listeners.set(name, callbacks);
  }
  dispatch(name, event = {}) {
    for (const callback of this.listeners.get(name) || []) {
      callback({target: this, preventDefault() {}, ...event});
    }
  }
  reset() { this.value = ""; }
}

function descendants(element) {
  return element.children.flatMap((child) => [child, ...descendants(child)]);
}

function boardWithDraft(draft) {
  const ids = [
    "notice", "symbol-count", "active-filter", "archived-filter", "symbol-list",
    "pattern-list", "symbol-form", "pattern-kind", "pattern-order-type", "threshold-label",
    "threshold-hint", "pattern-threshold", "pattern-name", "pattern-form",
    "symbol-input", "symbol-name", "symbol-source", "symbol-note",
  ];
  const elements = new Map(ids.map((id) => [id, new Element("div", id)]));
  const stored = new Map([["cherrypulse-board-draft-v1", JSON.stringify(draft)]]);
  const document = {
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
    URL,
    Event: class { constructor(type) { this.type = type; } },
  };
  const source = readFileSync(path.join(__dirname, "board.js"), "utf8");
  vm.runInNewContext(source, context, {filename: "board.js"});
  return {
    getElement: (id) => elements.get(id),
    getDraft: () => JSON.parse(stored.get("cherrypulse-board-draft-v1")),
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
