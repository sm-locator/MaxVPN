import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  ApiError,
  getSmartRoutingDomainDiagnostic,
} from '../api/client'
import type { SmartRoutingDomainDiagnosticResult } from '../types/api'
import {
  domainDiagnosticCheckDefinitions,
  formatDomainDiagnosticReason,
} from '../utils/domainDiagnostic'

type Props = {
  onUnauthorized: () => void
}

const exampleDomains = ['yandex.ru', 'cian.ru']

function formatAddresses(addresses: string[]): string {
  return addresses.length > 0 ? addresses.join(', ') : '—'
}

export function DomainDiagnostic({ onUnauthorized }: Props) {
  const [domain, setDomain] = useState('yandex.ru')
  const [result, setResult] =
    useState<SmartRoutingDomainDiagnosticResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function checkDomain(candidate = domain) {
    const normalizedDomain = candidate.trim()

    if (!normalizedDomain) {
      setError('Укажите домен для проверки.')
      return
    }

    setDomain(normalizedDomain)
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      setResult(await getSmartRoutingDomainDiagnostic(normalizedDomain))
    } catch (caughtError) {
      if (
        caughtError instanceof ApiError &&
        caughtError.status === 401
      ) {
        onUnauthorized()
        return
      }

      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'Не удалось выполнить проверку домена.',
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="domain-diagnostic panel-inner">
      <div className="eyebrow">DOMAIN DIAGNOSTIC</div>
      <h3>Проверка DIRECT-маршрута домена</h3>
      <p className="muted">
        Проверяет DNS IPv4, присутствие адресов в MAXVPN_DIRECT, маршрут
        с меткой и восемь правил DIRECT-маршрутизации на роутере.
      </p>

      <form
        className="domain-diagnostic-form"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault()
          void checkDomain()
        }}
      >
        <label className="domain-diagnostic-field">
          <span className="domain-diagnostic-field-label">Домен</span>
          <input
            className="input"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="yandex.ru"
            autoComplete="url"
            spellCheck="false"
          />
        </label>

        <button
          type="submit"
          className="button button-primary domain-diagnostic-submit"
          disabled={loading}
        >
          {loading ? 'Проверка...' : 'Проверить'}
        </button>
      </form>

      <div
        className="domain-diagnostic-examples"
        aria-label="Примеры доменов"
      >
        <span>Быстрая проверка:</span>
        {exampleDomains.map((example) => (
          <button
            key={example}
            type="button"
            className="domain-diagnostic-example"
            onClick={() => void checkDomain(example)}
            disabled={loading}
          >
            {example}
          </button>
        ))}
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <div className="domain-diagnostic-result">
          <div className="domain-diagnostic-result-heading">
            <div>
              <div className="add-rule-title">Результат: {result.domain}</div>
              <div className="form-note">
                Причина: {formatDomainDiagnosticReason(result.reason)}
              </div>
            </div>
            <span
              className={
                'domain-diagnostic-health ' +
                (result.healthy ? 'is-healthy' : 'is-unhealthy')
              }
            >
              {result.healthy ? 'HEALTHY' : 'ТРЕБУЕТ ВНИМАНИЯ'}
            </span>
          </div>

          <div className="domain-diagnostic-summary">
            <div>
              <span>DNS IPv4</span>
              <strong>{formatAddresses(result.dns_ipv4_addresses)}</strong>
            </div>
            <div>
              <span>В MAXVPN_DIRECT</span>
              <strong>{formatAddresses(result.present_ipv4_addresses)}</strong>
            </div>
            <div>
              <span>Нет в MAXVPN_DIRECT</span>
              <strong>{formatAddresses(result.missing_ipv4_addresses)}</strong>
            </div>
            <div>
              <span>Лишние в IPSet</span>
              <strong>
                {result.stale_ipv4_addresses.length > 0
                  ? formatAddresses(result.stale_ipv4_addresses)
                  : 'Не определяются для общего IPSet'}
              </strong>
            </div>
          </div>

          <div className="domain-diagnostic-section">
            <h4>Маршрут с меткой DIRECT</h4>
            {result.route_results.length > 0 ? (
              <ul className="domain-diagnostic-routes">
                {result.route_results.map((route) => (
                  <li
                    key={route}
                    className={
                      route.endsWith(' OK') ? 'text-ok' : 'text-error'
                    }
                  >
                    {route}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="form-note">
                Нет результатов маршрута: DNS IPv4 не найден или адреса ещё
                не попали в MAXVPN_DIRECT.
              </p>
            )}
          </div>

          <div className="domain-diagnostic-section">
            <h4>Проверки DIRECT-маршрутизации</h4>
            <div className="domain-diagnostic-checks">
              {domainDiagnosticCheckDefinitions.map((check) => {
                const passed = result.checks[check.key]

                return (
                  <div
                    key={check.key}
                    className={
                      'domain-diagnostic-check ' +
                      (passed ? 'is-passed' : 'is-failed')
                    }
                  >
                    <div>
                      <strong>{check.label}</strong>
                      <span>{check.description}</span>
                    </div>
                    <b>{passed ? 'OK' : 'НЕТ'}</b>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
