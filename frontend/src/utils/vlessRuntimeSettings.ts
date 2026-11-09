import type { VlessRuntimeSettings } from '../types/api'

export function normalizeUrltestToleranceMs(value: unknown): number {
  const parsed = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim() !== ''
      ? Number(value)
      : Number.NaN
  if (!Number.isFinite(parsed)) return 50
  return Math.max(0, Math.min(5000, Math.round(parsed)))
}

export function normalizeVlessRuntimeSettings(
  value: Partial<VlessRuntimeSettings> | null | undefined,
): VlessRuntimeSettings {
  const interval = value?.urltest_interval
  const allowedIntervals: VlessRuntimeSettings['urltest_interval'][] = [
    '30s', '1m', '2m', '3m', '5m', '10m',
  ]
  return {
    urltest_interval: interval && allowedIntervals.includes(interval) ? interval : '3m',
    urltest_tolerance_ms: normalizeUrltestToleranceMs(
      (value as { urltest_tolerance_ms?: unknown } | null | undefined)?.urltest_tolerance_ms,
    ),
  }
}

/** Normalize an API response before rendering it in the settings controls. */
export function normalizeVlessRuntimeSettingsFromApi(
  value: Partial<VlessRuntimeSettings> | null | undefined,
): VlessRuntimeSettings {
  return normalizeVlessRuntimeSettings(value)
}

/** Normalize the exact payload sent to the save endpoint. */
export function prepareVlessRuntimeSettingsForSave(
  value: Partial<VlessRuntimeSettings> | null | undefined,
): VlessRuntimeSettings {
  return normalizeVlessRuntimeSettings(value)
}
