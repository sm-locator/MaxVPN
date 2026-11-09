import { useState } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import {
  importSmartRouting,
  previewSmartRoutingImport,
} from '../api/client'
import type {
  CurrentUser,
  MaxVPNStatus,
  RussianDirectPresetResponse,
  SmartRoutingRule,
  SmartRoutingTargetType,
  SmartRoutingImportPreviewResponse,
  VpnRuntime,
  VlessRuntime,
  VpnTrafficMode,
} from '../types/api'
import { RoutingRules } from './RoutingRules'
import { DependencyDiagnostic } from './DependencyDiagnostic'
import { DomainDiagnostic } from './DomainDiagnostic'
import { SmartRoutingSync } from './SmartRoutingSync'
import { StatusCard } from './StatusCard'
import { VpnRuntimeCard } from './VpnRuntimeCard'
import { TrafficModeCard } from './TrafficModeCard'
import { VpnProfileCard } from './VpnProfileCard'
import { VlessRuntimeCard } from './VlessRuntimeCard'

type DashboardProps = {
  user: CurrentUser
  rules: SmartRoutingRule[]
  russianDirectDomains: string[]
  loading: boolean
  error: string | null
  status: MaxVPNStatus | null
  onLogout: () => void
  onSessionExpired: () => void
  onAdminSettings: () => void
  onRefresh: () => Promise<void>
  onCreate: (
    target: string,
    targetType: SmartRoutingTargetType,
  ) => Promise<void>
  onToggle: (rule: SmartRoutingRule) => Promise<void>
  onDelete: (id: number) => Promise<void>
  onAddRussianDirectPreset: () => Promise<RussianDirectPresetResponse>
  runtime: VpnRuntime | null
  vlessRuntime: VlessRuntime | null
  runtimeStarting: boolean
  runtimeStopping: boolean
  runtimeError: string | null
  modeChanging: boolean
  modeError: string | null
  onModeChange: (mode: VpnTrafficMode) => void
  onRuntimeStart: () => void
  onRuntimeStop: () => void
}

function statusTone(
  value: string | undefined,
): 'green' | 'gray' | 'red' {
  if (value === 'healthy' || value === 'connected') {
    return 'green'
  }

  if (value === undefined) {
    return 'gray'
  }

  return 'red'
}

function formatStatusValue(
  value: string | undefined,
  label: string,
): string {
  if (value === undefined) {
    return 'Проверка...'
  }

  if (label === 'Router') {
    if (value === 'connected') return 'Подключён'
    if (value === 'disconnected') return 'Недоступен'
  }

  return value
}

