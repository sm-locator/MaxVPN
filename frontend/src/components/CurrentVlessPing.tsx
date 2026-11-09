import { useEffect, useState } from 'react'
import { getVlessSelectionHistory } from '../api/client'
import type { VlessSelectionHistoryResponse } from '../types/api'

interface CurrentVlessPingProps {
  enabled: boolean
  activeOutbound: string | null | undefined
}

type Snapshot = VlessSelectionHistoryResponse['current']

function intervalMilliseconds(value: string | null | undefined): number {
  if (!value) return 180_000
  const match = value.trim().match(/^(\d+(?:\.\d+)?)(ms|s|m|h)$/i)
  if (!match) return 180_000

  const amount = Number(match[1])
  const factors: Record<string, number> = {
    ms: 1,
    s: 1_000,
    m: 60_000,
    h: 3_600_000,
  }
  return amount * factors[match[2].toLowerCase()]
}

function getFreshPing(snapshot: Snapshot, activeOutbound: string | null | undefined): number | null {
  if (!snapshot) return null

  const delay = snapshot.active_delay_ms
  const sampleTime = Date.parse(snapshot.active_delay_observed_at ?? '')
  const snapshotTime = Date.parse(snapshot.observed_at)
  const now = Date.now()
  const limit = intervalMilliseconds(snapshot.urltest_interval)

  if (
    !activeOutbound ||
    snapshot.active_outbound !== activeOutbound ||
    !snapshot.active_outbound ||
    !/^vless-profile-[1-9][0-9]*$/.test(snapshot.active_outbound) ||
    typeof delay !== 'number' ||
    !Number.isFinite(delay) ||
    delay <= 0 ||
    !Number.isFinite(sampleTime) ||
    !Number.isFinite(snapshotTime)
  ) {
    return null
  }

  const sampleAge = now - sampleTime
  const snapshotAge = now - snapshotTime

  if (
    sampleAge < -10_000 ||
    sampleAge > limit ||
    snapshotAge < -10_000 ||
    snapshotAge > limit
  ) {
    return null
  }

  return Math.round(delay)
}

export function CurrentVlessPing({ enabled, activeOutbound }: CurrentVlessPingProps) {
  const [snapshot, setSnapshot] = useState<Snapshot>(null)

  useEffect(() => {
    let cancelled = false

    if (!enabled || !activeOutbound) {
      return
    }

    const refresh = async () => {
      try {
        const history = await getVlessSelectionHistory()
        if (!cancelled) setSnapshot(history.current)
      } catch {
        if (!cancelled) setSnapshot(null)
      }
    }

    void refresh()
    const timer = window.setInterval(() => void refresh(), 15_000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [enabled, activeOutbound])

  if (!enabled) return null

  const ping = getFreshPing(snapshot, activeOutbound)

  return (
    <small
      className="vpn-runtime-ping"
      style={{ display: 'block', marginTop: 6, fontWeight: 600, opacity: 0.8 }}
      aria-label={ping === null ? 'Пинг текущего сервера недоступен' : `Пинг текущего сервера ${ping} миллисекунд`}
    >
      Пинг: {ping === null ? '—' : `${ping} мс`}
    </small>
  )
}
