export type SyncConnection = 'ONLINE' | 'OFFLINE' | 'DEGRADED'
export type SyncFreshness = 'FRESH' | 'DELAYED' | 'STALE'

export type ReadEvent = Readonly<{
  eventId: string
  stream: string
  sequence: number
  occurredAt: string
  payload: Readonly<Record<string, unknown>>
}>

export type OutboxCommand = Readonly<{
  commandId: string
  kind: string
  createdAt: string
}>

export type SyncState = Readonly<{
  connection: SyncConnection
  readModel: Readonly<Record<string, Readonly<Record<string, unknown>>>>
  lastSequenceByStream: Readonly<Record<string, number>>
  appliedEventIds: readonly string[]
  outbox: readonly OutboxCommand[]
  lastEventAt: string | null
  staleAfterMs: number
}>

export type SyncSummary = Readonly<{
  connection: SyncConnection
  freshness: SyncFreshness
  pendingCommands: number
}>

const AWARE_DATETIME_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,3})?(Z|([+-])(\d{2}):(\d{2}))$/
const IDENTIFIER_PATTERN = /^[!-~]+$/

function parseAwareTimestamp(value: string): number | null {
  const match = AWARE_DATETIME_PATTERN.exec(value)
  if (!match) return null
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , , offsetHourText, offsetMinuteText] = match
  const year = Number(yearText)
  const month = Number(monthText)
  const day = Number(dayText)
  const hour = Number(hourText)
  const minute = Number(minuteText)
  const second = Number(secondText)
  const offsetHour = offsetHourText === undefined ? 0 : Number(offsetHourText)
  const offsetMinute = offsetMinuteText === undefined ? 0 : Number(offsetMinuteText)
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0)
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

  const maxDay = daysInMonth[month - 1] ?? 0

  if (
    year < 1 ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > maxDay ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return null
  }

  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function createSyncState(staleAfterMs = 30_000): SyncState {
  if (!Number.isFinite(staleAfterMs) || staleAfterMs <= 0) {
    throw new Error('INVALID_STALE_AFTER_MS')
  }
  return {
    connection: 'OFFLINE',
    readModel: {},
    lastSequenceByStream: {},
    appliedEventIds: [],
    outbox: [],
    lastEventAt: null,
    staleAfterMs,
  }
}

export function applyReadEvent(state: SyncState, event: ReadEvent): SyncState {
  const occurredAtMs = parseAwareTimestamp(event.occurredAt)
  if (
    !IDENTIFIER_PATTERN.test(event.eventId) ||
    !IDENTIFIER_PATTERN.test(event.stream) ||
    !Number.isSafeInteger(event.sequence) ||
    event.sequence <= 0 ||
    occurredAtMs === null ||
    occurredAtMs > Date.now()
  ) {
    return state
  }
  const lastSequence = state.lastSequenceByStream[event.stream] ?? 0
  if (state.appliedEventIds.includes(event.eventId) || event.sequence <= lastSequence) {
    return state
  }
  const previousEventMs = state.lastEventAt === null ? -Infinity : parseAwareTimestamp(state.lastEventAt)

  return {
    ...state,
    readModel: {
      ...state.readModel,
      [event.stream]: { ...event.payload },
    },
    lastSequenceByStream: {
      ...state.lastSequenceByStream,
      [event.stream]: event.sequence,
    },
    appliedEventIds: [...state.appliedEventIds, event.eventId],
    lastEventAt:
      previousEventMs === null || occurredAtMs > previousEventMs ? event.occurredAt : state.lastEventAt,
  }
}

export function enqueueOutboxCommand(state: SyncState, command: OutboxCommand): SyncState {
  if (state.outbox.some((item) => item.commandId === command.commandId)) return state
  return { ...state, outbox: [...state.outbox, command] }
}

export function markConnection(state: SyncState, connection: SyncConnection): SyncState {
  return { ...state, connection }
}

export function summarizeSync(state: SyncState, nowMs: number): SyncSummary {
  const eventMs = state.lastEventAt === null ? null : Date.parse(state.lastEventAt)
  const ageMs = eventMs === null || Number.isNaN(eventMs) ? Infinity : Math.max(0, nowMs - eventMs)
  const freshness: SyncFreshness =
    eventMs !== null && eventMs > nowMs
      ? 'STALE'
      : ageMs <= state.staleAfterMs
      ? 'FRESH'
      : ageMs <= state.staleAfterMs * 3
        ? 'DELAYED'
        : 'STALE'

  return {
    connection: state.connection,
    freshness,
    pendingCommands: state.outbox.length,
  }
}
