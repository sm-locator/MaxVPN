import type { VpnTrafficMode } from '../types/api'

interface TrafficModeCardProps {
  currentMode: VpnTrafficMode | null
  busy: boolean
  error: string | null
  onChange: (mode: VpnTrafficMode) => void
}

const modes: Array<{ value: VpnTrafficMode; title: string; description: string }> = [
  { value: 'wan', title: 'WAN', description: 'Напрямую через провайдера' },
  { value: 'vpn', title: 'AmneziaWG', description: 'Существующий VPN-режим' },
  { value: 'vless', title: 'VLESS + REALITY', description: 'Через sing-box и maxvpn0' },
]

export function TrafficModeCard({ currentMode, busy, error, onChange }: TrafficModeCardProps) {
  return (
    <section className="vless-card" aria-labelledby="traffic-mode-title">
      <div className="vless-card-header">
        <div>
          <div className="vless-eyebrow">LAN TRAFFIC</div>
          <h2 id="traffic-mode-title">Режим маршрутизации</h2>
          <p className="vless-subtitle">
            Выберите, через какой выход будет направляться трафик домашней сети.
          </p>
        </div>
        <strong className="is-ready">
          {currentMode === 'wan' ? 'WAN' : currentMode === 'vpn' ? 'AmneziaWG' : currentMode === 'vless' ? 'VLESS' : 'Проверка…'}
        </strong>
      </div>
      <div className="vless-button-row">
        {modes.map((mode) => (
          <button
            key={mode.value}
            type="button"
            className={currentMode === mode.value ? 'button button-primary' : 'button button-secondary'}
            onClick={() => onChange(mode.value)}
            disabled={busy || currentMode === mode.value || currentMode === null}
            title={mode.description}
          >
            {busy ? 'Переключение…' : mode.title}
          </button>
        ))}
      </div>
      {currentMode === 'vless' && (
        <p className="muted">
          IPv4 DIRECT-исключения сохраняются. IPv6-трафик из LAN блокируется до отдельной реализации и проверки маршрута через VLESS.
        </p>
      )}
      {error && <div className="vless-alert vless-alert-error" role="alert">{error}</div>}
    </section>
  )
}
