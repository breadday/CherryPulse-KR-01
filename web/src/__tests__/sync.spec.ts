import { describe, expect, it } from 'vitest'

import {
  applyReadEvent,
  createSyncState,
  enqueueOutboxCommand,
  markConnection,
  summarizeSync,
} from '../sync/state'

describe('sync state reducer', () => {
  it('applies each stream event once and ignores reverse delivery', () => {
    let state = createSyncState()

    state = applyReadEvent(state, {
      eventId: 'evt-2',
      stream: 'board',
      sequence: 2,
      occurredAt: '2026-09-22T14:00:02Z',
      payload: { holding: 1 },
    })
    state = applyReadEvent(state, {
      eventId: 'evt-1',
      stream: 'board',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:01Z',
      payload: { holding: 0 },
    })
    state = applyReadEvent(state, {
      eventId: 'evt-2',
      stream: 'board',
      sequence: 2,
      occurredAt: '2026-09-22T14:00:02Z',
      payload: { holding: 99 },
    })

    expect(state.readModel).toEqual({ board: { holding: 1 } })
    expect(state.lastSequenceByStream.board).toBe(2)
    expect(state.appliedEventIds).toEqual(['evt-2'])
  })

  it('keeps read state separate from pending outbox commands', () => {
    let state = createSyncState()
    state = enqueueOutboxCommand(state, {
      commandId: 'cmd-1',
      kind: 'REFRESH_BOARD',
      createdAt: '2026-09-22T14:00:00Z',
    })
    state = applyReadEvent(state, {
      eventId: 'evt-1',
      stream: 'board',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:01Z',
      payload: { holding: 1 },
    })

    expect(state.readModel).toEqual({ board: { holding: 1 } })
    expect(state.outbox).toHaveLength(1)
    expect(state.outbox[0]?.commandId).toBe('cmd-1')
  })

  it('preserves read state when independent streams deliver events', () => {
    let state = createSyncState()
    state = applyReadEvent(state, {
      eventId: 'board-1',
      stream: 'board',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:01Z',
      payload: { holding: 1 },
    })
    state = applyReadEvent(state, {
      eventId: 'operation-1',
      stream: 'operation',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:02Z',
      payload: { holding: 2 },
    })

    expect(state.readModel).toEqual({
      board: { holding: 1 },
      operation: { holding: 2 },
    })
  })

  it('ignores future timestamps and invalid sequence metadata', () => {
    let state = createSyncState()
    state = applyReadEvent(state, {
      eventId: 'future',
      stream: 'board',
      sequence: 1,
      occurredAt: '2099-01-01T00:00:00Z',
      payload: { holding: 1 },
    })
    state = applyReadEvent(state, {
      eventId: 'nan',
      stream: 'board',
      sequence: Number.NaN,
      occurredAt: '2026-09-22T14:00:01Z',
      payload: { holding: 2 },
    })

    expect(state.readModel).toEqual({})
    expect(state.lastSequenceByStream).toEqual({})
  })

  it('keeps the newest accepted timestamp across streams', () => {
    let state = createSyncState()
    state = applyReadEvent(state, {
      eventId: 'operation-1',
      stream: 'operation',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:02Z',
      payload: { engine: 'ONLINE' },
    })
    state = applyReadEvent(state, {
      eventId: 'board-1',
      stream: 'board',
      sequence: 1,
      occurredAt: '2026-09-22T14:00:01Z',
      payload: { holding: 1 },
    })

    expect(state.lastEventAt).toBe('2026-09-22T14:00:02Z')
  })

  it('rejects timestamps outside the shared aware ISO contract', () => {
    let state = createSyncState()
    for (const occurredAt of [
      '09/22/2026',
      '2026-09-22',
      '0',
      '2026-02-30T00:00:00Z',
      '2024-02-30T00:00:00Z',
      '2026-09-22T24:00:00Z',
      '0000-01-01T00:00:00Z',
    ]) {
      state = applyReadEvent(state, {
        eventId: occurredAt,
        stream: 'board',
        sequence: 1,
        occurredAt,
        payload: { holding: 1 },
      })
    }

    expect(state.readModel).toEqual({})
    expect(state.lastEventAt).toBeNull()
  })

  it('ignores events with blank identifiers and streams', () => {
    let state = createSyncState()
    for (const [eventId = '', stream = ''] of [
      ['', 'board'],
      ['evt-1', ''],
    ]) {
      state = applyReadEvent(state, {
        eventId,
        stream,
        sequence: 1,
        occurredAt: '2026-09-22T14:00:01Z',
        payload: { holding: 1 },
      })
    }

    expect(state.readModel).toEqual({})
    expect(state.appliedEventIds).toEqual([])
  })

  it('rejects invalid freshness thresholds', () => {
    expect(() => createSyncState(0)).toThrow('INVALID_STALE_AFTER_MS')
    expect(() => createSyncState(Number.NaN)).toThrow('INVALID_STALE_AFTER_MS')
    expect(() => createSyncState(Number.POSITIVE_INFINITY)).toThrow('INVALID_STALE_AFTER_MS')
  })

  it('reports offline and delayed states without claiming live readiness', () => {
    let state = createSyncState()
    state = markConnection(state, 'OFFLINE')
    expect(summarizeSync(state, Date.parse('2026-09-22T14:01:00Z'))).toEqual({
      connection: 'OFFLINE',
      freshness: 'STALE',
      pendingCommands: 0,
    })

    state = markConnection(
      applyReadEvent(state, {
        eventId: 'evt-1',
        stream: 'board',
        sequence: 1,
        occurredAt: '2026-09-22T14:00:50Z',
        payload: { holding: 1 },
      }),
      'ONLINE',
    )
    expect(summarizeSync(state, Date.parse('2026-09-22T14:01:00Z'))).toEqual({
      connection: 'ONLINE',
      freshness: 'FRESH',
      pendingCommands: 0,
    })
  })
})
