import { describe, expect, it } from 'vitest'
import {
  normalizeUrltestToleranceMs,
  normalizeVlessRuntimeSettings,
  normalizeVlessRuntimeSettingsFromApi,
  prepareVlessRuntimeSettingsForSave,
} from './vlessRuntimeSettings'

describe('normalizeUrltestToleranceMs', () => {
  it.each([
    [50, 50],
    [0, 0],
    [5000, 5000],
    ['125', 125],
    [' 75 ', 75],
    [123.6, 124],
    [-25, 0],
    [6000, 5000],
  ])('normalizes %s to %i', (input, expected) => {
    expect(normalizeUrltestToleranceMs(input)).toBe(expected)
  })

  it.each([undefined, null, '', '   ', 'not-a-number', Number.NaN, Number.POSITIVE_INFINITY])(
    'uses the default 50 ms for invalid input %s',
    (input) => {
      expect(normalizeUrltestToleranceMs(input)).toBe(50)
    },
  )
})

describe('normalizeVlessRuntimeSettings', () => {
  it('uses safe defaults when the API response is missing', () => {
    expect(normalizeVlessRuntimeSettings(undefined)).toEqual({
      urltest_interval: '3m',
      urltest_tolerance_ms: 50,
    })
  })

  it('preserves supported settings', () => {
    expect(normalizeVlessRuntimeSettings({
      urltest_interval: '5m',
      urltest_tolerance_ms: 125,
    })).toEqual({
      urltest_interval: '5m',
      urltest_tolerance_ms: 125,
    })
  })

  it('falls back for an unsupported interval and malformed tolerance', () => {
    expect(normalizeVlessRuntimeSettings({
      urltest_interval: 'invalid' as unknown as '3m',
      urltest_tolerance_ms: Number.NaN,
    })).toEqual({
      urltest_interval: '3m',
      urltest_tolerance_ms: 50,
    })
  })

  it('clamps out-of-range tolerance values', () => {
    expect(normalizeVlessRuntimeSettings({
      urltest_interval: '1m',
      urltest_tolerance_ms: 9000,
    })).toEqual({
      urltest_interval: '1m',
      urltest_tolerance_ms: 5000,
    })
  })
})


describe('normalizeVlessRuntimeSettingsFromApi', () => {
  it('keeps the default tolerance when the API omits it', () => {
    expect(normalizeVlessRuntimeSettingsFromApi({ urltest_interval: '3m' })).toEqual({
      urltest_interval: '3m',
      urltest_tolerance_ms: 50,
    })
  })

  it('normalizes malformed API settings before they reach the input', () => {
    expect(normalizeVlessRuntimeSettingsFromApi({
      urltest_interval: 'not-supported' as unknown as '3m',
      urltest_tolerance_ms: 'not-a-number' as unknown as number,
    })).toEqual({
      urltest_interval: '3m',
      urltest_tolerance_ms: 50,
    })
  })
})


describe('prepareVlessRuntimeSettingsForSave', () => {
  it('normalizes the outgoing payload before the API call', () => {
    expect(prepareVlessRuntimeSettingsForSave({
      urltest_interval: '3m',
      urltest_tolerance_ms: 125,
    })).toEqual({
      urltest_interval: '3m',
      urltest_tolerance_ms: 125,
    })
  })

  it('uses 50 ms when the edited value is missing or malformed', () => {
    expect(prepareVlessRuntimeSettingsForSave({
      urltest_interval: '3m',
    })).toEqual({ urltest_interval: '3m', urltest_tolerance_ms: 50 })
    expect(prepareVlessRuntimeSettingsForSave({
      urltest_interval: '3m',
      urltest_tolerance_ms: 'broken' as unknown as number,
    })).toEqual({ urltest_interval: '3m', urltest_tolerance_ms: 50 })
  })

  it('clamps the outgoing tolerance to the supported range', () => {
    expect(prepareVlessRuntimeSettingsForSave({
      urltest_interval: '5m',
      urltest_tolerance_ms: 99999,
    })).toEqual({ urltest_interval: '5m', urltest_tolerance_ms: 5000 })
  })
})
