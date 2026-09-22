import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { parseContractBundle } from '../contracts/models'

const fixturePath = resolve(process.cwd(), '../contracts/fixtures/step02-contract.json')

function loadFixture(): unknown {
  return JSON.parse(readFileSync(fixturePath, 'utf8'))
}

describe('shared trading contracts', () => {
  it('accepts the same contract fixture as the Python model', () => {
    const bundle = parseContractBundle(loadFixture())

    expect(bundle.instrument.symbol).toBe('005930')
    expect(bundle.execution_config.state).toBe('ACCEPTED')
    expect(bundle.order.filled_quantity).toBe(
      bundle.fills.reduce((total, fill) => total + fill.quantity, 0),
    )
  })

  it('rejects an accepted config whose applied version does not match', () => {
    const payload = structuredClone(loadFixture()) as {
      execution_config: { applied_version: number }
    }
    payload.execution_config.applied_version = 1

    expect(() => parseContractBundle(payload)).toThrowError('ACCEPTED_VERSION_MISMATCH')
  })

  it('rejects quantities outside the safe integer range', () => {
    const payload = structuredClone(loadFixture()) as {
      order: {
        quantity: number
        filled_quantity: number
        remaining_quantity: number
      }
    }
    payload.order.quantity = 9_007_199_254_740_992
    payload.order.filled_quantity = 9_007_199_254_740_992
    payload.order.remaining_quantity = 1

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_ORDER_QUANTITY')
  })

  it('rejects impossible calendar dates', () => {
    const payload = structuredClone(loadFixture()) as {
      execution_config: { requested_at: string; expires_at: string }
    }
    payload.execution_config.requested_at = '2026-02-30T00:00:00Z'
    payload.execution_config.expires_at = '2026-03-03T00:00:00Z'

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_REQUESTED_AT')
  })

  it.each([
    1_795_478_400,
    '2026-09-22 00:00:00Z',
    '2026-09-22T00:00:00z',
    '2026-09-22T00:00:00+0900',
  ])('rejects noncanonical datetime input %j', (invalidRequestedAt) => {
    const payload = structuredClone(loadFixture()) as {
      execution_config: { requested_at: unknown }
    }
    payload.execution_config.requested_at = invalidRequestedAt

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_REQUESTED_AT')
  })

  it('rejects datetime precision beyond milliseconds', () => {
    const payload = structuredClone(loadFixture()) as {
      execution_config: { requested_at: string }
    }
    payload.execution_config.requested_at = '2026-09-22T00:00:00.000001Z'

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_REQUESTED_AT')
  })

  it.each(['2026-09-22T00:00:00.1Z', '2026-09-22T00:00:00.12Z', '2026-09-22T00:00:00.123Z'])(
    'accepts one to three fractional-second digits: %s',
    (requestedAt) => {
      const payload = structuredClone(loadFixture()) as {
        execution_config: { requested_at: string }
      }
      payload.execution_config.requested_at = requestedAt

      expect(parseContractBundle(payload).execution_config.requested_at).toBe(requestedAt)
    },
  )

  it('rejects a boolean schema version', () => {
    const payload = structuredClone(loadFixture()) as { schema_version: unknown }
    payload.schema_version = true

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_SCHEMA_VERSION')
  })

  it('accepts JSON numeric schema version one', () => {
    const payload = structuredClone(loadFixture()) as { schema_version: number }
    payload.schema_version = 1.0

    expect(parseContractBundle(payload).schema_version).toBe(1)
  })

  it('requires an explicit schema version', () => {
    const payload = structuredClone(loadFixture()) as { schema_version?: number }
    delete payload.schema_version

    expect(() => parseContractBundle(payload)).toThrowError(
      'CONTRACT_BUNDLE_SCHEMA_VERSION_REQUIRED',
    )
  })

  it('rejects an integer in the boolean operation field', () => {
    const payload = structuredClone(loadFixture()) as {
      operation: { live_trading_enabled: unknown }
    }
    payload.operation.live_trading_enabled = 0

    expect(() => parseContractBundle(payload)).toThrowError('INVALID_LIVE_TRADING_ENABLED')
  })

  it('normalizes UUID casing before cross-reference checks', () => {
    const payload = structuredClone(loadFixture()) as {
      patterns: Array<{ pattern_id: string }>
      execution_config: { buy_pattern: { pattern_id: string } }
    }
    const pattern = payload.patterns[0]
    if (pattern === undefined) throw new Error('fixture must contain a buy pattern')
    pattern.pattern_id = 'AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA'
    payload.execution_config.buy_pattern.pattern_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

    const bundle = parseContractBundle(payload)

    expect(bundle.patterns[0]?.pattern_id).toBe('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
  })
})
