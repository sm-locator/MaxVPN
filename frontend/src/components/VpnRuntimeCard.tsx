import type { VlessRuntime, VpnRuntime } from '../types/api'
import { ServerCountryLabel } from './ServerCountryLabel'
import { CurrentVlessPing } from './CurrentVlessPing'

interface VpnRuntimeCardProps {
  runtime: VpnRuntime | null
  vlessRuntime: VlessRuntime | null
  starting: boolean
  stopping: boolean
  error: string | null
  onStart: () => void
  onStop: () => void
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`
  }

  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value
  let unitIndex = -1

  do {
    size /= 1024
    unitIndex += 1
  } while (size >= 1024 && unitIndex < units.length - 1)

  return `${size.toFixed(1)} ${units[unitIndex]}`
}

function formatHandshakeAge(seconds: number | null): string {
  if (seconds === null) {
    return 'Нет данных'
  }

  if (seconds < 60) {
    return `${seconds} сек. назад`
  }

  const minutes = Math.floor(seconds / 60)

  if (minutes < 60) {
    return `${minutes} мин. назад`
  }

  const hours = Math.floor(minutes / 60)
  return `${hours} ч. назад`
}

function formatCheckedAt(value: string): string {
  return new Date(value).toLocaleTimeString('ru-RU')
}

function getVlessServerText(runtime: VlessRuntime | null): string {
  if (!runtime) return 'Не удалось проверить'
  if (!runtime.running) return 'Не используется'
  if (runtime.active_server_address) {
    const name = runtime.active_server_name
      ? `${runtime.active_server_name} · `
      : ''
    return `${name}${runtime.active_server_address}:${runtime.active_server_port ?? '—'}`
  }
  if (runtime.selection_mode === 'unknown') return 'Активный узел не определён'
  if (runtime.selection_mode === 'manual') return 'Выбранный узел не определён'
  return 'Автовыбор · узел определяется'
}

function getVlessProcessText(runtime: VlessRuntime | null): string {
  if (!runtime) return 'Не удалось проверить'
  if (runtime.running) return 'Запущен'
  return runtime.installed ? 'Остановлен' : 'Не установлен'
}

function getVlessSelectionModeText(runtime: VlessRuntime | null): string {
  if (!runtime) return 'Нет данных'
  if (runtime.selection_mode === 'manual') return 'Ручной'
  if (runtime.selection_mode === 'auto') return 'Автоматический'
  if (runtime.selection_mode === 'legacy') return 'Одиночный профиль'
  return 'Не определён'
}

function getVlessConfigModeText(runtime: VlessRuntime | null): string {
  if (!runtime) return 'Нет данных'
  if (runtime.runtime_config_mode === 'multi_profile') return 'Несколько профилей'
  if (runtime.runtime_config_mode === 'single_profile') return 'Одиночный профиль'
  return 'Не определён'
}

function getVpnTitle(
  runtime: VpnRuntime,
  vlessRuntime: VlessRuntime | null,
  starting: boolean,
  stopping: boolean,
): string {
  if (starting) {
    return 'Запуск VPN…'
  }

  if (stopping) {
    return 'Остановка VPN…'
  }

  if (runtime.traffic_mode === 'wan') {
    return 'VPN выключен'
  }

  if (runtime.traffic_mode === 'vless') {
    if (!vlessRuntime) return 'Состояние VLESS недоступно'
    if (!vlessRuntime.running) return 'VLESS выбран, но sing-box остановлен'
    if (!vlessRuntime.lan_routing_enabled) return 'LAN-маршрут через VLESS не подтверждён'
    return 'Маршрутизация через VLESS'
  }

  if (!runtime.interface_up) {
    return 'VPN требует внимания'
  }

  if (runtime.reason === 'no_handshake') {
    return 'VPN подключается…'
  }

  if (!runtime.healthy) {
    return 'VPN требует внимания'
  }

  return 'VPN подключён'
}

function getVpnSubtitle(runtime: VpnRuntime, vlessRuntime: VlessRuntime | null): string {
  if (runtime.traffic_mode === 'wan') {
    return 'LAN-трафик идёт напрямую через WAN'
  }

  if (runtime.traffic_mode === 'vless') {
    if (!vlessRuntime) return 'Не удалось подтвердить состояние sing-box; статус туннеля неизвестен.'
    if (!vlessRuntime.running) return 'LAN-маршрут выбран через VLESS, но sing-box не запущен. Проверьте состояние VPN перед использованием.'
    if (!vlessRuntime.lan_routing_enabled) return 'sing-box запущен, но активность LAN-маршрута через VLESS не подтверждена.'
    return 'LAN-трафик идёт через sing-box; IPv6-пересылка через WAN заблокирована'
  }

  if (!runtime.interface_up) {
    return 'VPN-режим включён, но туннель WireGuard не поднят'
  }

  if (runtime.reason === 'no_handshake') {
    return 'Туннель поднят, ожидается подтверждение соединения'
  }

  if (!runtime.healthy) {
    return 'Проверьте состояние туннеля и подключение к серверу'
  }

  return 'Весь LAN-трафик идёт через VPN'
}

function getStatusText(
  runtime: VpnRuntime,
  vlessRuntime: VlessRuntime | null,
  starting: boolean,
  stopping: boolean,
): string {
  if (starting) {
    return 'Запуск'
  }

  if (stopping) {
    return 'Остановка'
  }

  if (runtime.traffic_mode === 'wan') {
    return 'Выключен'
  }

  if (runtime.traffic_mode === 'vless') {
    if (!vlessRuntime) return 'Нет данных'
    return vlessRuntime.running && vlessRuntime.lan_routing_enabled
      ? 'Через VLESS'
      : 'Внимание'
  }

  if (!runtime.interface_up || !runtime.healthy) {
    return 'Внимание'
  }

  if (runtime.healthy) {
    return 'Активен'
  }

  return 'Внимание'
}

export function VpnRuntimeCard({
  runtime,
  vlessRuntime,
  starting,
  stopping,
  error,
  onStart,
  onStop,
}: VpnRuntimeCardProps) {
  if (!runtime) {
    return (
      <section className="vpn-runtime-card">
        <div className="vpn-runtime-header">
          <div>
            <div className="eyebrow">VPN</div>
            <h2>Состояние недоступно</h2>
            <p className="muted">
              Не удалось получить текущее состояние VPN.
            </p>
          </div>
        </div>

        {error && <p className="vpn-runtime-error">{error}</p>}
      </section>
    )
  }

  const statusClass =
    runtime.traffic_mode === 'wan'
      ? 'is-stopped'
      : runtime.traffic_mode === 'vless'
        ? !vlessRuntime
          ? 'is-stopped'
          : vlessRuntime.running && vlessRuntime.lan_routing_enabled
            ? 'is-healthy'
            : 'is-unhealthy'
        : runtime.healthy && runtime.interface_up
          ? 'is-healthy'
          : 'is-unhealthy'

  const statusText = getStatusText(
    runtime,
    vlessRuntime,
    starting,
    stopping,
  )

  return (
    <section className="vpn-runtime-card">
      <div className="vpn-runtime-header">
        <div>
          <div className="eyebrow">VPN</div>
          <h2>{getVpnTitle(runtime, vlessRuntime, starting, stopping)}</h2>
          <p className="muted">{getVpnSubtitle(runtime, vlessRuntime)}</p>
        </div>

        <div className={`vpn-runtime-status ${statusClass}`}>
          <span className="vpn-runtime-dot" />
          {statusText}
        </div>
      </div>

      <div className="vpn-runtime-grid">
        <div className="vpn-runtime-item">
          <span>Состояние</span>
          <strong>
            {starting
              ? 'Запуск'
              : stopping
                ? 'Остановка'
                : runtime.traffic_mode === 'wan'
                  ? 'Неактивен'
                  : runtime.traffic_mode === 'vless'
                    ? !vlessRuntime
                      ? 'Нет данных sing-box'
                      : !vlessRuntime.running
                        ? 'sing-box остановлен'
                        : !vlessRuntime.lan_routing_enabled
                          ? 'LAN-маршрут не подтверждён'
                          : 'sing-box запущен'
                    : runtime.interface_up && runtime.healthy
                      ? 'Подключён'
                      : 'Требует внимания'}
          </strong>
        </div>

        <div className="vpn-runtime-item">
          <span>Маршрутизация</span>
          <strong>
            {runtime.traffic_mode === 'vless'
              ? !vlessRuntime
                ? 'Нет данных'
                : vlessRuntime.lan_routing_enabled
                  ? 'Через VLESS'
                  : 'Не подтверждена'
              : runtime.traffic_mode === 'vpn'
                ? 'Через AmneziaWG'
                : 'Через WAN'}
          </strong>
        </div>

        <div className="vpn-runtime-item">
          <span>Сервер</span>
          <strong>
            {runtime.traffic_mode === 'vless'
              ? (vlessRuntime?.active_server_address
                ? <ServerCountryLabel source={{ name: vlessRuntime.active_server_name, address: vlessRuntime.active_server_address }} />
                : getVlessServerText(vlessRuntime))
              : runtime.interface_up
                ? runtime.expected_endpoint
                  ? 'Доступен'
                  : 'Не подтверждён'
                : 'Не используется'}
          </strong>
          {runtime.traffic_mode === 'vless' && vlessRuntime?.active_server_address && (
            <small className="muted" style={{ display: 'block' }}>
              {`${vlessRuntime.active_server_address}:${vlessRuntime.active_server_port ?? '—'}`}
            </small>
          )}
          <CurrentVlessPing enabled={runtime?.traffic_mode === 'vless'} activeOutbound={vlessRuntime?.active_outbound} />
        </div>

        <div className="vpn-runtime-item">
          <span>{runtime.traffic_mode === 'vless' ? 'Состояние sing-box' : runtime.traffic_mode === 'vpn' ? 'Handshake' : 'Соединение'}</span>
          <strong>
            {runtime.traffic_mode === 'vless'
              ? getVlessProcessText(vlessRuntime)
              : runtime.traffic_mode === 'wan'
                ? 'Не используется'
                : runtime.interface_up
                  ? formatHandshakeAge(runtime.handshake_age_seconds)
                  : '—'}
          </strong>
        </div>
      </div>

      {runtime.traffic_mode === 'vless' && (!vlessRuntime || !vlessRuntime.running || !vlessRuntime.lan_routing_enabled) && (
        <div className="vpn-runtime-warning">
          {!vlessRuntime
            ? 'Не удалось проверить состояние sing-box и LAN-маршрута.'
            : !vlessRuntime.running
              ? 'LAN-режим VLESS выбран, но sing-box остановлен. Туннель автоматически не переключён на другой протокол.'
              : 'sing-box запущен, но активность LAN-маршрута через VLESS не подтверждена.'}
        </div>
      )}

      {runtime.traffic_mode !== 'vless' &&
        runtime.interface_up &&
        runtime.reason && (
        <div className="vpn-runtime-warning">
          {runtime.reason === 'no_handshake'
            ? 'Соединение с VPN-сервером ещё не подтверждено.'
            : runtime.reason}
        </div>
      )}

      {error && <p className="vpn-runtime-error">{error}</p>}

      <div className="vpn-runtime-actions">
        {runtime.traffic_mode === 'vless' ? (
          <p className="muted">
            Режимом LAN управляет карточка «Режим маршрутизации».
          </p>
        ) : runtime.traffic_mode === 'vpn' && runtime.interface_up ? (
          <button
            type="button"
            className="button button-danger"
            onClick={onStop}
            disabled={stopping || starting}
          >
            {stopping ? 'Остановка...' : 'Остановить VPN'}
          </button>
        ) : (
          <button
            type="button"
            className="button button-primary"
            onClick={onStart}
            disabled={starting || stopping}
          >
            {starting ? 'Запуск...' : 'Запустить VPN'}
          </button>
        )}
      </div>

      <details className="vpn-runtime-details">
        <summary>Диагностика</summary>

        {runtime.traffic_mode === 'vless' ? (
          <div className="vpn-runtime-grid">
            <div className="vpn-runtime-item">
              <span>Состояние AmneziaWG</span>
              <strong>Не используется · выбран режим VLESS</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Интерфейс TUN</span>
              <strong>{vlessRuntime?.interface ?? 'Нет данных'}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>sing-box установлен</span>
              <strong>{vlessRuntime ? (vlessRuntime.installed ? 'Да' : 'Нет') : 'Нет данных'}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Процесс sing-box</span>
              <strong>{getVlessProcessText(vlessRuntime)}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Маршрут LAN</span>
              <strong>{vlessRuntime ? (vlessRuntime.lan_routing_enabled ? 'Через VLESS' : 'Не подтверждён') : 'Нет данных'}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Режим выбора сервера</span>
              <strong>{getVlessSelectionModeText(vlessRuntime)}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Активный узел</span>
              <strong>{getVlessServerText(vlessRuntime)}</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Режим конфигурации</span>
              <strong>{getVlessConfigModeText(vlessRuntime)}</strong>
            </div>
          </div>
        ) : runtime.traffic_mode === 'wan' ? (
          <div className="vpn-runtime-grid">
            <div className="vpn-runtime-item">
              <span>Режим маршрутизации</span>
              <strong>Через WAN</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Состояние AmneziaWG</span>
              <strong>Не используется · выбран режим WAN</strong>
            </div>
            <div className="vpn-runtime-item">
              <span>Проверка AmneziaWG</span>
              <strong>Не оценивается для текущего режима</strong>
            </div>
          </div>
        ) : (
          <div className="vpn-runtime-grid">
            <div className="vpn-runtime-item">
              <span>Interface</span>
              <strong>{runtime.interface}</strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Interface up</span>
              <strong>{runtime.interface_up ? 'Да' : 'Нет'}</strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Peer</span>
              <strong>
                {runtime.interface_up
                  ? runtime.expected_peer_found
                    ? 'Найден'
                    : 'Не найден'
                  : 'Не используется'}
              </strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Endpoint</span>
              <strong>
                {runtime.interface_up
                  ? runtime.expected_endpoint
                    ? 'Подтверждён'
                    : 'Не совпадает'
                  : 'Не используется'}
              </strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Маршрут endpoint</span>
              <strong>
                {runtime.interface_up
                  ? runtime.endpoint_route_ok
                    ? 'OK'
                    : 'Ошибка'
                  : 'Не используется'}
              </strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Listen port</span>
              <strong>{runtime.listen_port ?? '—'}</strong>
            </div>

            <div className="vpn-runtime-item">
              <span>RX</span>
              <strong>{formatBytes(runtime.rx_bytes)}</strong>
            </div>

            <div className="vpn-runtime-item">
              <span>TX</span>
              <strong>{formatBytes(runtime.tx_bytes)}</strong>
            </div>

            <div className="vpn-runtime-item">
              <span>Последний handshake</span>
              <strong>{formatHandshakeAge(runtime.handshake_age_seconds)}</strong>
            </div>
          </div>
        )}
      </details>

      <div className="vpn-runtime-footer">
        Проверено: {formatCheckedAt(runtime.checked_at)}
      </div>
    </section>
  )
}
