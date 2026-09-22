export type Instrument = Readonly<{
  symbol: string
  name: string
  market: 'KOSPI' | 'KOSDAQ'
}>

export type PriceThreshold = Readonly<{
  kind: 'PRICE_THRESHOLD'
  comparison: 'GTE' | 'LTE'
  threshold_price: string
}>

export type AveragePricePercent = Readonly<{
  kind: 'AVERAGE_PRICE_PERCENT'
  percent: string
}>

export type PatternDefinition = PriceThreshold | AveragePricePercent

export type PatternVersion = Readonly<{
  pattern_id: string
  version: number
  side: 'BUY' | 'SELL'
  name: string
  definition: PatternDefinition
}>

export type PatternRef = Readonly<{
  pattern_id: string
  version: number
}>

export type ExecutionConfig = Readonly<{
  execution_id: string
  account_id: string
  environment: 'PAPER' | 'LIVE'
  symbol: string
  buy_pattern: PatternRef
  sell_pattern: PatternRef
  requested_version: number
  applied_version: number | null
  state: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED'
  requested_at: string
  expires_at: string
  rejection_reason: string | null
}>

export type OrderSnapshot = Readonly<{
  client_order_id: string
  request_id: string
  execution_id: string
  broker_order_no: string | null
  symbol: string
  side: 'BUY' | 'SELL'
  order_type: 'LIMIT' | 'MARKET'
  price: string | null
  quantity: number
  filled_quantity: number
  cancelled_quantity: number
  remaining_quantity: number
  state: 'PENDING' | 'OPEN' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELLED' | 'REJECTED'
}>

export type FillSnapshot = Readonly<{
  fill_id: string
  client_order_id: string
  quantity: number
  price: string
  filled_at: string
}>

export type OperationStatus = Readonly<{
  engine: 'ONLINE' | 'OFFLINE' | 'DEGRADED'
  live_trading_enabled: boolean
  data_mode: 'MOCK' | 'PAPER' | 'LIVE'
  reconciliation: 'OK' | 'RECONCILING' | 'RECONCILIATION_REQUIRED'
  last_event_at: string | null
}>

export type ContractBundle = Readonly<{
  schema_version: 1
  instrument: Instrument
  patterns: readonly PatternVersion[]
  execution_config: ExecutionConfig
  order: OrderSnapshot
  fills: readonly FillSnapshot[]
  operation: OperationStatus
}>

type JsonObject = Record<string, unknown>

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SYMBOL_PATTERN = /^[0-9]{6}$/
const KEY_PATTERN = /^[!-~]+$/
const DECIMAL_PATTERN = /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/
const AWARE_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,3})?(?:Z|[+-](\d{2}):(\d{2}))$/

function fail(code: string): never {
  throw new Error(code)
}

function object(value: unknown, keys: readonly string[], label: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    fail(`${label}_MUST_BE_OBJECT`)
  const result = value as JsonObject
  const allowed = new Set(keys)
  for (const key of Object.keys(result)) {
    if (!allowed.has(key)) fail(`${label}_UNKNOWN_FIELD`)
  }
  return result
}

function hasOwn(record: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

function required(record: JsonObject, key: string, label: string): unknown {
  if (!hasOwn(record, key)) fail(`${label}_${key.toUpperCase()}_REQUIRED`)
  return record[key]
}

function text(value: unknown, label: string): string {
  if (typeof value !== 'string' || value.length === 0) fail(label)
  return value
}

function oneOf<const T extends readonly string[]>(
  value: unknown,
  choices: T,
  label: string,
): T[number] {
  if (typeof value !== 'string' || !choices.includes(value)) fail(label)
  return value as T[number]
}

function integer(value: unknown, minimum: number, label: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum) fail(label)
  return value
}

function uuid(value: unknown, label: string): string {
  if (typeof value !== 'string' || !UUID_PATTERN.test(value)) fail(label)
  return value.toLowerCase()
}

