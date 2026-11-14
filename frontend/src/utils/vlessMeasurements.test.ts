import { describe, expect, it } from 'vitest'
import type { VlessProfileDelayItem, VlessSelectionDelaySample } from '../types/api'
import {
  getLatestMeasurementDelay,
  getLatestMeasurementSource,
  sortProfilesByLatestMeasurement,
} from './vlessMeasurements'

function manualSample(overrides: Partial<VlessProfileDelayItem> = {}): VlessProfileDelayItem {
  return {
    profile_id: 1,
    delay_ms: 250,
    reachable: true,
    first_failed_at: null,
    last_checked_at: '2026-10-25T08:00:00Z',
    last_success_at: '2026-10-25T08:00:00Z',
    last_outage_started_at: null,
    last_recovered_at: null,
    last_outage_duration_seconds: null,
    consecutive_failures: 0,
    unavailable_seconds: null,
    ...overrides,
  }
}

function urltestSample(overrides: Partial<VlessSelectionDelaySample> = {}): VlessSelectionDelaySample {
  return {
    delay_ms: 320,
    observed_at: '2026-10-25T08:01:00Z',
    ...overrides,
  }
}

describe('getLatestMeasurementSource', () => {
  it('uses URLTest when its measurement is newer than manual testing', () => {
    expect(getLatestMeasurementSource(
      manualSample({ last_checked_at: '2026-10-25T08:00:00Z' }),
      urltestSample({ observed_at: '2026-10-25T08:01:00Z' }),
    )).toBe('urltest')
  })

  it('uses a newer manual measurement when it was checked after URLTest', () => {
    expect(getLatestMeasurementSource(
      manualSample({ last_checked_at: '2026-10-25T08:02:00Z' }),
      urltestSample({ observed_at: '2026-10-25T08:01:00Z' }),
    )).toBe('manual')
  })

  it('prefers URLTest when both timestamps are equal', () => {
    const timestamp = '2026-10-25T08:01:00Z'
    expect(getLatestMeasurementSource(
      manualSample({ last_checked_at: timestamp }),
      urltestSample({ observed_at: timestamp }),
    )).toBe('urltest')
  })

  it('falls back to manual data when there is no URLTest sample', () => {
    expect(getLatestMeasurementSource(manualSample(), undefined)).toBe('manual')
  })

  it('uses a URLTest sample with unknown observation time instead of inventing another source', () => {
    expect(getLatestMeasurementSource(
      manualSample({ last_checked_at: null }),
      urltestSample({ observed_at: null }),
    )).toBe('urltest')
  })

  it('returns null when neither source has measurement data', () => {
    expect(getLatestMeasurementSource(undefined, undefined)).toBeNull()
  })
})

describe('getLatestMeasurementDelay', () => {
  it('returns the selected URLTest latency', () => {
    expect(getLatestMeasurementDelay('urltest', manualSample({ delay_ms: 90 }), urltestSample({ delay_ms: 320 }))).toBe(320)
  })

  it('uses manual latency only when manual is the selected source and reachable', () => {
    expect(getLatestMeasurementDelay('manual', manualSample({ delay_ms: 245 }), urltestSample())).toBe(245)
  })

  it('treats unreachable manual checks as unknown latency even when an old delay remains', () => {
    expect(getLatestMeasurementDelay('manual', manualSample({ reachable: false, delay_ms: 40 }), undefined)).toBe(Number.POSITIVE_INFINITY)
  })

  it('treats a URLTest sample without a successful delay as unknown latency', () => {
    expect(getLatestMeasurementDelay('urltest', manualSample({ delay_ms: 180 }), urltestSample({ delay_ms: null }))).toBe(Number.POSITIVE_INFINITY)
  })

  it('treats a missing source as unknown latency', () => {
    expect(getLatestMeasurementDelay(null, undefined, undefined)).toBe(Number.POSITIVE_INFINITY)
  })
})

describe('sortProfilesByLatestMeasurement', () => {
  const profiles = [
    { id: 9, name: 'unknown' },
    { id: 4, name: 'slower' },
    { id: 2, name: 'fast' },
    { id: 3, name: 'same latency, lower ID' },
  ]

  it('sorts by effective latency and uses profile ID as deterministic tie-breaker', () => {
    const delays: Record<number, number> = { 4: 320, 2: 180, 3: 180, 9: Number.POSITIVE_INFINITY }
    expect(sortProfilesByLatestMeasurement(profiles, (profile) => delays[profile.id]).map((profile) => profile.id))
      .toEqual([2, 3, 4, 9])
  })

  it('puts missing measurements last and does not mutate the original array', () => {
    const originalIds = profiles.map((profile) => profile.id)
    const sorted = sortProfilesByLatestMeasurement(profiles, (profile) => profile.id === 4 ? 320 : Number.POSITIVE_INFINITY)
    expect(sorted.map((profile) => profile.id)).toEqual([4, 2, 3, 9])
    expect(profiles.map((profile) => profile.id)).toEqual(originalIds)
  })

  it('re-sorts after a newer URLTest sample changes a profile latency', () => {
    const samples: Record<number, VlessSelectionDelaySample> = {
      2: urltestSample({ delay_ms: 180 }),
      4: urltestSample({ delay_ms: 320 }),
    }
    const sortNow = () => sortProfilesByLatestMeasurement(profiles, (profile) => {
      const sample = samples[profile.id]
      return typeof sample?.delay_ms === 'number' ? sample.delay_ms : Number.POSITIVE_INFINITY
    }).map((profile) => profile.id)

    expect(sortNow()).toEqual([2, 4, 3, 9])
    samples[4] = urltestSample({ delay_ms: 120, observed_at: '2026-10-25T08:02:00Z' })
    expect(sortNow()).toEqual([4, 2, 3, 9])
  })
})
