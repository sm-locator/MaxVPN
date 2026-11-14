import type { VlessProfileDelayItem, VlessSelectionDelaySample } from '../types/api'

export type LatestMeasurementSource = 'manual' | 'urltest' | null

/** Chooses the measurement with the later timestamp. Ties intentionally favor URLTest. */
export function getLatestMeasurementSource(
  manual: VlessProfileDelayItem | undefined,
  urltest: VlessSelectionDelaySample | undefined,
): LatestMeasurementSource {
  const manualTime = manual?.last_checked_at ? Date.parse(manual.last_checked_at) : Number.NaN
  const urltestTime = urltest?.observed_at ? Date.parse(urltest.observed_at) : Number.NaN
  const hasManualTime = Number.isFinite(manualTime)
  const hasUrltestTime = Number.isFinite(urltestTime)

  if (hasManualTime && hasUrltestTime) return manualTime > urltestTime ? 'manual' : 'urltest'
  if (hasManualTime) return 'manual'
  if (hasUrltestTime) return 'urltest'
  if (urltest) return 'urltest'
  if (manual?.last_checked_at) return 'manual'
  return null
}

/** Returns the usable latency for the selected source, or +Infinity for unknown/unreachable samples. */
export function getLatestMeasurementDelay(
  source: LatestMeasurementSource,
  manual: VlessProfileDelayItem | undefined,
  urltest: VlessSelectionDelaySample | undefined,
): number {
  if (source === 'manual') {
    return manual?.reachable && typeof manual.delay_ms === 'number'
      ? manual.delay_ms
      : Number.POSITIVE_INFINITY
  }
  if (source === 'urltest') {
    return typeof urltest?.delay_ms === 'number' ? urltest.delay_ms : Number.POSITIVE_INFINITY
  }
  return Number.POSITIVE_INFINITY
}

/** Sorts a copy by effective latency; profiles without a usable latency stay last, ties use local profile ID. */
export function sortProfilesByLatestMeasurement<T extends { id: number }>(
  profiles: readonly T[],
  getDelay: (profile: T) => number,
): T[] {
  return [...profiles].sort((a, b) => {
    const aDelay = getDelay(a)
    const bDelay = getDelay(b)
    const aKnown = Number.isFinite(aDelay)
    const bKnown = Number.isFinite(bDelay)
    if (aKnown && bKnown && aDelay !== bDelay) return aDelay - bDelay
    if (aKnown !== bKnown) return aKnown ? -1 : 1
    return a.id - b.id
  })
}