function symbol(value: unknown): string {
  if (typeof value !== 'string' || !SYMBOL_PATTERN.test(value)) fail('INVALID_SYMBOL')
  return value
}

function key(value: unknown, label: string): string {
  if (typeof value !== 'string' || !KEY_PATTERN.test(value)) fail(label)
  return value
}

function canonicalDecimal(value: unknown, label: string): string {
  if (typeof value !== 'string' || !DECIMAL_PATTERN.test(value)) fail(label)
  const negative = value.startsWith('-')
  const unsigned = negative ? value.slice(1) : value
  const [whole = '0', fraction = ''] = unsigned.split('.')
  const trimmedFraction = fraction.replace(/0+$/, '')
  const magnitude = trimmedFraction === '' ? whole : `${whole}.${trimmedFraction}`
  if (magnitude === '0') return '0'
  return negative ? `-${magnitude}` : magnitude
}

function positiveDecimal(value: unknown, label: string, code: string): string {
  const canonical = canonicalDecimal(value, label)
  if (canonical === '0' || canonical.startsWith('-')) fail(code)
  return canonical
}

function awareDatetime(value: unknown, label: string): string {
  if (typeof value !== 'string') fail(label)
  const match = AWARE_DATETIME_PATTERN.exec(value)
  if (match === null) fail(label)

  const [
    ,
    yearText,
    monthText,
    dayText,
    hourText,
    minuteText,
    secondText,
    offsetHourText,
    offsetMinuteText,
  ] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = Number(hourText)
  const minute = Number(minuteText)
  const second = Number(secondText)
  const offsetHour = offsetHourText === undefined ? 0 : Number(offsetHourText)
  const offsetMinute = offsetMinuteText === undefined ? 0 : Number(offsetMinuteText)
  const daysInMonth =
    month >= 1 && month <= 12 ? new Date(Date.UTC(year, month, 0)).getUTCDate() : 0

  if (
    year < 1 ||
    day < 1 ||
    day > daysInMonth ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59 ||
    !Number.isFinite(Date.parse(value))
  ) {
    fail(label)
  }
  return value
}

function nullable<T>(value: unknown, parser: (input: unknown) => T): T | null {
  return value === null ? null : parser(value)
}

function parseInstrument(value: unknown): Instrument {
  const record = object(value, ['symbol', 'name', 'market'], 'INSTRUMENT')
  return Object.freeze({
    symbol: symbol(required(record, 'symbol', 'INSTRUMENT')),
    name: text(required(record, 'name', 'INSTRUMENT'), 'INVALID_INSTRUMENT_NAME'),
    market: oneOf(required(record, 'market', 'INSTRUMENT'), ['KOSPI', 'KOSDAQ'], 'INVALID_MARKET'),
  })
}

function parseDefinition(value: unknown): PatternDefinition {
  const record = object(
    value,
    ['kind', 'comparison', 'threshold_price', 'percent'],
    'PATTERN_DEFINITION',
  )
  const kind = oneOf(
    required(record, 'kind', 'PATTERN_DEFINITION'),
    ['PRICE_THRESHOLD', 'AVERAGE_PRICE_PERCENT'],
    'INVALID_PATTERN_KIND',
  )
  if (kind === 'PRICE_THRESHOLD') {
    const exact = object(value, ['kind', 'comparison', 'threshold_price'], 'PRICE_THRESHOLD')
    return Object.freeze({
      kind,
      comparison: oneOf(
        required(exact, 'comparison', 'PRICE_THRESHOLD'),
        ['GTE', 'LTE'],
        'INVALID_PATTERN_COMPARISON',
      ),
      threshold_price: positiveDecimal(
        required(exact, 'threshold_price', 'PRICE_THRESHOLD'),
        'INVALID_PATTERN_PRICE',
        'PATTERN_PRICE_MUST_BE_POSITIVE',
      ),
    })
  }

  const exact = object(value, ['kind', 'percent'], 'AVERAGE_PRICE_PERCENT')
  const percent = canonicalDecimal(
    required(exact, 'percent', 'AVERAGE_PRICE_PERCENT'),
    'INVALID_PATTERN_PERCENT',
  )
  if (!percent.startsWith('-') || compareDecimalMagnitude(percent.slice(1), '100') >= 0) {
    fail('PATTERN_PERCENT_OUT_OF_RANGE')
  }
  return Object.freeze({ kind, percent })
}

