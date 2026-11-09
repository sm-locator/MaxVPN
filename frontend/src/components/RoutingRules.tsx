import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  getDependencyGroups,
  testRule as testSmartRoutingRule,
} from '../api/client'
import type {
  DependencyGroup,
  SmartRoutingRule,
  SmartRoutingRuleTestResponse,
} from '../types/api'

type RoutingRulesProps = {
  rules: SmartRoutingRule[]
  russianDirectDomains: string[]
  busyRuleId: number | null
  onToggle: (rule: SmartRoutingRule) => void
  onDelete: (id: number) => void
  russianAction?: ReactNode
  customAction?: ReactNode
}


function isRussianDirectRule(
  rule: SmartRoutingRule,
  russianDirectDomains: Set<string>,
): boolean {
  return (
    rule.target_type === 'domain' &&
    rule.action === 'direct' &&
    rule.address_family === 'any' &&
    russianDirectDomains.has(
      rule.target.trim().toLowerCase().replace(/\.$/, ''),
    )
  )
}

function routeDecisionLabel(value: string): string {
  switch (value) {
    case 'direct':
      return 'DIRECT'
    case 'vpn':
      return 'VPN'
    case 'not_applied':
      return 'Не применено'
    case 'disabled':
      return 'Выключено'
    default:
      return 'Не определён'
  }
}

function routeDecisionClass(value: string): string {
  switch (value) {
    case 'direct':
      return 'rule-test-decision-direct'
    case 'vpn':
      return 'rule-test-decision-vpn'
    default:
      return 'rule-test-decision-neutral'
  }
}

function RuleTestPanel({
  result,
  onClose,
}: {
  result: SmartRoutingRuleTestResponse
  onClose: () => void
}) {
  const routeTest = result.route_test
  const destination = routeTest.destinations[0] ?? null

  const directApplied = routeTest.overall === 'direct'

  const actualRoute = destination
    ? directApplied
      ? destination.marked_route
      : destination.unmarked_route
    : null

  const alternateRoute = destination
    ? directApplied
      ? destination.unmarked_route
      : destination.marked_route
    : null

  return (
    <div className="rule-test-panel">
      <div className="rule-test-header">
        <div>
          <div className="rule-test-title">Проверка маршрута</div>
          <div className="rule-test-subtitle">
            {routeTest.rule.target} · Runtime priority {routeTest.rule.priority}
          </div>
        </div>

        <div className="rule-test-header-actions">
          <span
            className={`rule-test-decision ${routeDecisionClass(
              routeTest.overall,
            )}`}
          >
            Решение: {routeDecisionLabel(routeTest.overall)}
          </span>

          <button
            type="button"
            className="rule-test-close"
            aria-label="Закрыть проверку маршрута"
            title="Закрыть"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </div>

      <div className="rule-test-grid">
        <div className="rule-test-item">
          <span>Конфигурация</span>
          <strong>
            {routeTest.configuration.applied &&
            !routeTest.configuration.config_dirty
              ? 'Синхронизирована'
              : 'Не синхронизирована'}
          </strong>
        </div>

        <div className="rule-test-item">
          <span>Определено IP</span>
          <strong>
            {routeTest.resolution.addresses.join(', ') || 'Нет'}
          </strong>
        </div>

        {destination ? (
          <>
            <div className="rule-test-item">
              <span>Источник на LAN Brume</span>
              <strong>
                {destination.marked_route.probe_client_ip || 'Не определён'}
              </strong>
            </div>

            <div className="rule-test-item">
              <span>Состояние источника</span>
              <strong>
                {destination.marked_route.probe_client_state || '—'}
              </strong>
            </div>

            <div className="rule-test-item">
              <span>Фактический маршрут</span>
              <strong>
                {actualRoute?.dev || '—'}
                {actualRoute?.via
                  ? ` → ${actualRoute.via}`
                  : ''}
              </strong>
              <small>
                {directApplied
                  ? 'DIRECT · table 200 · mark 0x64'
                  : 'обычный policy route · table 100'}
              </small>
            </div>

            <div className="rule-test-item">
              <span>
                {directApplied
                  ? 'Альтернативный маршрут без DIRECT'
                  : 'DIRECT при включении'}
              </span>
              <strong>
                {alternateRoute?.dev || '—'}
                {alternateRoute?.via
                  ? ` → ${alternateRoute.via}`
                  : ''}
              </strong>
              <small>
                {directApplied
                  ? 'обычный policy route · table 100'
                  : 'table 200 · mark 0x64 (расчётный)'}
              </small>
            </div>
          </>
        ) : null}
      </div>

      {destination ? (
        <details className="rule-test-details" open>
          <summary>Почему выбран этот маршрут</summary>

          <div className="rule-test-reasons">
            {destination.reason.map((reason, index) => (
              <div className="rule-test-reason" key={`${reason}-${index}`}>
                <span>✓</span>
                <span>{reason}</span>
              </div>
            ))}
          </div>
        </details>
      ) : (
        <div className="rule-test-empty">
          Диагностика не получила адрес назначения.
        </div>
      )}

      {destination ? (
        <details className="rule-test-details">
          <summary>Техническая информация</summary>

          <div className="rule-test-tech">
            <div>
              <span>IP</span>
              <code>{destination.ip}</code>
            </div>

            <div>
              <span>Marked route</span>
              <code>{destination.marked_route.raw}</code>
            </div>

            <div>
              <span>Unmarked route</span>
              <code>{destination.unmarked_route.raw}</code>
            </div>
          </div>
        </details>
      ) : null}
    </div>
  )
}

