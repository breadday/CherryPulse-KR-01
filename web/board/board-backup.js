"use strict";

(function exposeBoardBackup(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.CherryPulseBoardBackup = api;
  }
})(globalThis, () => {
  const BACKUP_FORMAT = "cherrypulse-board-draft";
  const BACKUP_SCHEMA_VERSION = 1;
  const rootFields = new Set(["format", "schemaVersion", "symbols", "patterns"]);
  const symbolFields = new Set(["code", "name", "source", "note", "patternId", "archived"]);
  const patternFields = new Set([
    "id", "name", "kind", "threshold", "orderType", "patternId", "version", "active",
  ]);
  const patternKinds = new Set(["PRICE_AT_OR_BELOW", "AVERAGE_COST_DROP"]);
  const orderTypes = new Set(["MARKET", "LIMIT"]);
  const decimalPattern = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

  class BoardBackupError extends Error {
    constructor(code, path = "") {
      super(code);
      this.code = code;
      this.path = path;
    }
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function rejectUnknownFields(value, allowed, path) {
    for (const key of Object.keys(value)) {
      if (!allowed.has(key)) throw new BoardBackupError("BACKUP_FIELDS_INVALID", `${path}.${key}`);
    }
  }

  function validateOptionalText(record, key, maxLength, path) {
    if (!Object.hasOwn(record, key)) return;
    const value = record[key];
    if (typeof value !== "string" || value.length > maxLength) {
      throw new BoardBackupError("BACKUP_FIELD_INVALID", `${path}.${key}`);
    }
  }

  function validateSource(record, path) {
    validateOptionalText(record, "source", 2048, path);
    const source = record.source;
    if (source === undefined || source === "") return;
    try {
      const url = new URL(source);
      if (url.protocol === "http:" || url.protocol === "https:") return;
    } catch {
      // Reject malformed and unsupported URLs below.
    }
    throw new BoardBackupError("BACKUP_FIELD_INVALID", `${path}.source`);
  }

  function validateSymbols(symbols) {
    const codes = new Set();
    for (const [index, symbol] of symbols.entries()) {
      const path = `symbols[${index}]`;
      if (!isRecord(symbol)) throw new BoardBackupError("BACKUP_SYMBOL_INVALID", path);
      rejectUnknownFields(symbol, symbolFields, path);
      if (typeof symbol.code !== "string" || !/^\d{6}$/.test(symbol.code)) {
        throw new BoardBackupError("BACKUP_SYMBOL_INVALID", `${path}.code`);
      }
      if (codes.has(symbol.code)) throw new BoardBackupError("BACKUP_DUPLICATE_SYMBOL", `${path}.code`);
      codes.add(symbol.code);
      if (typeof symbol.name !== "string" || !symbol.name.trim() || symbol.name.length > 100) {
        throw new BoardBackupError("BACKUP_SYMBOL_INVALID", `${path}.name`);
      }
      validateSource(symbol, path);
      validateOptionalText(symbol, "note", 1000, path);
      if (Object.hasOwn(symbol, "patternId") &&
        (typeof symbol.patternId !== "string" || symbol.patternId.length > 128)) {
        throw new BoardBackupError("BACKUP_FIELD_INVALID", `${path}.patternId`);
      }
      if (Object.hasOwn(symbol, "archived") && typeof symbol.archived !== "boolean") {
        throw new BoardBackupError("BACKUP_FIELD_INVALID", `${path}.archived`);
      }
    }
  }

  function validatePatterns(patterns) {
    const ids = new Set();
    const revisions = new Set();
    for (const [index, pattern] of patterns.entries()) {
      const path = `patterns[${index}]`;
      if (!isRecord(pattern)) throw new BoardBackupError("BACKUP_PATTERN_INVALID", path);
      rejectUnknownFields(pattern, patternFields, path);
      if (typeof pattern.id !== "string" || !pattern.id.trim() || pattern.id.length > 128) {
        throw new BoardBackupError("BACKUP_PATTERN_INVALID", `${path}.id`);
      }
      if (ids.has(pattern.id)) throw new BoardBackupError("BACKUP_DUPLICATE_PATTERN_ID", `${path}.id`);
      ids.add(pattern.id);
      if (typeof pattern.name !== "string" || !pattern.name.trim() || pattern.name.length > 100 ||
        !patternKinds.has(pattern.kind)) {
        throw new BoardBackupError("BACKUP_PATTERN_INVALID", path);
      }
      if (typeof pattern.threshold !== "string" || pattern.threshold.trim() !== pattern.threshold ||
        !decimalPattern.test(pattern.threshold)) {
        throw new BoardBackupError("BACKUP_THRESHOLD_INVALID", `${path}.threshold`);
      }
      const threshold = Number(pattern.threshold);
      if (!Number.isFinite(threshold) || threshold <= 0 ||
        (pattern.kind === "AVERAGE_COST_DROP" && threshold >= 1)) {
        throw new BoardBackupError("BACKUP_THRESHOLD_INVALID", `${path}.threshold`);
      }
      if (Object.hasOwn(pattern, "orderType") && !orderTypes.has(pattern.orderType)) {
        throw new BoardBackupError("BACKUP_ORDER_TYPE_INVALID", `${path}.orderType`);
      }
      const hasFamily = Object.hasOwn(pattern, "patternId");
      const hasVersion = Object.hasOwn(pattern, "version");
      if (hasFamily !== hasVersion) {
        throw new BoardBackupError("BACKUP_PATTERN_REVISION_INVALID", path);
      }
      if (hasFamily && (typeof pattern.patternId !== "string" ||
        !pattern.patternId.trim() || pattern.patternId.length > 128 ||
        !Number.isSafeInteger(pattern.version) || pattern.version <= 0)) {
        throw new BoardBackupError("BACKUP_PATTERN_REVISION_INVALID", path);
      }
      if (Object.hasOwn(pattern, "active") && typeof pattern.active !== "boolean") {
        throw new BoardBackupError("BACKUP_PATTERN_INVALID", `${path}.active`);
      }
      const familyId = hasFamily ? pattern.patternId : pattern.id;
      const revision = hasVersion ? pattern.version : 1;
      const revisionKey = `${familyId}\u0000${revision}`;
      if (revisions.has(revisionKey)) {
        throw new BoardBackupError("BACKUP_DUPLICATE_PATTERN_VERSION", path);
      }
      revisions.add(revisionKey);
    }
    return ids;
  }

  function parseBoardBackup(text) {
    let backup;
    try {
      backup = JSON.parse(text);
    } catch {
      throw new BoardBackupError("BACKUP_JSON_INVALID");
    }
    if (!isRecord(backup)) throw new BoardBackupError("BACKUP_ROOT_INVALID");
    rejectUnknownFields(backup, rootFields, "backup");
    if (backup.format !== BACKUP_FORMAT) throw new BoardBackupError("BACKUP_FORMAT_UNSUPPORTED");
    if (backup.schemaVersion !== BACKUP_SCHEMA_VERSION) {
      throw new BoardBackupError("BACKUP_SCHEMA_UNSUPPORTED");
    }
    if (!Array.isArray(backup.symbols) || !Array.isArray(backup.patterns)) {
      throw new BoardBackupError("BACKUP_COLLECTIONS_INVALID");
    }
    validateSymbols(backup.symbols);
    const patternIds = validatePatterns(backup.patterns);
    for (const [index, symbol] of backup.symbols.entries()) {
      if (symbol.patternId && !patternIds.has(symbol.patternId)) {
        throw new BoardBackupError("BACKUP_PATTERN_LINK_MISSING", `symbols[${index}].patternId`);
      }
    }
    return backup;
  }

  function serializeBoardBackup(state) {
    const text = JSON.stringify({
      format: BACKUP_FORMAT,
      schemaVersion: BACKUP_SCHEMA_VERSION,
      symbols: state.symbols,
      patterns: state.patterns,
    }, null, 2);
    parseBoardBackup(text);
    return text;
  }

  function backupSummary(backup) {
    return {
      symbols: backup.symbols.length,
      archivedSymbols: backup.symbols.filter((symbol) => symbol.archived === true).length,
      patterns: backup.patterns.length,
      inactivePatterns: backup.patterns.filter((pattern) => pattern.active === false).length,
    };
  }

  return {
    BACKUP_FORMAT,
    BACKUP_SCHEMA_VERSION,
    BoardBackupError,
    backupSummary,
    parseBoardBackup,
    serializeBoardBackup,
  };
});
