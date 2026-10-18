"use strict";

(function exposeLogView(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CherryPulseLogView = api;
  }
})(globalThis, () => {
  const MAX_TEXT_BYTES = 1024 * 1024;
  const MAX_REASON_LENGTH = 64;
  const MAX_MESSAGE_LENGTH = 160;

  class LogViewError extends Error {
    constructor(code) {
      super(code);
      this.code = code;
    }
  }

  function shortCode(value) {
    if (typeof value === "number" && Number.isInteger(value)) return value;
    if (typeof value !== "string" || !value) return null;
    return value.slice(0, MAX_REASON_LENGTH);
  }

  function cleanMessage(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    return value.replace(/\d{4,}/g, "<digits>").trim().slice(0, MAX_MESSAGE_LENGTH);
  }

  function countBool(value) {
    return value === true;
  }

  function nonNegativeInt(value) {
    return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : null;
  }

  function summarizeProbe(payload) {
    const queries = Array.isArray(payload.queries) ? payload.queries : null;
    if (!queries) return null;
    const brief = [];
    for (const item of queries) {
      if (!item || typeof item !== "object") return null;
      if (typeof item.api_id !== "string" || !item.api_id) return null;
      brief.push({
        api_id: item.api_id.slice(0, 16),
        complete: item.complete === true,
        reason: shortCode(item.reason),
        pages: nonNegativeInt(item.pages),
        observed_rows: nonNegativeInt(item.observed_rows),
      });
    }
    return {
      complete: brief.length > 0 && brief.every((item) => item.complete),
      total: brief.length,
      queries: brief,
    };
  }

  function summarizeSubmit(payload) {
    if (typeof payload.order_submitted !== "boolean" || typeof payload.acked !== "boolean") return null;
    return {
      submitted: payload.order_submitted,
      acked: payload.acked,
      reason: shortCode(payload.reason),
      broker_code: typeof payload.broker_code === "number" || payload.broker_code === null
        ? payload.broker_code
        : null,
      broker_message: cleanMessage(payload.broker_message),
    };
  }

  function summarizeLinkage(payload) {
    if (!payload.row_counts || typeof payload.row_counts !== "object") return null;
    const rows = {};
    for (const [key, value] of Object.entries(payload.row_counts)) {
      const count = nonNegativeInt(value);
      if (count === null) return null;
      rows[String(key).slice(0, 16)] = count;
    }
    return {
      row_counts: rows,
      order_seen: countBool(payload.order_seen_in_multiple),
      fills_seen: countBool(payload.fills_seen),
      reason: shortCode(payload.reason),
    };
  }

  function parseLogText(text) {
    if (typeof text !== "string" || !text) throw new LogViewError("LOG_EMPTY");
    if (typeof Buffer !== "undefined" && Buffer.byteLength(text, "utf8") > MAX_TEXT_BYTES) throw new LogViewError("LOG_TOO_LARGE");
    const lines = text.split(/\r?\n/);
    const summary = {lines: 0, probe: null, submit: null, linkage: null};
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("{")) continue;
      let payload;
      try {
        payload = JSON.parse(trimmed);
      } catch {
        continue;
      }
      if (!payload || typeof payload !== "object") continue;
      summary.lines += 1;
      summary.probe = summarizeProbe(payload) || summary.probe;
      summary.submit = summarizeSubmit(payload) || summary.submit;
      summary.linkage = summarizeLinkage(payload) || summary.linkage;
    }
    if (!summary.lines) throw new LogViewError("LOG_NO_JSON");
    return summary;
  }

  function describe(summary) {
    const parts = [`JSON ${summary.lines}줄 읽음.`];
    if (summary.probe) {
      parts.push(`조회 ${summary.probe.total}건 ${summary.probe.complete ? "완료" : "미완료"}.`);
    }
    if (summary.submit) {
      if (summary.submit.acked) parts.push("모의 주문 접수됨.");
      else if (summary.submit.submitted) parts.push(`주문 거절(코드 ${String(summary.submit.broker_code)}).`);
      else parts.push("미리보기만(전송 없음).");
    }
    if (summary.linkage) {
      const total = Object.values(summary.linkage.row_counts).reduce((a, b) => a + b, 0);
      parts.push(total > 0 ? `이력 ${total}행 관측.` : "이력 0행.");
    }
    return parts.join(" ");
  }

  return {LogViewError, parseLogText, describe};
});