function RuleRow({
  rule,
  busyRuleId,
  onToggle,
  onDelete,
}: {
  rule: SmartRoutingRule
  busyRuleId: number | null
  onToggle: (rule: SmartRoutingRule) => void
  onDelete: (id: number) => void
}) {
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] =
    useState<SmartRoutingRuleTestResponse | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  async function handleTest() {
    setTesting(true)
    setTestError(null)

    try {
      const result = await testSmartRoutingRule(rule.id)
      setTestResult(result)
    } catch (error) {
      setTestResult(null)
      setTestError(
        error instanceof Error
          ? error.message
          : 'Не удалось выполнить проверку маршрута',
      )
    } finally {
      setTesting(false)
    }
  }

  return (
    <>
      <div className="rule-row">
        <div className="rule-main">
          <div className="rule-target">{rule.target}</div>

          <div className="rule-meta">
            {rule.target_type === 'cidr' ? 'IP/CIDR' : 'Домен'} ·{' '}
            {rule.address_family === 'ipv4'
              ? 'IPv4'
              : rule.address_family === 'ipv6'
                ? 'IPv6'
                : rule.target_type === 'domain'
                  ? 'IPv4 + IPv6'
                  : 'Авто'}{' '}
            · приоритет {rule.priority}
          </div>
        </div>

        <div
          className={`rule-action ${
            rule.action === 'direct' ? 'action-direct' : 'action-vpn'
          }`}
        >
          {rule.action === 'direct' ? 'DIRECT' : 'VPN'}
        </div>

        <button
          type="button"
          className="rule-test-button"
          disabled={
            testing ||
            busyRuleId === rule.id
          }
          onClick={handleTest}
        >
          {testing ? 'Проверка…' : 'Проверить'}
        </button>

        <button
          type="button"
          className={`switch ${rule.enabled ? 'switch-on' : ''}`}
          aria-label={rule.enabled ? 'Отключить правило' : 'Включить правило'}
          disabled={busyRuleId === rule.id || testing}
          onClick={() => onToggle(rule)}
        >
          <span />
        </button>

        <button
          type="button"
          className="icon-button danger"
          aria-label="Удалить правило"
          disabled={busyRuleId === rule.id || testing}
          onClick={() => onDelete(rule.id)}
        >
          ×
        </button>
      </div>

      {testing ? (
        <div className="rule-test-loading">
          Выполняется проверка маршрута на роутере…
        </div>
      ) : null}

      {testError ? (
        <div className="rule-test-error">
          <strong>Ошибка проверки:</strong> {testError}
        </div>
      ) : null}

      {testResult ? (
        <RuleTestPanel
          result={testResult}
          onClose={() => {
            setTestResult(null)
            setTestError(null)
          }}
        />
      ) : null}
    </>
  )
}

