"use strict";

(function exposeDraftImport(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CherryPulseDraftImport = api;
  }
})(globalThis, () => {
  const allowedFields = new Set(["code", "name", "source", "note"]);
  const requiredFields = new Set(["code", "name"]);

  class DraftImportError extends Error {
    constructor(code, recordNumber) {
      super(code);
      this.code = code;
      this.recordNumber = recordNumber;
    }
  }

  function parseCsv(text) {
    const rows = [];
    let row = [];
    let field = "";
    let quoted = false;
    let quoteClosed = false;
    for (let index = 0; index < text.length; index += 1) {
      const char = text[index];
      if (quoted) {
        if (char === '"') {
          if (text[index + 1] === '"') {
            field += '"';
            index += 1;
          } else {
            quoted = false;
            quoteClosed = true;
          }
        } else {
          field += char;
        }
        continue;
      }
      if (quoteClosed && char !== "," && char !== "\r" && char !== "\n") {
        throw new DraftImportError("IMPORT_CSV_INVALID");
      }
      if (char === '"') {
        if (field) throw new DraftImportError("IMPORT_CSV_INVALID");
        quoted = true;
      } else if (char === ",") {
        row.push(field);
        field = "";
        quoteClosed = false;
      } else if (char === "\r" || char === "\n") {
        row.push(field);
        if (row.some((cell) => cell.trim())) rows.push(row);
        row = [];
        field = "";
        quoteClosed = false;
        if (char === "\r" && text[index + 1] === "\n") index += 1;
      } else {
        field += char;
      }
    }
    if (quoted) throw new DraftImportError("IMPORT_CSV_INVALID");
    if (field || row.length || quoteClosed) {
      row.push(field);
      if (row.some((cell) => cell.trim())) rows.push(row);
    }
    return rows;
  }

  function sourceUrl(value, recordNumber) {
    if (value === undefined || value === "") return "";
    if (typeof value !== "string" || value.length > 2048) {
      throw new DraftImportError("IMPORT_SYMBOL_INVALID", recordNumber);
    }
    try {
      const url = new URL(value);
      if (url.protocol === "http:" || url.protocol === "https:") return url.href;
    } catch {
      // Convert malformed and unsupported URLs to one input validation result.
    }
    throw new DraftImportError("IMPORT_SYMBOL_INVALID", recordNumber);
  }

  function normalizeRecord(record, recordNumber) {
    if (!record || typeof record !== "object" || Array.isArray(record)) {
      throw new DraftImportError("IMPORT_SYMBOL_INVALID", recordNumber);
    }
    for (const key of Object.keys(record)) {
      if (!allowedFields.has(key)) throw new DraftImportError("IMPORT_FIELDS_INVALID", recordNumber);
    }
    for (const key of requiredFields) {
      if (typeof record[key] !== "string") throw new DraftImportError("IMPORT_SYMBOL_INVALID", recordNumber);
    }
    const code = record.code.trim();
    const name = record.name.trim();
    const note = record.note === undefined ? "" : record.note;
    const source = record.source === undefined ? "" : record.source;
    if (!/^\d{6}$/.test(code) || !name || name.length > 100 ||
      typeof source !== "string" || typeof note !== "string" || note.length > 1000) {
      throw new DraftImportError("IMPORT_SYMBOL_INVALID", recordNumber);
    }
    return {code, name, source: sourceUrl(source.trim(), recordNumber), note: note.trim()};
  }

  function recordsFromCsv(text) {
    const rows = parseCsv(text.replace(/^\uFEFF/, ""));
    if (!rows.length) throw new DraftImportError("IMPORT_EMPTY");
    const headers = rows[0].map((header) => header.trim());
    if (new Set(headers).size !== headers.length ||
      ![...requiredFields].every((key) => headers.includes(key)) ||
      headers.some((key) => !allowedFields.has(key))) {
      throw new DraftImportError("IMPORT_CSV_HEADER_INVALID");
    }
    return rows.slice(1).map((cells, index) => {
      if (cells.length !== headers.length) {
        throw new DraftImportError("IMPORT_CSV_INVALID", index + 2);
      }
      return Object.fromEntries(headers.map((header, cellIndex) => [header, cells[cellIndex]]));
    });
  }

  function parseSymbolImport(fileName, text, existingSymbols = []) {
    const extension = fileName.toLowerCase().split(".").pop();
    let records;
    if (extension === "json") {
      try {
        records = JSON.parse(text);
      } catch {
        throw new DraftImportError("IMPORT_JSON_INVALID");
      }
      if (!Array.isArray(records)) throw new DraftImportError("IMPORT_JSON_ARRAY_REQUIRED");
    } else if (extension === "csv") {
      records = recordsFromCsv(text);
    } else {
      throw new DraftImportError("IMPORT_FILE_TYPE_UNSUPPORTED");
    }
    if (!records.length) throw new DraftImportError("IMPORT_EMPTY");

    const seen = new Set(existingSymbols.map((symbol) => symbol.code));
    return records.map((record, index) => {
      const normalized = normalizeRecord(record, index + 1);
      if (seen.has(normalized.code)) {
        throw new DraftImportError("IMPORT_DUPLICATE_SYMBOL", index + 1);
      }
      seen.add(normalized.code);
      return {...normalized, patternId: "", archived: false};
    });
  }

  function exportActiveSymbols(symbols) {
    return symbols
      .filter((symbol) => symbol.archived !== true)
      .map(({code, name, source, note}) => ({
        code,
        name,
        source: source || "",
        note: note || "",
      }));
  }

  return {DraftImportError, exportActiveSymbols, parseSymbolImport};
});