function compareDecimalMagnitude(left: string, right: string): number {
  const [leftWhole = '0', leftFraction = ''] = left.split('.')
  const [rightWhole = '0', rightFraction = ''] = right.split('.')
  if (leftWhole.length !== rightWhole.length) return leftWhole.length < rightWhole.length ? -1 : 1
  if (leftWhole !== rightWhole) return leftWhole < rightWhole ? -1 : 1
  const width = Math.max(leftFraction.length, rightFraction.length)
  const normalizedLeft = leftFraction.padEnd(width, '0')
  const normalizedRight = rightFraction.padEnd(width, '0')
  return normalizedLeft === normalizedRight ? 0 : normalizedLeft < normalizedRight ? -1 : 1
}

function parsePattern(value: unknown): PatternVersion {
  const record = object(value, ['pattern_id', 'version', 'side', 'name', 'definition'], 'PATTERN')
  return Object.freeze({
    pattern_id: uuid(required(record, 'pattern_id', 'PATTERN'), 'INVALID_PATTERN_ID'),
    version: integer(required(record, 'version', 'PATTERN'), 1, 'INVALID_PATTERN_VERSION'),
    side: oneOf(required(record, 'side', 'PATTERN'), ['BUY', 'SELL'], 'INVALID_PATTERN_SIDE'),
    name: text(required(record, 'name', 'PATTERN'), 'INVALID_PATTERN_NAME'),
    definition: parseDefinition(required(record, 'definition', 'PATTERN')),
  })
}

function parsePatternRef(value: unknown, label: string): PatternRef {
  const record = object(value, ['pattern_id', 'version'], label)
  return Object.freeze({
    pattern_id: uuid(required(record, 'pattern_id', label), 'INVALID_PATTERN_ID'),
    version: integer(required(record, 'version', label), 1, 'INVALID_PATTERN_VERSION'),
  })
}