export function Dashboard({
  user,
  rules,
  russianDirectDomains,
  loading,
  error,
  status,
  onLogout,
  onSessionExpired,
  onAdminSettings,
  onRefresh,
  onCreate,
  onToggle,
  onDelete,
  onAddRussianDirectPreset,
  runtime,
  vlessRuntime,
  runtimeStarting,
  runtimeStopping,
  runtimeError,
  modeChanging,
  modeError,
  onModeChange,
  onRuntimeStart,
  onRuntimeStop,
}: DashboardProps) {
  const [target, setTarget] = useState('')
  const [targetType, setTargetType] =
    useState<SmartRoutingTargetType | null>(null)
  const [busyRuleId, setBusyRuleId] = useState<number | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [russianPresetLoading, setRussianPresetLoading] = useState(false)
  const [russianPresetResult, setRussianPresetResult] =
    useState<RussianDirectPresetResponse | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] =
    useState<SmartRoutingImportPreviewResponse | null>(null)
  const [importLoading, setImportLoading] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)

  async function submitRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)

    const normalized = target.trim()

    if (!targetType) {
      setFormError('Выберите тип ресурса: IP-адрес / CIDR или Домен.')
      return
    }

    if (!normalized) {
      setFormError(
        targetType === 'domain'
          ? 'Введите домен.'
          : 'Введите IPv4-адрес или CIDR.',
      )
      return
    }

    try {
      await onCreate(normalized, targetType)
      setTarget('')
      setTargetType(null)
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Не удалось создать правило.'

      if (
        message.includes(
          'domain must contain only a hostname without scheme, path or parameters',
        )
      ) {
        setFormError(
          'Введите только домен без https://, пути и параметров.',
        )
      } else {
        setFormError(message)
      }
    }
  }

  async function addRussianDirectPreset() {
    setRussianPresetLoading(true)
    setRussianPresetResult(null)

    try {
      const result = await onAddRussianDirectPreset()
      setRussianPresetResult(result)
    } finally {
      setRussianPresetLoading(false)
    }
  }

  async function handleImportFileChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0] ?? null

    setImportFile(file)
    setImportPreview(null)
    setImportError(null)

    if (!file) {
      return
    }

    const extension = file.name.toLowerCase().split('.').pop()

    if (extension !== 'txt' && extension !== 'csv') {
      setImportError('Выберите файл TXT или CSV.')
      return
    }

    setImportLoading(true)

    try {
      const preview = await previewSmartRoutingImport(file)
      setImportPreview(preview)
    } catch (error) {
      setImportError(
        error instanceof Error
          ? error.message
          : 'Не удалось проверить файл.',
      )
    } finally {
      setImportLoading(false)
    }
  }

  async function handleImportConfirm() {
    if (!importFile) {
      return
    }

    setImportLoading(true)
    setImportError(null)

    try {
      await importSmartRouting(importFile)
      setImportFile(null)
      setImportPreview(null)
      await onRefresh()
    } catch (error) {
      setImportError(
        error instanceof Error
          ? error.message
          : 'Не удалось импортировать файл.',
      )
    } finally {
      setImportLoading(false)
    }
  }

  async function toggleRule(rule: SmartRoutingRule) {
    setBusyRuleId(rule.id)

    try {
      await onToggle(rule)
    } finally {
      setBusyRuleId(null)
    }
  }

  async function deleteRule(id: number) {
    setBusyRuleId(id)

    try {
      await onDelete(id)
    } finally {
      setBusyRuleId(null)
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark small">M</div>
          <div>
            <div className="brand-name">MaxVPN</div>
            <div className="brand-subtitle">Router Control</div>
          </div>
        </div>

        <div className="topbar-right">
          <span className="user-email">{user.email}</span>
          <button
            type="button"
            className="button button-secondary"
            onClick={onAdminSettings}
          >
            Настройки
          </button>
          <button
            type="button"
            className="button button-secondary"
            onClick={onLogout}
          >
            Выйти
          </button>
        </div>
      </header>

      <section className="page">
        <div className="page-heading">
          <div>
            <div className="eyebrow">DASHBOARD</div>
            <h1>Управление маршрутизацией</h1>
            <p className="muted">
              VPN остаётся маршрутом по умолчанию. DIRECT-правила отправляют
              выбранные IPv4- и IPv6-ресурсы напрямую через WAN.
            </p>
          </div>

          <button
            type="button"
            className="button button-secondary dashboard-refresh-button"
            onClick={() => void onRefresh()}
            disabled={loading}
            aria-label="Обновить состояние"
            title="Обновить состояние"
          >
            <span aria-hidden="true">↻</span>
          </button>
        </div>

        <TrafficModeCard
          currentMode={runtime?.traffic_mode ?? null}
          busy={modeChanging}
          error={modeError}
          onChange={onModeChange}
        />

        <VpnRuntimeCard
          runtime={runtime}
          vlessRuntime={vlessRuntime}
          starting={runtimeStarting}
          stopping={runtimeStopping}
          error={runtimeError}
          onStart={onRuntimeStart}
          onStop={onRuntimeStop}
        />

        <VpnProfileCard />

        <VlessRuntimeCard />

        <section className="status-grid status-grid-secondary">
          <StatusCard
            label="Router"
            value={formatStatusValue(status?.router.status, 'Router')}
            tone={statusTone(status?.router.status)}
          />

          <StatusCard
            label="Smart Routing"
            value={
              status
                ? `${rules.filter((rule) => rule.enabled).length} активно`
                : 'Проверка...'
            }
            tone={statusTone(status?.smart_routing.status)}
          />
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">SMART ROUTING</div>
              <h2>Исключения из VPN</h2>
              <p className="muted smart-routing-panel-note">
                Доменные DIRECT-правила учитывают IPv4 (A) и IPv6 (AAAA).
                Ручное добавление IPv6 CIDR пока не поддерживается.
              </p>
            </div>
          </div>

          <SmartRoutingSync onRefresh={onRefresh} />

          <DomainDiagnostic onUnauthorized={onSessionExpired} />

          <RoutingRules
            rules={rules}
            russianDirectDomains={russianDirectDomains}
            busyRuleId={busyRuleId}
            onToggle={(rule) => void toggleRule(rule)}
            onDelete={(id) => void deleteRule(id)}
            russianAction={
              <div className="smart-routing-group-action">
                <button
                  type="button"
                  className="button button-secondary smart-routing-group-action-button"
                  onClick={() => void addRussianDirectPreset()}
                  disabled={loading || russianPresetLoading}
                >
                  {russianPresetLoading
                    ? 'Импортирование...'
                    : 'Импортировать российские сервисы'}
                </button>

                {russianPresetResult && (
                  <div className="smart-routing-import-result">
                    <strong>Российские сервисы</strong>
                    <span>Добавлено новых: {russianPresetResult.added}</span>
                    <span>
                      Уже есть в исключениях: {russianPresetResult.already_present}
                    </span>
                    <span>
                      Всего в пресете: {russianPresetResult.total_domains}
                    </span>
                  </div>
                )}
              </div>
            }
            customAction={
              <label className="button button-secondary smart-routing-group-action-button">
                {importLoading
                  ? 'Проверка...'
                  : 'Импортировать из файла'}
                <input
                  type="file"
                  accept=".txt,.csv,text/plain,text/csv"
                  onChange={(event) => void handleImportFileChange(event)}
                  hidden
                  disabled={loading || importLoading}
                />
              </label>
            }
          />

          {importError && (
            <div className="alert alert-error smart-routing-import-alert">
              {importError}
            </div>
          )}

          {importPreview && (
            <div className="smart-routing-import-preview">
              <div className="smart-routing-import-preview-header">
                <div>
                  <div className="add-rule-title">Предпросмотр импорта</div>
                  <div className="form-note">
                    {importPreview.filename ?? importFile?.name}
                  </div>
                </div>

                <button
                  type="button"
                  className="icon-button"
                  onClick={() => {
                    setImportFile(null)
                    setImportPreview(null)
                    setImportError(null)
                  }}
                  disabled={importLoading}
                  aria-label="Закрыть предпросмотр"
                >
                  ×
                </button>
              </div>

              <div className="smart-routing-import-summary">
                <div className="smart-routing-import-stat">
                  <span>Новые</span>
                  <strong>{importPreview.new}</strong>
                </div>

                <div className="smart-routing-import-stat">
                  <span>Уже есть в исключениях</span>
                  <strong>{importPreview.already_exists}</strong>
                </div>

                <div className="smart-routing-import-stat">
                  <span>Дубликаты в файле</span>
                  <strong>{importPreview.duplicates}</strong>
                </div>

                <div className="smart-routing-import-stat">
                  <span>Ошибки</span>
                  <strong>{importPreview.invalid}</strong>
                </div>
              </div>

              {importPreview.invalid > 0 && (
                <div className="smart-routing-import-items">
                  {importPreview.items
                    .filter((item) => item.status === 'invalid')
                    .map((item) => (
                      <div
                        key={`${item.line}-${item.resource}`}
                        className="smart-routing-import-item invalid"
                      >
                        <span>Строка {item.line}</span>
                        <strong>{item.resource}</strong>
                        <span>{item.error}</span>
                      </div>
                    ))}
                </div>
              )}

              <div className="smart-routing-import-actions">
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => void handleImportConfirm()}
                  disabled={
                    importLoading ||
                    importPreview.new === 0 ||
                    importPreview.invalid > 0
                  }
                >
                  {importLoading
                    ? 'Импортирование...'
                    : `Импортировать новые (${importPreview.new})`}
                </button>

                {importPreview.invalid > 0 && (
                  <div className="form-note">
                    Исправьте ошибочные строки и загрузите файл повторно.
                  </div>
                )}
              </div>
            </div>
          )}

          <DependencyDiagnostic onCommitted={onRefresh} />

          <div className="add-rule">
            <div className="add-rule-title">Добавить исключение</div>

            <form onSubmit={submitRule} className="rule-form">
              <input
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                placeholder={
                  targetType === 'domain'
                    ? 'Например: example.ru'
                    : targetType === 'cidr'
                      ? 'Например: 1.1.1.0/24'
                      : 'Сначала выберите тип ресурса'
                }
                aria-label={
                  targetType === 'domain'
                    ? 'Домен'
                    : targetType === 'cidr'
                      ? 'IPv4 адрес или CIDR'
                      : 'Адрес или домен'
                }
              />

              <div className="target-type-buttons" role="group" aria-label="Тип ресурса">
                <button
                  type="button"
                  className={`target-type-button ${
                    targetType === 'cidr' ? 'active' : ''
                  }`}
                  onClick={() => {
                    setTargetType('cidr')
                    setFormError(null)
                  }}
                  aria-pressed={targetType === 'cidr'}
                >
                  IP-адрес / CIDR
                </button>

                <button
                  type="button"
                  className={`target-type-button ${
                    targetType === 'domain' ? 'active' : ''
                  }`}
                  onClick={() => {
                    setTargetType('domain')
                    setFormError(null)
                  }}
                  aria-pressed={targetType === 'domain'}
                >
                  Домен
                </button>
              </div>

              <button
                type="submit"
                className="button button-primary"
                disabled={loading || !targetType || !target.trim()}
              >
                Добавить
              </button>
            </form>

            {formError && (
              <div className="alert alert-error">{formError}</div>
            )}

            <div className="form-note">
              Добавленные ресурсы становятся исключениями из VPN и
              направляются напрямую через WAN. Для доменных правил учитываются
              IPv4 (A) и IPv6 (AAAA). Ручное добавление IPv6 CIDR пока не поддерживается.
            </div>
          </div>
        </section>

        {error && (
          <div className="alert alert-error page-alert">{error}</div>
        )}




      </section>
    </main>
  )
}
