import { useEffect, useRef, useState } from 'react'
import {
  commitDependencyDiagnosticRules,
  startDependencyDiagnostic,
  pollDependencyDiagnostic,
} from '../api/client'
import type {
  DependencyDiagnosticResource,
  DependencyDiagnosticResult,
} from '../types/api'

type Props = { onCommitted: () => Promise<void> }

const relevanceLabels: Record<DependencyDiagnosticResource['relevance'], string> = {
  required: 'Высокая',
  likely: 'Вероятная',
  possible: 'Возможная',
  background: 'Фоновая',
}

const categoryLabels: Record<DependencyDiagnosticResource['category'], string> = {
  target_site: 'Ресурс целевого домена',
  external_candidate: 'Внешний кандидат — связь не подтверждена',
  background: 'Фоновая DNS-активность',
}

export function DependencyDiagnostic({ onCommitted }: Props) {
  const [domain, setDomain] = useState('')
  const [clientIp, setClientIp] = useState('')
  const domainInputRef = useRef<HTMLInputElement>(null)
  const clientIpInputRef = useRef<HTMLInputElement>(null)
  const clientIpOverrideRef = useRef<HTMLDetailsElement>(null)
  const [duration, setDuration] = useState(30)
  const [result, setResult] = useState<DependencyDiagnosticResult | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
  }, [])




  async function poll(token: string) {
    const next = await pollDependencyDiagnostic(token)
    setResult(next)
    if (next.running) {
      timer.current = window.setTimeout(() => void poll(token), 1000)
    } else {
      // Match the appliance UI: candidates require explicit user selection.
      setSelected([])
      setBusy(false)
    }
  }

  async function start() {
    // Read the live input values as well as React state. Some browsers can
    // autofill controlled inputs without dispatching the change event.
    const domainValue = (domainInputRef.current?.value ?? domain).trim()
    // A remembered override is active only while its advanced section is open.
    const clientIpValue = clientIpOverrideRef.current?.open
      ? (clientIpInputRef.current?.value ?? clientIp).trim()
      : ''
    if (!domainValue) {
      setMessage('Укажите домен сайта.')
      return
    }

    // Keep the controlled component state aligned with the values actually submitted.
    setDomain(domainValue)
    setClientIp(clientIpValue)
    if (timer.current !== null) window.clearTimeout(timer.current)
    setBusy(true); setMessage(null); setSelected([])
    try {
      const started = await startDependencyDiagnostic({
        site_domain: domainValue,
        ...(clientIpValue ? { client_ip: clientIpValue } : {}),
        duration_seconds: duration,
      })
      setResult(started)
      setMessage(
        `Диагностика запущена для клиента ${started.client_ip}. Откройте или обновите ${domainValue}.`,
      )
      await poll(started.token)
    } catch (error) {
      setBusy(false)
      const detail = error instanceof Error ? error.message : 'Не удалось запустить диагностику.'
      if (!clientIpValue && /IP клиента|IP client/i.test(detail)) {
        if (clientIpOverrideRef.current) clientIpOverrideRef.current.open = true
      }
      setMessage(detail)
    }
  }

  function toggle(hostname: string) {
    setSelected((current) => current.includes(hostname)
      ? current.filter((item) => item !== hostname)
      : [...current, hostname])
  }

  async function addSelected() {
    if (!result || selected.length === 0) return
    setBusy(true)
    try {
      const committed = await commitDependencyDiagnosticRules(
        result.token,
        selected,
        result.site_domain,
      )
      setMessage(`Добавлено новых: ${committed.created_rules.length}. Уже существовало: ${committed.reused_rules.length}. Нажмите «Применить».`)
      setSelected([])
      await onCommitted()
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Не удалось добавить правила.'
      if (/404|diagnostic session (?:result )?not found/i.test(detail)) {
        setMessage('Результаты диагностики устарели или сессия недоступна. Запустите диагностику ещё раз и добавьте выбранные ресурсы сразу после завершения.')
      } else {
        setMessage(detail)
      }
    } finally { setBusy(false) }
  }

  const resources = result?.resources ?? []
  const observedResources = resources.filter((item) => !item.synthetic)
  const candidates = resources.filter((item) => item.selection_allowed && item.candidate_for_direct)
  const targetResources = resources.filter((item) => item.category === 'target_site')
  const externalCandidates = resources.filter((item) => item.category === 'external_candidate')
  const backgroundResources = resources.filter((item) => item.category === 'background')

  function renderResource(item: DependencyDiagnosticResource) {
    const hasDetails = Boolean(
      item.cname_chain?.length ||
        (item.synthetic && item.observed_hostnames?.length) ||
        item.dependency_reasons?.length ||
        item.related_hostnames?.length,
    )

    return <tr key={item.hostname}>
      <td>
        {item.selection_allowed && item.candidate_for_direct ? (
          <input
            type="checkbox"
            checked={selected.includes(item.hostname)}
            onChange={() => toggle(item.hostname)}
          />
        ) : null}
      </td>

      <td>
        <strong>{item.hostname}</strong>

        {item.synthetic ? (
          <span className="dependency-synthetic">
            АГРЕГИРОВАННЫЙ РЕСУРС
          </span>
        ) : null}

        {hasDetails ? (
          <details className="dependency-resource-details">
            <summary>Подробнее</summary>

            {item.cname_chain?.length ? (
              <small className="dependency-cname">
                CNAME: {item.cname_chain.join(' → ')}
              </small>
            ) : null}

            {item.synthetic && item.observed_hostnames?.length ? (
              <div className="dependency-children">
                {item.observed_hostnames.map((hostname) => (
                  <div key={hostname}>├── {hostname}</div>
                ))}
              </div>
            ) : null}

            {item.dependency_reasons?.length ? (
              <small className="dependency-cname">
                Почему: {item.dependency_reasons.join(' · ')}
              </small>
            ) : null}

            {item.related_hostnames?.length ? (
              <small className="dependency-cname">
                Связано: {item.related_hostnames.join(', ')}
              </small>
            ) : null}
          </details>
        ) : null}
      </td>

      <td>{item.ips?.join(', ') || '—'}</td>
      <td>{item.query_count}</td>

      <td
        className={
          item.routing === 'direct'
            ? 'text-ok'
            : item.routing === 'vpn'
              ? 'text-warn'
              : ''
        }
      >
        {item.routing === 'direct'
          ? 'DIRECT'
          : item.routing === 'vpn'
            ? 'VPN'
            : item.routing}
      </td>

      <td>
        {item.covered_by_rule
          ? `Да${item.rule_domain ? ` · ${item.rule_domain}` : ''}`
          : 'Нет'}
      </td>

      <td>
        <div>{categoryLabels[item.category]}</div>
        <small className="dependency-cname">{item.category_detail}</small>
        <small className="dependency-cname">Эвристическая оценка: {relevanceLabels[item.relevance]} · {item.relevance_score}</small>
      </td>
    </tr>
  }

  function renderResourceSection(title: string, items: DependencyDiagnosticResource[]) {
    if (items.length === 0) return null
    const observedCount = items.filter((item) => !item.synthetic).length
    return <div className="dependency-resource-section" key={title}>
      <h4>{title} · {observedCount}</h4>
      <div className="dependency-table-wrap">
        <table className="dependency-table">
          <thead><tr><th></th><th>Ресурс</th><th>IPv4</th><th>Запросы A/HTTPS/AAAA</th><th>Ожидаемый маршрут*</th><th>Доменное правило</th><th>Классификация</th></tr></thead>
          <tbody>{items.map(renderResource)}</tbody>
        </table>
      </div>
    </div>
  }

  return <section className="dependency-diagnostic panel-inner">
    <div className="eyebrow">ДИАГНОСТИКА</div>
    <h3>Почему сайт загружается не полностью?</h3>
    <p className="muted">Наблюдаем DNS-запросы конкретного клиента и выделяем ресурсы, которые могут быть связаны с загрузкой сайта. Релевантность — эвристика по DNS-признакам, а не доказательство HTTP-зависимости.</p>
    <div className="dependency-form">
      <label className="dependency-field">
        <span className="dependency-field-label">Сайт</span>
        <input
          ref={domainInputRef}
          className="input"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="2gis.ru"
          autoComplete="url"
        />
      </label>

      <label className="dependency-field dependency-field-duration">
        <span className="dependency-field-label">Время наблюдения</span>
        <select
          className="select"
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
        >
          {[20, 30, 45, 60].map((value) => (
            <option key={value} value={value}>
              {value} сек
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className="button button-primary dependency-start-button"
        onClick={() => void start()}
        disabled={busy}
      >
        {busy ? 'Наблюдение...' : 'Запустить диагностику'}
      </button>
    </div>
    <p className="dependency-ip-hint">
      IP устройства определяется автоматически. Для диагностики другого устройства
      можно указать его адрес в дополнительных настройках.
    </p>
    <details ref={clientIpOverrideRef} className="dependency-client-override">
      <summary>Указать IP другого устройства</summary>
      <label className="dependency-field">
        <span className="dependency-field-label">IP клиента (необязательно)</span>
        <input
          ref={clientIpInputRef}
          className="input"
          value={clientIp}
          onChange={(e) => setClientIp(e.target.value)}
          placeholder="192.168.8.231"
          autoComplete="off"
        />
      </label>
    </details>
    {message && <div className="notice">{message}</div>}
    {result && <>
      <div className="dependency-summary">
        <span>{result.running ? `Наблюдение: ${result.remaining_seconds} сек` : `Найдено DNS-ресурсов: ${observedResources.length}`}</span>
        <span>Сайт: {observedResources.filter((item) => item.category === 'target_site').length}</span>
        <span>Внешние кандидаты: {observedResources.filter((item) => item.category === 'external_candidate').length}</span>
        <span>Фоновые: {observedResources.filter((item) => item.category === 'background').length}</span>
        <span>Ожидается DIRECT/WAN: {result.summary?.direct ?? 0}</span>
        <span>Ожидается VPN: {result.summary?.vpn ?? 0}</span>
        <span>Можно выбрать: {candidates.length}</span>
      </div>
      <p className="muted">К выбору допускаются только фактически наблюдавшиеся домены сайта или известного пространства бренда с IPv4, ожидаемым маршрутом VPN и без покрывающего доменного правила. Внешние ресурсы, связанные только по времени, показываются без возможности добавления.</p>
      {!result.running && <button type="button" className="button button-primary" onClick={() => void addSelected()} disabled={busy || selected.length === 0}>Добавить выбранные в DIRECT ({selected.length})</button>}
      {renderResourceSection('Ресурсы целевого домена и поддоменов', targetResources)}
      {renderResourceSection('Внешние кандидаты — связь не подтверждена', externalCandidates)}
      {renderResourceSection('Фоновая DNS-активность — связь с сайтом не установлена', backgroundResources)}
    </>}
  </section>
}