function parseExecutionConfig(value: unknown): ExecutionConfig {
  const record = object(
    value,
    [
      'execution_id',
      'account_id',
      'environment',
      'symbol',
      'buy_pattern',
      'sell_pattern',
      'requested_version',
      'applied_version',
      'state',
      'requested_at',
      'expires_at',
      'rejection_reason',
    ],
    'EXECUTION_CONFIG',
  )
  const requestedVersion = integer(
    required(record, 'requested_version', 'EXECUTION_CONFIG'),
    1,
    'INVALID_REQUESTED_VERSION',
  )
  const appliedVersion = nullable(required(record, 'applied_version', 'EXECUTION_CONFIG'), (item) =>
    integer(item, 1, 'INVALID_APPLIED_VERSION'),
  )
  const state = oneOf(
    required(record, 'state', 'EXECUTION_CONFIG'),
    ['PENDING', 'ACCEPTED', 'REJECTED', 'EXPIRED'],
    'INVALID_CONFIG_STATE',
  )
  const requestedAt = awareDatetime(
    required(record, 'requested_at', 'EXECUTION_CONFIG'),
    'INVALID_REQUESTED_AT',
  )
  const expiresAt = awareDatetime(
    required(record, 'expires_at', 'EXECUTION_CONFIG'),
    'INVALID_EXPIRES_AT',
  )
  const rejectionReason = nullable(
    required(record, 'rejection_reason', 'EXECUTION_CONFIG'),
    (item) => text(item, 'INVALID_REJECTION_REASON'),
  )

  if (Date.parse(expiresAt) <= Date.parse(requestedAt)) fail('CONFIG_EXPIRY_MUST_FOLLOW_REQUEST')
  if (state === 'PENDING' && (appliedVersion !== null || rejectionReason !== null)) {
    fail('PENDING_CONFIG_HAS_RESULT')
  }
  if (state === 'ACCEPTED') {
    if (appliedVersion !== requestedVersion) fail('ACCEPTED_VERSION_MISMATCH')
    if (rejectionReason !== null) fail('ACCEPTED_CONFIG_HAS_REJECTION')
  }
  if (state === 'REJECTED' && (appliedVersion !== null || rejectionReason === null)) {
    fail('REJECTED_CONFIG_RESULT_INVALID')
  }
  if (state === 'EXPIRED' && (appliedVersion !== null || rejectionReason !== null)) {
    fail('EXPIRED_CONFIG_HAS_RESULT')
  }

  return Object.freeze({
    execution_id: uuid(
      required(record, 'execution_id', 'EXECUTION_CONFIG'),
      'INVALID_EXECUTION_ID',
    ),
    account_id: key(required(record, 'account_id', 'EXECUTION_CONFIG'), 'INVALID_ACCOUNT_ID'),
    environment: oneOf(
      required(record, 'environment', 'EXECUTION_CONFIG'),
      ['PAPER', 'LIVE'],
      'INVALID_ENVIRONMENT',
    ),
    symbol: symbol(required(record, 'symbol', 'EXECUTION_CONFIG')),
    buy_pattern: parsePatternRef(
      required(record, 'buy_pattern', 'EXECUTION_CONFIG'),
      'BUY_PATTERN',
    ),
    sell_pattern: parsePatternRef(
      required(record, 'sell_pattern', 'EXECUTION_CONFIG'),
      'SELL_PATTERN',
    ),
    requested_version: requestedVersion,
    applied_version: appliedVersion,
    state,
    requested_at: requestedAt,
    expires_at: expiresAt,
    rejection_reason: rejectionReason,
  })
}

