import { useEffect, useState } from 'react'
import {
  applySmartRouting,
  getSmartRoutingSyncPreview,
  pullSmartRoutingFromBrume,
  deleteRule,
  getRules,
  pushSmartRoutingToBrume,
  syncSmartRoutingEnabledFromBrume,
} from '../api/client'
import type {
  SmartRoutingRule,
  SmartRoutingSyncPreview,
  SmartRoutingSyncPullResponse,
  SmartRoutingSyncPushResponse,
  SmartRoutingSyncEnabledResponse,
} from '../types/api'

type Props = {
  onRefresh: () => Promise<void>
}

type RuntimeState = Record<string, unknown>

function targetLabel(rule: SmartRoutingRule): string {
  return rule.target
}

function asBoolean(
  value: unknown,
): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asNumber(
  value: unknown,
): number | null {
  return typeof value === 'number' ? value : null
}

function asString(
  value: unknown,
): string | null {
  return typeof value === 'string' ? value : null
}

function runtimeDirty(
  runtime: RuntimeState,
): boolean {
  return asBoolean(runtime.config_dirty) === true
}

export function SmartRoutingSync({ onRefresh }: Props) {
  const [preview, setPreview] =
    useState<SmartRoutingSyncPreview | null>(null)

  const [pullResult, setPullResult] =
    useState<SmartRoutingSyncPullResponse | null>(null)

  const [pushResult, setPushResult] =
    useState<SmartRoutingSyncPushResponse | null>(null)

  const [loading, setLoading] = useState(true)
  const [pulling, setPulling] = useState(false)
  const [pushing, setPushing] = useState(false)
  const [applying, setApplying] = useState(false)
  const [deletingLocalOnly, setDeletingLocalOnly] = useState(false)
  const [enabledSyncing, setEnabledSyncing] = useState(false)
  const [enabledSyncResult, setEnabledSyncResult] =
    useState<SmartRoutingSyncEnabledResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    setError(null)

    try {
      const data = await getSmartRoutingSyncPreview()
      setPreview(data)
      setPullResult(null)
      setPushResult(null)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось проверить состояние Brume 3',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])


  async function handleEnabledSync() {
    setEnabledSyncing(true)
    setError(null)

    try {
      const result =
        await syncSmartRoutingEnabledFromBrume()

      setEnabledSyncResult(result)

      await onRefresh()
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось синхронизировать состояния правил',
      )
    } finally {
      setEnabledSyncing(false)
    }
  }


  async function handlePull() {
    if (!preview) return

    const remoteOnly = preview.diff.remote_only
    const diagnosticRelinks = preview.diff.diagnostic_relinks

    if (remoteOnly.length === 0 && diagnosticRelinks.length === 0) return

    const parts: string[] = []

    if (remoteOnly.length > 0) {
      parts.push(`Импортировать ${remoteOnly.length} новых правил с Brume 3 в localhost?`)
    }

    if (diagnosticRelinks.length > 0) {
      parts.push(
        `Восстановить привязку ${diagnosticRelinks.length} уже существующих правил к диагностическим группам?`,
      )
    }

    const confirmed = window.confirm(
      parts.join('\n\n') +
        '\n\nСуществующие локальные правила не будут удалены или изменены.',
    )

    if (!confirmed) return

    setPulling(true)
    setError(null)

    try {
      const result = await pullSmartRoutingFromBrume(
        preview.remote.fingerprint,
      )

      setPullResult(result)
      await onRefresh()
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось выполнить Pull',
      )
    } finally {
      setPulling(false)
    }
  }

  async function handleDeleteLocalOnly() {
    if (!preview) return

    const localOnly = preview.diff.local_only

    if (localOnly.length === 0) return

    const targets = localOnly
      .map((rule) => `• ${targetLabel(rule)}`)
      .join('\n')

    const confirmed = window.confirm(
      `Удалить ${localOnly.length} правил из localhost?\n\n` +
        `${targets}\n\n` +
        'Правила на Brume 3 не будут изменены.',
    )

    if (!confirmed) return

    setDeletingLocalOnly(true)
    setError(null)

    try {
      /*
       * Sync preview содержит логические правила без DB id.
       * Получаем актуальные локальные правила и восстанавливаем
       * их реальные id по той же логической идентичности:
       * target_type + normalized target.
       */
      const currentRules = await getRules()

      const ruleKey = (
        targetType: string,
        target: string,
      ): string => {
        const type =
          String(targetType || '')
            .trim()
            .toLowerCase()

        let value =
          String(target || '')
            .trim()
            .toLowerCase()

        if(type === 'domain'){
          value = value.replace(/\.+$/, '')
        }

        return `${type}:${value}`
      }

      const currentByKey =
        new Map(
          currentRules.map(
            (rule) => [
              ruleKey(
                rule.target_type,
                rule.target,
              ),
              rule,
            ],
          ),
        )

      const ids =
        localOnly.map((rule) => {

          const current =
            currentByKey.get(
              ruleKey(
                rule.target_type,
                rule.target,
              ),
            )

          if(
            !current ||
            !Number.isInteger(current.id)
          ){
            throw new Error(
              `Не удалось найти локальное правило: ${targetLabel(rule)}`
            )
          }

          return current.id
        })

      /*
       * Проверяем наличие всех id ДО первого DELETE,
       * чтобы не получить частичное удаление.
       */
      for(const id of ids){
        if(!Number.isInteger(id)){
          throw new Error(
            'Получен некорректный идентификатор локального правила'
          )
        }
      }

      for(const id of ids){
        await deleteRule(id)
      }

      await onRefresh()
      await refresh()

    } catch (err) {

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось удалить локальные правила',
      )

    } finally {
      setDeletingLocalOnly(false)
    }
  }


  async function handlePush() {
    if (!preview) return

    const localOnly = preview.diff.local_only

    if (localOnly.length === 0) return

    const confirmed = window.confirm(
      `Отправить ${localOnly.length} локальных правил на Brume 3?\n\n` +
        'Существующие правила Brume 3 не будут удалены или изменены.\n' +
        'Runtime Brume 3 не изменится автоматически — после Push потребуется Apply.',
    )

    if (!confirmed) return

    setPushing(true)
    setError(null)

    try {
      const result = await pushSmartRoutingToBrume(
        preview.remote.fingerprint,
      )

      setPushResult(result)
      await onRefresh()
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось выполнить Push',
      )
    } finally {
      setPushing(false)
    }
  }

  async function handleApply() {
    const confirmed = window.confirm(
      'Применить текущую конфигурацию Smart Routing на Brume 3?\n\n' +
        'Будет обновлён runtime policy routing. ' +
        'WireGuard/AWG routing table 100 не должна изменяться.',
    )

    if (!confirmed) return

    setApplying(true)
    setError(null)

    try {
      await applySmartRouting()
      await onRefresh()
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось применить Smart Routing',
      )
    } finally {
      setApplying(false)
    }
  }

  const remoteOnly = preview?.diff.remote_only ?? []
  const localOnly = preview?.diff.local_only ?? []
  const protectedLocalOnly =
    preview?.diff.protected_local_only ?? []
  const semanticMismatches =
    preview?.diff.semantic_mismatches ?? []
  const orderMismatches =
    preview?.diff.order_mismatches ?? []
  const diagnosticRelinks =
    preview?.diff.diagnostic_relinks ?? []

  const runtime: RuntimeState =
    preview?.remote.runtime ?? {}

  const dirty = runtimeDirty(runtime)
  const directMangleCount =
    asNumber(runtime.mangle_direct_count)
  const staticMangleCount =
    asNumber(runtime.mangle_static_count)
  const directIpSet =
    asBoolean(runtime.direct_ipset)
  const staticIpSet =
    asBoolean(runtime.static_ipset)
  const ipRule =
    asString(runtime.ip_rule)
  const table200 =
    asString(runtime.table_200)

  const policyRoutingActive =
    Boolean(
      ipRule?.includes(
        'fwmark 0x64/0xff lookup 200',
      ),
    )

  const runtimeHealthy =
    !dirty &&
    directMangleCount === 1 &&
    staticMangleCount === 1 &&
    directIpSet === true &&
    staticIpSet === true &&
    policyRoutingActive

  const fullySynchronized =
    Boolean(preview) &&
    remoteOnly.length === 0 &&
    localOnly.length === 0 &&
    semanticMismatches.length === 0 &&
    orderMismatches.length === 0 &&
    diagnosticRelinks.length === 0

  return (
    <section className="smart-routing-sync panel-inner">
      <div className="smart-routing-sync-header">
        <div>
          <div className="eyebrow">СИНХРОНИЗАЦИЯ</div>
          <h3>Brume 3 ↔ localhost</h3>
          <p className="muted">
            Сравнивает логические Smart Routing правила и состояние
            runtime Brume 3. Pull и Push не удаляют существующие правила.
          </p>
        </div>

        <div className="smart-routing-sync-header-actions">
          <button
            type="button"
            className="button button-primary"
            onClick={() => void handleEnabledSync()}
            disabled={
              loading ||
              pulling ||
              pushing ||
              applying ||
              enabledSyncing
            }
            title="Получить с Brume 3 только состояние ВКЛ/ВЫКЛ существующих правил"
          >
            {enabledSyncing
              ? 'Синхронизируем…'
              : 'Синхронизировать ВКЛ/ВЫКЛ'}
          </button>

          <button
            type="button"
            className="button button-secondary"
            onClick={() => void refresh()}
            disabled={
              loading ||
              pulling ||
              pushing ||
              applying ||
              enabledSyncing
            }
          >
            {loading ? 'Проверяем…' : 'Обновить'}
          </button>
        </div>
      </div>


      {enabledSyncResult && (
        <div className="smart-routing-sync-result">
          Состояния ВКЛ/ВЫКЛ синхронизированы:
          <strong>{enabledSyncResult.updated_count}</strong>
          изменено
          ·
          <strong>{enabledSyncResult.unchanged_count}</strong>
          без изменений
          ·
          <strong>{enabledSyncResult.remote_only_count}</strong>
          только на Brume 3
        </div>
      )}


      {error && (
        <div className="alert alert-error smart-routing-sync-error">
          {error}
        </div>
      )}

      {preview && (
        <>
          <div className="smart-routing-sync-stats">
            <div className="smart-routing-sync-stat">
              <span>localhost</span>
              <strong>{preview.local.total}</strong>
              <small>правил</small>
            </div>

            <div className="smart-routing-sync-stat">
              <span>Brume 3</span>
              <strong>{preview.remote.total}</strong>
              <small>правил</small>
            </div>

            <div className="smart-routing-sync-stat">
              <span>Совпадают</span>
              <strong>{preview.diff.same.length}</strong>
              <small>правил</small>
            </div>

            <div className="smart-routing-sync-stat">
              <span>Brume → localhost</span>
              <strong>{remoteOnly.length}</strong>
              <small>новых</small>
            </div>

            <div className="smart-routing-sync-stat">
              <span>localhost → Brume</span>
              <strong>{localOnly.length}</strong>
              <small>новых</small>
            </div>
          </div>

          <div className="smart-routing-runtime">
            <div className="smart-routing-runtime-header">
              <div>
                <div className="eyebrow">RUNTIME BRUME 3</div>
                <h4>
                  {dirty
                    ? 'Требуется Apply'
                    : runtimeHealthy
                      ? 'Применён'
                      : 'Состояние требует проверки'}
                </h4>
              </div>

              {dirty ? (
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => void handleApply()}
                  disabled={applying || pulling || pushing}
                >
                  {applying
                    ? 'Применяем…'
                    : 'Применить runtime'}
                </button>
              ) : (
                <span
                  className={
                    runtimeHealthy
                      ? 'smart-routing-runtime-badge smart-routing-runtime-badge-ok'
                      : 'smart-routing-runtime-badge'
                  }
                >
                  {runtimeHealthy
                    ? 'OK'
                    : 'Проверить'}
                </span>
              )}
            </div>

            <div className="smart-routing-runtime-grid">
              <div className="smart-routing-runtime-item">
                <span>DIRECT mangle</span>
                <strong>
                  {directMangleCount ?? '—'}
                </strong>
                <small>
                  ожидается 1
                </small>
              </div>

              <div className="smart-routing-runtime-item">
                <span>STATIC mangle</span>
                <strong>
                  {staticMangleCount ?? '—'}
                </strong>
                <small>
                  ожидается 1
                </small>
              </div>

              <div className="smart-routing-runtime-item">
                <span>MAXVPN_DIRECT</span>
                <strong>
                  {directIpSet === true
                    ? 'Есть'
                    : directIpSet === false
                      ? 'Нет'
                      : '—'}
                </strong>
                <small>
                  runtime set
                </small>
              </div>

              <div className="smart-routing-runtime-item">
                <span>STATIC DIRECT</span>
                <strong>
                  {staticIpSet === true
                    ? 'Есть'
                    : staticIpSet === false
                      ? 'Нет'
                      : '—'}
                </strong>
                <small>
                  runtime set
                </small>
              </div>

              <div className="smart-routing-runtime-item smart-routing-runtime-item-wide">
                <span>Policy routing</span>
                <strong>
                  {policyRoutingActive
                    ? '0x64 → table 200'
                    : 'Не подтверждено'}
                </strong>
                <small>
                  fwmark policy
                </small>
              </div>
            </div>

            {table200 && (
              <details className="smart-routing-runtime-details">
                <summary>
                  Маршруты table 200
                </summary>
                <pre>{table200}</pre>
              </details>
            )}

            <div className="smart-routing-runtime-note">
              AWG table 100 контролируется отдельно и не изменяется
              операциями Smart Routing.
            </div>
          </div>

          {(semanticMismatches.length > 0 ||
            orderMismatches.length > 0) && (
            <div className="alert alert-error smart-routing-sync-error">
              Синхронизация остановлена: обнаружен конфликт
              параметров правил.
            </div>
          )}

          {(remoteOnly.length > 0 || diagnosticRelinks.length > 0) &&
            semanticMismatches.length === 0 &&
            orderMismatches.length === 0 && (
              <div className="smart-routing-sync-pull">
                <div>
                  <strong>
                    {remoteOnly.length > 0
                      ? `На Brume 3 есть ${remoteOnly.length} новых правил`
                      : 'Найдены правила без диагностической группы'}
                  </strong>

                  {diagnosticRelinks.length > 0 && (
                    <div className="smart-routing-sync-repair-note">
                      Найдено {diagnosticRelinks.length} правил, которые уже
                      есть на localhost, но не привязаны к диагностическим
                      группам. Их классификация будет восстановлена.
                    </div>
                  )}

                  {remoteOnly.length > 0 && (
                    <div className="smart-routing-sync-list">
                      {remoteOnly.map((rule) => (
                        <span key={`${rule.target_type}:${rule.target}`}>
                          {targetLabel(rule)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => void handlePull()}
                  disabled={pulling || pushing || applying}
                >
                  {pulling
                    ? 'Синхронизируем…'
                    : remoteOnly.length > 0
                      ? `Импортировать ${remoteOnly.length}`
                      : 'Исправить диагностику'}
                </button>
              </div>
            )}

          {localOnly.length > 0 &&
            semanticMismatches.length === 0 &&
            orderMismatches.length === 0 && (
              <div className="smart-routing-sync-push">
                <div>
                  <strong>
                    На localhost есть {localOnly.length} правил,
                    которых нет на Brume 3
                  </strong>

                  <div className="smart-routing-sync-list">
                    {localOnly.map((rule) => (
                      <span key={`${rule.target_type}:${rule.target}`}>
                        {targetLabel(rule)}
                      </span>
                    ))}
                  </div>

                  <small>
                    Существующие правила Brume 3 не удаляются.
                    После Push потребуется Apply.
                  </small>
                </div>

                <div className="smart-routing-sync-push-actions">
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={() => void handlePush()}
                    disabled={
                      pulling ||
                      pushing ||
                      applying ||
                      deletingLocalOnly
                    }
                  >
                    {pushing
                      ? 'Отправляем…'
                      : `Отправить ${localOnly.length}`}
                  </button>

                  <button
                    type="button"
                    className="button button-danger"
                    onClick={() => void handleDeleteLocalOnly()}
                    disabled={
                      pulling ||
                      pushing ||
                      applying ||
                      deletingLocalOnly
                    }
                  >
                    {deletingLocalOnly
                      ? 'Удаляем…'
                      : `Удалить ${localOnly.length}`}
                  </button>
                </div>
              </div>
            )}

          {fullySynchronized && (
            <div className="smart-routing-sync-ok">
              <strong>
                Конфигурации синхронизированы
              </strong>
              <span>
                {preview.remote.total} правил на обеих сторонах.
              </span>
            </div>
          )}

          {protectedLocalOnly.length > 0 && (
            <div className="smart-routing-sync-preserved">
              Локальные дополнительные правила:
              <strong>
                {protectedLocalOnly.length}
              </strong>
              {' — '}
              они сохраняются и не удаляются при Pull.
            </div>
          )}

          {pullResult && pullResult.created_count && pullResult.created_count > 0 && (
            <div className="smart-routing-sync-result">
              Импортировано:
              <strong>{pullResult.created_count}</strong> правил.
            </div>
          )}

          {pullResult && pullResult.relinked_count && pullResult.relinked_count > 0 && (
            <div className="smart-routing-sync-result">
              Восстановлена привязка к диагностике:
              <strong>{pullResult.relinked_count}</strong> правил.
            </div>
          )}

          {pushResult?.pushed &&
            pushResult.created_count &&
            pushResult.created_count > 0 && (
              <div className="smart-routing-sync-result">
                На Brume 3 отправлено:
                <strong>
                  {pushResult.created_count}
                </strong>
                правил.
                {pushResult.apply_required && (
                  <span>
                    {' '}
                    Runtime требует Apply.
                  </span>
                )}
              </div>
            )}
        </>
      )}
    </section>
  )
}