function RoutingGroup({
  title,
  subtitle,
  count,
  rules,
  expanded,
  onToggleExpanded,
  busyRuleId,
  onToggle,
  onDelete,
  action,
}: {
  title: string
  subtitle: string
  count: number
  rules: SmartRoutingRule[]
  expanded: boolean
  onToggleExpanded: () => void
  busyRuleId: number | null
  onToggle: (rule: SmartRoutingRule) => void
  onDelete: (id: number) => void
  action?: ReactNode
}) {
  return (
    <div className="routing-group-row">
      <section className="routing-group">
      <button
        type="button"
        className="routing-group-header"
        aria-expanded={expanded}
        onClick={onToggleExpanded}
      >
        <div className="routing-group-info">
          <div className="routing-group-title">{title}</div>
          <div className="routing-group-subtitle">{subtitle}</div>
        </div>

        <div className="routing-group-right">
          <span className="routing-group-count">{count}</span>
          <span
            className={`routing-group-chevron ${
              expanded ? 'routing-group-chevron-open' : ''
            }`}
            aria-hidden="true"
          >
            ›
          </span>
        </div>
      </button>

      {expanded && (
        <div className="rules-list">
          {rules.map((rule) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              busyRuleId={busyRuleId}
              onToggle={onToggle}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
      </section>

      {action && (
        <div className="routing-group-action">
          {action}
        </div>
      )}
    </div>
  )
}


function DiagnosticGroups({
  groups,
  expanded,
  onToggleExpanded,
  busyRuleId,
  onToggle,
  onDelete,
}: {
  groups: DependencyGroup[]
  expanded: boolean
  onToggleExpanded: () => void
  busyRuleId: number | null
  onToggle: (rule: SmartRoutingRule) => void
  onDelete: (id: number) => void
}) {
  return (
    <section className="routing-group">
      <button
        type="button"
        className="routing-group-header"
        aria-expanded={expanded}
        onClick={onToggleExpanded}
      >
        <div className="routing-group-info">
          <div className="routing-group-title">Диагностика</div>
          <div className="routing-group-subtitle">
            Ресурсы, добавленные из диагностики
          </div>
        </div>

        <div className="routing-group-right">
          <span className="routing-group-count">{groups.length}</span>
          <span
            className={`routing-group-chevron ${
              expanded ? 'routing-group-chevron-open' : ''
            }`}
            aria-hidden="true"
          >
            ›
          </span>
        </div>
      </button>

      {expanded && (
        <div className="diagnostic-saved-groups">
          {groups.length === 0 ? (
            <div className="diagnostic-saved-empty">
              Здесь появятся ресурсы, добавленные из диагностики.
            </div>
          ) : (
            groups.map((group) => (
              <details
                key={group.id}
                className="diagnostic-saved-group"
              >
                <summary>
                  <div className="diagnostic-saved-group-info">
                    <strong>
                      Ресурсы связанные с {group.site_domain}
                    </strong>
                    <span>{group.title}</span>
                  </div>

                  <span className="routing-group-count">
                    {group.items.length}
                  </span>
                </summary>

                <div className="rules-list">
                  {group.items.map((item) =>
                    item.rule ? (
                      <RuleRow
                        key={item.rule_id}
                        rule={item.rule}
                        busyRuleId={busyRuleId}
                        onToggle={onToggle}
                        onDelete={onDelete}
                      />
                    ) : null,
                  )}
                </div>
              </details>
            ))
          )}
        </div>
      )}
    </section>
  )
}

export function RoutingRules({
  rules,
  russianDirectDomains,
  busyRuleId,
  onToggle,
  onDelete,
  russianAction,
  customAction,
}: RoutingRulesProps) {
  const [russianExpanded, setRussianExpanded] = useState(false)
  const [customExpanded, setCustomExpanded] = useState(false)
  const [diagnosticExpanded, setDiagnosticExpanded] = useState(false)
  const [dependencyGroups, setDependencyGroups] = useState<DependencyGroup[]>([])

  useEffect(() => {
    let cancelled = false

    void getDependencyGroups()
      .then((groups) => {
        if (!cancelled) {
          setDependencyGroups(groups)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setDependencyGroups([])
        }
      })

    return () => {
      cancelled = true
    }
  }, [rules])

  if (rules.length === 0) {
    return (
      <>
        <div className="empty-state">
          <strong>Правил пока нет</strong>
          <span>
            Добавьте домен или IP/CIDR, чтобы настроить исключение из VPN.
          </span>
        </div>

        <DiagnosticGroups
          groups={dependencyGroups}
          expanded={diagnosticExpanded}
          onToggleExpanded={() =>
            setDiagnosticExpanded((value) => !value)
          }
          busyRuleId={busyRuleId}
          onToggle={onToggle}
          onDelete={onDelete}
        />
      </>
    )
  }

  const russianDomainSet = new Set(
    russianDirectDomains.map((domain) =>
      domain.trim().toLowerCase().replace(/\.$/, ''),
    ),
  )

  const russianRules = rules.filter((rule) =>
    isRussianDirectRule(rule, russianDomainSet),
  )

  const diagnosticRuleIds = new Set(
    dependencyGroups.flatMap((group) =>
      group.items.map((item) => item.rule_id),
    ),
  )

  const customRules = rules.filter(
    (rule) =>
      !isRussianDirectRule(rule, russianDomainSet) &&
      !diagnosticRuleIds.has(rule.id),
  )

  return (
    <div className="routing-groups">
      <RoutingGroup
        title="Ru DIRECT"
        subtitle="Российские сервисы"
        count={russianRules.length}
        rules={russianRules}
        expanded={russianExpanded}
        onToggleExpanded={() => setRussianExpanded((value) => !value)}
        busyRuleId={busyRuleId}
        onToggle={onToggle}
        onDelete={onDelete}
        action={russianAction}
      />

      <RoutingGroup
        title="Мои исключения"
        subtitle="Ваши адреса и домены"
        count={customRules.length}
        rules={customRules}
        expanded={customExpanded}
        onToggleExpanded={() => setCustomExpanded((value) => !value)}
        busyRuleId={busyRuleId}
        onToggle={onToggle}
        onDelete={onDelete}
        action={customAction}
      />

      <DiagnosticGroups
        groups={dependencyGroups}
        expanded={diagnosticExpanded}
        onToggleExpanded={() =>
          setDiagnosticExpanded((value) => !value)
        }
        busyRuleId={busyRuleId}
        onToggle={onToggle}
        onDelete={onDelete}
      />
    </div>
  )
}