function parseOrder(value: unknown): OrderSnapshot {
  const record = object(
    value,
    [
      'client_order_id',
      'request_id',
      'execution_id',
      'broker_order_no',
      'symbol',
      'side',
      'order_type',
      'price',
      'quantity',
      'filled_quantity',
      'cancelled_quantity',
      'remaining_quantity',
      'state',
    ],
    'ORDER',
  )
  const orderType = oneOf(
    required(record, 'order_type', 'ORDER'),
    ['LIMIT', 'MARKET'],
    'INVALID_ORDER_TYPE',
  )
  const rawPrice = required(record, 'price', 'ORDER')
  const price = nullable(rawPrice, (item) =>
    positiveDecimal(item, 'INVALID_ORDER_PRICE', 'ORDER_PRICE_MUST_BE_POSITIVE'),
  )
  const quantity = integer(required(record, 'quantity', 'ORDER'), 1, 'INVALID_ORDER_QUANTITY')
  const filledQuantity = integer(
    required(record, 'filled_quantity', 'ORDER'),
    0,
    'INVALID_FILLED_QUANTITY',
  )
  const cancelledQuantity = integer(
    required(record, 'cancelled_quantity', 'ORDER'),
    0,
    'INVALID_CANCELLED_QUANTITY',
  )
  const remainingQuantity = integer(
    required(record, 'remaining_quantity', 'ORDER'),
    0,
    'INVALID_REMAINING_QUANTITY',
  )
  const state = oneOf(
    required(record, 'state', 'ORDER'),
    ['PENDING', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED'],
    'INVALID_ORDER_STATE',
  )

  if (orderType === 'LIMIT' && price === null) fail('LIMIT_PRICE_REQUIRED')
  if (orderType === 'MARKET' && price !== null) fail('MARKET_PRICE_MUST_BE_NULL')
  if (state === 'REJECTED') {
    if (filledQuantity !== 0 || cancelledQuantity !== 0 || remainingQuantity !== 0) {
      fail('REJECTED_ORDER_HAS_QUANTITY')
    }
  } else if (quantity !== filledQuantity + cancelledQuantity + remainingQuantity) {
    fail('ORDER_QUANTITY_MISMATCH')
  }

  if (
    (state === 'PENDING' || state === 'OPEN') &&
    (filledQuantity !== 0 || cancelledQuantity !== 0)
  ) {
    fail('OPEN_ORDER_HAS_TERMINAL_QUANTITY')
  }
  if (state === 'PARTIALLY_FILLED' && (filledQuantity <= 0 || remainingQuantity <= 0)) {
    fail('PARTIAL_ORDER_QUANTITY_INVALID')
  }
  if (
    state === 'FILLED' &&
    (filledQuantity !== quantity || cancelledQuantity !== 0 || remainingQuantity !== 0)
  ) {
    fail('FILLED_ORDER_QUANTITY_INVALID')
  }
  if (state === 'CANCELLED' && (cancelledQuantity <= 0 || remainingQuantity !== 0)) {
    fail('CANCELLED_ORDER_QUANTITY_INVALID')
  }

  return Object.freeze({
    client_order_id: uuid(required(record, 'client_order_id', 'ORDER'), 'INVALID_CLIENT_ORDER_ID'),
    request_id: uuid(required(record, 'request_id', 'ORDER'), 'INVALID_REQUEST_ID'),
    execution_id: uuid(required(record, 'execution_id', 'ORDER'), 'INVALID_EXECUTION_ID'),
    broker_order_no: nullable(required(record, 'broker_order_no', 'ORDER'), (item) =>
      key(item, 'INVALID_BROKER_ORDER_NO'),
    ),
    symbol: symbol(required(record, 'symbol', 'ORDER')),
    side: oneOf(required(record, 'side', 'ORDER'), ['BUY', 'SELL'], 'INVALID_ORDER_SIDE'),
    order_type: orderType,
    price,
    quantity,
    filled_quantity: filledQuantity,
    cancelled_quantity: cancelledQuantity,
    remaining_quantity: remainingQuantity,
    state,
  })
}

function parseFill(value: unknown): FillSnapshot {
  const record = object(
    value,
    ['fill_id', 'client_order_id', 'quantity', 'price', 'filled_at'],
    'FILL',
  )
  return Object.freeze({
    fill_id: uuid(required(record, 'fill_id', 'FILL'), 'INVALID_FILL_ID'),
    client_order_id: uuid(required(record, 'client_order_id', 'FILL'), 'INVALID_CLIENT_ORDER_ID'),
    quantity: integer(required(record, 'quantity', 'FILL'), 1, 'INVALID_FILL_QUANTITY'),
    price: positiveDecimal(
      required(record, 'price', 'FILL'),
      'INVALID_FILL_PRICE',
      'FILL_PRICE_MUST_BE_POSITIVE',
    ),
    filled_at: awareDatetime(required(record, 'filled_at', 'FILL'), 'INVALID_FILLED_AT'),
  })
}

function parseOperation(value: unknown): OperationStatus {
  const record = object(
    value,
    ['engine', 'live_trading_enabled', 'data_mode', 'reconciliation', 'last_event_at'],
    'OPERATION',
  )
  const engine = oneOf(
    required(record, 'engine', 'OPERATION'),
    ['ONLINE', 'OFFLINE', 'DEGRADED'],
    'INVALID_ENGINE_STATUS',
  )
  const liveTradingEnabled = required(record, 'live_trading_enabled', 'OPERATION')
  if (typeof liveTradingEnabled !== 'boolean') fail('INVALID_LIVE_TRADING_ENABLED')
  const dataMode = oneOf(
    required(record, 'data_mode', 'OPERATION'),
    ['MOCK', 'PAPER', 'LIVE'],
    'INVALID_DATA_MODE',
  )
  if (liveTradingEnabled && (engine !== 'ONLINE' || dataMode !== 'LIVE')) {
    fail('LIVE_TRADING_STATUS_INVALID')
  }
  return Object.freeze({
    engine,
    live_trading_enabled: liveTradingEnabled,
    data_mode: dataMode,
    reconciliation: oneOf(
      required(record, 'reconciliation', 'OPERATION'),
      ['OK', 'RECONCILING', 'RECONCILIATION_REQUIRED'],
      'INVALID_RECONCILIATION_STATUS',
    ),
    last_event_at: nullable(required(record, 'last_event_at', 'OPERATION'), (item) =>
      awareDatetime(item, 'INVALID_LAST_EVENT_AT'),
    ),
  })
}

export function parseContractBundle(value: unknown): ContractBundle {
  const record = object(
    value,
    ['schema_version', 'instrument', 'patterns', 'execution_config', 'order', 'fills', 'operation'],
    'CONTRACT_BUNDLE',
  )
  const schemaVersion = required(record, 'schema_version', 'CONTRACT_BUNDLE')
  if (schemaVersion !== 1) fail('INVALID_SCHEMA_VERSION')

  const rawPatterns = required(record, 'patterns', 'CONTRACT_BUNDLE')
  if (!Array.isArray(rawPatterns)) fail('PATTERNS_MUST_BE_ARRAY')
  const patterns = Object.freeze(rawPatterns.map(parsePattern))

  const rawFills = required(record, 'fills', 'CONTRACT_BUNDLE')
  if (!Array.isArray(rawFills)) fail('FILLS_MUST_BE_ARRAY')
  const fills = Object.freeze(rawFills.map(parseFill))

  const instrument = parseInstrument(required(record, 'instrument', 'CONTRACT_BUNDLE'))
  const executionConfig = parseExecutionConfig(
    required(record, 'execution_config', 'CONTRACT_BUNDLE'),
  )
  const order = parseOrder(required(record, 'order', 'CONTRACT_BUNDLE'))
  const operation = parseOperation(required(record, 'operation', 'CONTRACT_BUNDLE'))

  if (executionConfig.symbol !== instrument.symbol) fail('CONFIG_INSTRUMENT_MISMATCH')
  if (order.symbol !== instrument.symbol || order.execution_id !== executionConfig.execution_id) {
    fail('ORDER_EXECUTION_MISMATCH')
  }

  const patternByVersion = new Map<string, PatternVersion>()
  for (const pattern of patterns) {
    const patternKey = `${pattern.pattern_id}:${pattern.version}`
    if (patternByVersion.has(patternKey)) fail('DUPLICATE_PATTERN_VERSION')
    patternByVersion.set(patternKey, pattern)
  }
  for (const [reference, expectedSide] of [
    [executionConfig.buy_pattern, 'BUY'],
    [executionConfig.sell_pattern, 'SELL'],
  ] as const) {
    const pattern = patternByVersion.get(`${reference.pattern_id}:${reference.version}`)
    if (pattern === undefined) fail('PATTERN_REFERENCE_NOT_FOUND')
    if (pattern.side !== expectedSide) fail('PATTERN_SIDE_MISMATCH')
  }

  const fillIds = new Set<string>()
  let totalFilled = 0
  for (const fill of fills) {
    if (fillIds.has(fill.fill_id)) fail('DUPLICATE_FILL')
    fillIds.add(fill.fill_id)
    if (fill.client_order_id !== order.client_order_id) fail('FILL_ORDER_MISMATCH')
    totalFilled += fill.quantity
  }
  if (totalFilled !== order.filled_quantity) fail('FILL_TOTAL_MISMATCH')

  return Object.freeze({
    schema_version: 1,
    instrument,
    patterns,
    execution_config: executionConfig,
    order,
    fills,
    operation,
  })
}
