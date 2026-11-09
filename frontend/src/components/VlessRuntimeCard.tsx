import { getLatestMeasurementDelay, getLatestMeasurementSource, sortProfilesByLatestMeasurement } from '../utils/vlessMeasurements'
import {
  normalizeUrltestToleranceMs,
  normalizeVlessRuntimeSettingsFromApi,
  prepareVlessRuntimeSettingsForSave,
} from '../utils/vlessRuntimeSettings'
import {
  formatVlessOutboundLabel,
  getOutboundTagForLocalProfile,
  resolveDisplayedActiveVlessProfile,
  resolveVlessProfileForOutbound,
} from '../utils/vlessSelectionIdentity'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  deleteVlessProfile,
  exportVlessProfilesForAppliance,
  getVlessProfiles,
  getVlessRuntime,
  getVlessRuntimeSettings,
  importVlessProfile,
  importVlessProfiles,
  prepareVlessRuntime,
  selectVlessOutbound,
  setVlessProfileEnabled,
  startVlessRuntime,
  stopVlessRuntime,
  getVlessProfileDelayHistory,
  getVlessSelectionHistory,
  getVlessApplianceSyncStatus,
  setVlessApplianceKillSwitch,
  synchronizeVlessFromAppliance,
  testVlessProfileDelays,
  updateVlessRuntimeSettings,
  validateVlessProfile,
} from '../api/client'
import type {
  VlessProfile,
  VlessProfileBatchImportResponse,
  VlessProfileDelayItem,
  VlessProfileDelayResponse,
  VlessProfileValidation,
  VlessRuntime,
  VlessRuntimeSettings,
  VlessSelectionHistoryResponse,
  VlessSelectionDelaySample,
  VlessApplianceSyncStatus,
} from '../types/api'
import { ServerCountryLabel } from './ServerCountryLabel'

type RuntimeAction = 'prepare' | 'start' | 'stop'

type ProfileFilter = 'all' | 'available' | 'no-response'

const APPLIANCE_SELECTION_BASELINE_KEY = 'maxvpn.vless.appliance-selection-baseline.v1'

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const remainingSeconds = total % 60
  if (days) return `${days} д ${hours} ч`
  if (hours) return `${hours} ч ${minutes} мин`
  if (minutes) return `${minutes} мин ${remainingSeconds} с`
  return `${remainingSeconds} с`
}

function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? value : new Date(timestamp).toLocaleString()
}

function selectionFreshnessLabel(value: string | undefined): string {
  if (value === 'fresh') return 'оба измерения свежие'
  if (value === 'stale') return 'есть устаревшее измерение'
  if (value === 'incomplete') return 'недостаточно данных'
  return 'свежесть неизвестна'
}

function selectionDiagnosticLabel(value: string | undefined): string {
  const labels: Record<string, string> = {
    consistent_with_latest_delays: 'Согласуется с последними измерениями',
    not_explained_by_latest_delays: 'Не объясняется последними измерениями',
    stale_measurements: 'Измерения устарели',
    insufficient_data: 'Недостаточно данных',
    insufficient_configuration: 'Не хватает параметров URLTest',
    observation_gap: 'Перерыв в наблюдениях',
    selection_mode_changed: 'Изменился режим выбора',
    manual_selection: 'Ручной выбор',
  }
  return value ? (labels[value] ?? value) : 'Диагностика не сохранена'
}

function formatDelay(item: VlessProfileDelayItem | undefined, nowMs = Date.now()): string {
  if (!item || !item.last_checked_at) return 'Не проверено'
  if (item.reachable && typeof item.delay_ms === 'number') return `${item.delay_ms} мс`
  if (item.first_failed_at) {
    const started = Date.parse(item.first_failed_at)
    const seconds = Number.isNaN(started)
      ? (item.unavailable_seconds ?? 0)
      : Math.max(0, Math.floor((nowMs - started) / 1000))
    return `Нет ответа · ${formatDuration(seconds)}`
  }
  return 'Нет ответа'
}

function formatDelayDetails(item: VlessProfileDelayItem | undefined): string {
  if (!item || !item.last_checked_at) return ''
  const parts = [`Проверено backend localhost:8080: ${formatTimestamp(item.last_checked_at)}`]
  if (item.first_failed_at) {
    parts.push(`Первый отказ в проверках localhost:8080: ${formatTimestamp(item.first_failed_at)}`)
    parts.push(`Неудачных проверок localhost подряд: ${item.consecutive_failures}`)
    if (item.last_success_at) parts.push(`Последний успех: ${formatTimestamp(item.last_success_at)}`)
  } else if (item.last_recovered_at) {
    parts.push(`Восстановлен: ${formatTimestamp(item.last_recovered_at)}`)
    if (item.last_outage_duration_seconds !== null) {
      parts.push(`Последний простой: ${formatDuration(item.last_outage_duration_seconds)}`)
    }
  } else if (item.last_success_at) {
    parts.push(`Последний успех: ${formatTimestamp(item.last_success_at)}`)
  }
  return parts.join(' · ')
}

function urltestIntervalSeconds(value: string | null | undefined): number | null {
  if (!value) return null
  const match = value.trim().match(/^(\d+(?:\.\d+)?)(ms|s|m|h)$/i)
  if (!match) return null
  const amount = Number(match[1])
  const unit = match[2].toLowerCase()
  if (!Number.isFinite(amount) || amount <= 0) return null
  const multiplier = unit === 'ms' ? 0.001 : unit === 's' ? 1 : unit === 'm' ? 60 : 3600
  return amount * multiplier
}

function measurementAgeSeconds(value: string | null | undefined, nowMs = Date.now()): number | null {
  if (!value) return null
  const measuredAt = Date.parse(value)
  if (!Number.isFinite(measuredAt)) return null
  return Math.max(0, Math.floor((nowMs - measuredAt) / 1000))
}

function isMeasurementStale(
  value: string | null | undefined,
  interval: string | null | undefined,
  nowMs = Date.now(),
): boolean {
  const age = measurementAgeSeconds(value, nowMs)
  const threshold = urltestIntervalSeconds(interval)
  return age !== null && threshold !== null && age > threshold
}

function formatManualMeasurementAge(
  item: VlessProfileDelayItem | undefined,
  interval: string | null | undefined,
  nowMs = Date.now(),
): string {
  if (!item?.last_checked_at) return 'Ручная проверка ещё не выполнялась'
  const age = measurementAgeSeconds(item.last_checked_at, nowMs)
  const threshold = urltestIntervalSeconds(interval)
  if (age === null) return `Измерено ${formatTimestamp(item.last_checked_at)} · возраст неизвестен`
  const ageLabel = `Измерено ${formatTimestamp(item.last_checked_at)} · возраст ${formatDuration(age)}`
  if (threshold !== null && age > threshold) {
    return `${ageLabel} · УСТАРЕЛО: старше интервала URLTest (${interval}); это сохранённый результат ручной проверки, а не текущее измерение URLTest`
  }
  if (threshold !== null) {
    return `${ageLabel} · сохранённый результат ручной проверки; не является измерением URLTest`
  }
  return `${ageLabel} · порог свежести неизвестен; не является измерением URLTest`
}

function formatUrltestMeasurement(
  current: VlessSelectionHistoryResponse['current'],
  nowMs = Date.now(),
): string {
  if (!current) return 'URLTest (sing-box): нет снимка состояния'
  const delay = current.active_delay_ms == null ? 'нет измерения' : `${current.active_delay_ms} мс`
  const measuredAt = current.active_delay_observed_at
  if (!measuredAt) return `URLTest (sing-box): ${delay} · время измерения неизвестно · свежесть неизвестна`
  const age = measurementAgeSeconds(measuredAt, nowMs)
  if (age === null) return `URLTest (sing-box): ${delay} · время измерения не распознано · свежесть неизвестна`
  const threshold = urltestIntervalSeconds(current.urltest_interval)
  const ageLabel = `измерено ${formatTimestamp(measuredAt)} · возраст ${formatDuration(age)}`
  if (threshold !== null && age > threshold) {
    return `URLTest (sing-box): ${delay} · ${ageLabel} · УСТАРЕЛО: возраст больше интервала ${current.urltest_interval}`
  }
  if (threshold !== null) {
    return `URLTest (sing-box): ${delay} · ${ageLabel} · в пределах интервала ${current.urltest_interval}`
  }
  return `URLTest (sing-box): ${delay} · ${ageLabel} · интервал для оценки свежести неизвестен`
}

function formatUrltestProfileMeasurement(
  sample: VlessSelectionDelaySample | undefined,
  interval: string | null | undefined,
  nowMs = Date.now(),
): string {
  if (!sample) return 'Нет данных по этому серверу в API sing-box'
  const measuredAt = sample.observed_at
  if (!measuredAt) {
    return sample.delay_ms == null
      ? 'Нет успешного измерения; время последнего замера неизвестно'
      : 'Время измерения неизвестно'
  }
  const age = measurementAgeSeconds(measuredAt, nowMs)
  if (age === null) return `Время измерения не распознано: ${measuredAt}`
  const ageLabel = `Измерено ${formatTimestamp(measuredAt)} · возраст ${formatDuration(age)}`
  if (sample.delay_ms == null) return `${ageLabel} · успешная задержка не получена`
  const threshold = urltestIntervalSeconds(interval)
  if (threshold !== null && age > threshold) {
    return `${ageLabel} · УСТАРЕЛО: старше интервала URLTest (${interval})`
  }
  if (threshold !== null) return `${ageLabel} · в пределах интервала URLTest (${interval})`
  return `${ageLabel} · свежесть неизвестна: интервал URLTest не определён`
}

function formatLatestManualMeasurementAge(
  item: VlessProfileDelayItem | undefined,
  interval: string | null | undefined,
  nowMs = Date.now(),
): string {
  if (!item?.last_checked_at) return 'Время измерения неизвестно'
  const age = measurementAgeSeconds(item.last_checked_at, nowMs)
  const threshold = urltestIntervalSeconds(interval)
  if (age === null) return `Время измерения не распознано: ${item.last_checked_at}`
  const label = `Измерено ${formatTimestamp(item.last_checked_at)} · возраст ${formatDuration(age)}`
  if (threshold !== null && age > threshold) return `${label} · УСТАРЕЛО`
  if (threshold !== null) return `${label} · в пределах интервала ${interval}`
  return `${label} · свежесть неизвестна`
}

export function VlessRuntimeCard() {
  const [profiles, setProfiles] = useState<VlessProfile[]>([])
  const [runtime, setRuntime] = useState<VlessRuntime | null>(null)
  const [settings, setSettings] = useState<VlessRuntimeSettings>({ urltest_interval: '3m', urltest_tolerance_ms: 50 })
  const [savingSettings, setSavingSettings] = useState(false)
  const [source, setSource] = useState('')
  const [profileName, setProfileName] = useState('')
  const [validation, setValidation] = useState<VlessProfileValidation | null>(null)
  const [delayResults, setDelayResults] = useState<Record<number, VlessProfileDelayItem>>({})
  const [selectionHistory, setSelectionHistory] = useState<VlessSelectionHistoryResponse | null>(null)
  const [selectionHistoryError, setSelectionHistoryError] = useState<string | null>(null)
  const [selectionHistoryExpanded, setSelectionHistoryExpanded] = useState(false)
  const [visibleSelectionHistoryCount, setVisibleSelectionHistoryCount] = useState(5)
  const [applianceSyncStatus, setApplianceSyncStatus] = useState<VlessApplianceSyncStatus | null>(null)
  const [applianceSyncError, setApplianceSyncError] = useState<string | null>(null)
  const [syncingAppliance, setSyncingAppliance] = useState(false)
  const [savingKillSwitch, setSavingKillSwitch] = useState(false)
  const [selectionModeChanged, setSelectionModeChanged] = useState(false)
  const selectionBaselineRef = useRef<string | null>(null)
  const [clockNow, setClockNow] = useState(0)
  const [busy, setBusy] = useState(false)
  const [runtimeAction, setRuntimeAction] = useState<RuntimeAction | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [testingDelays, setTestingDelays] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [batchResult, setBatchResult] = useState<VlessProfileBatchImportResponse | null>(null)
  const [showAllProfiles, setShowAllProfiles] = useState(false)
  const [profileSearch, setProfileSearch] = useState('')
  const [profileFilter, setProfileFilter] = useState<ProfileFilter>('all')

  useEffect(() => {
    const initialTimer = window.setTimeout(() => setClockNow(Date.now()), 0)
    const timer = window.setInterval(() => setClockNow(Date.now()), 30_000)
    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [])

  const refreshData = useCallback(async () => {
    setRefreshing(true)
    const [profilesResult, runtimeResult, settingsResult, delayHistoryResult, selectionHistoryResult] = await Promise.allSettled([
      getVlessProfiles(),
      getVlessRuntime(),
      getVlessRuntimeSettings(),
      getVlessProfileDelayHistory(),
      getVlessSelectionHistory(),
    ])
    if (profilesResult.status === 'fulfilled') {
      setProfiles(profilesResult.value)
    } else {
      setError(errorText(profilesResult.reason, 'Не удалось загрузить список VLESS-серверов.'))
    }
    if (runtimeResult.status === 'fulfilled') {
      setRuntime(runtimeResult.value)
    } else {
      setError((previous) => previous ?? errorText(runtimeResult.reason, 'Не удалось получить состояние sing-box.'))
    }
    if (settingsResult.status === 'fulfilled') setSettings(normalizeVlessRuntimeSettingsFromApi(settingsResult.value))
    if (delayHistoryResult.status === 'fulfilled') {
      setDelayResults(Object.fromEntries(delayHistoryResult.value.results.map((item) => [item.profile_id, item] as const)))
    }
    if (selectionHistoryResult.status === 'fulfilled') {
      setSelectionHistory(selectionHistoryResult.value)
      setSelectionHistoryError(null)
    } else {
      setSelectionHistoryError(errorText(selectionHistoryResult.reason, 'Не удалось обновить измерения URLTest из sing-box.'))
    }
    setInitialLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshData()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshData])

  const acceptApplianceSyncStatus = useCallback((status: VlessApplianceSyncStatus, resetSelectionBaseline = false) => {
    setApplianceSyncStatus(status)
    setApplianceSyncError(null)
    if (status.selection_signature === 'unknown') return

    let baseline = selectionBaselineRef.current
    let storageAvailable = true
    try {
      baseline = window.localStorage.getItem(APPLIANCE_SELECTION_BASELINE_KEY) ?? baseline
    } catch {
      storageAvailable = false
    }

    if (resetSelectionBaseline) {
      selectionBaselineRef.current = status.selection_signature
      if (storageAvailable) {
        try {
          window.localStorage.setItem(APPLIANCE_SELECTION_BASELINE_KEY, status.selection_signature)
        } catch {
          // The in-memory baseline still detects drift for this page session.
        }
      }
      setSelectionModeChanged(false)
      return
    }

    if (!baseline) {
      // A first visit must not silently accept a router-side manual pin as already
      // synchronized. Treat auto as the initial baseline; an explicit sync acknowledges
      // an existing manual selection and records its signature.
      baseline = status.selection_mode === 'manual' ? 'auto' : status.selection_signature
      selectionBaselineRef.current = baseline
      if (storageAvailable) {
        try {
          window.localStorage.setItem(APPLIANCE_SELECTION_BASELINE_KEY, baseline)
        } catch {
          // The in-memory baseline still detects drift for this page session.
        }
      }
      setSelectionModeChanged(baseline !== status.selection_signature)
      return
    }

    selectionBaselineRef.current = baseline
    setSelectionModeChanged(baseline !== status.selection_signature)
  }, [])

  const refreshApplianceSyncStatus = useCallback(async (resetSelectionBaseline = false) => {
    try {
      const result = await getVlessApplianceSyncStatus()
      acceptApplianceSyncStatus(result, resetSelectionBaseline)
    } catch (syncStatusError) {
      setApplianceSyncError(errorText(syncStatusError, 'Не удалось проверить состояние maxvpn.lan.'))
    }
  }, [acceptApplianceSyncStatus])

  useEffect(() => {
    const initialTimer = window.setTimeout(() => {
      void refreshApplianceSyncStatus()
    }, 0)
    const timer = window.setInterval(() => void refreshApplianceSyncStatus(), 30_000)
    return () => {
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [refreshApplianceSyncStatus])

  useEffect(() => {
    let cancelled = false
    const loadSelectionHistory = async () => {
      try {
        const result = await getVlessSelectionHistory()
        if (!cancelled) {
          setSelectionHistory(result)
          setSelectionHistoryError(null)
        }
      } catch (loadError) {
        if (!cancelled) {
          setSelectionHistoryError(
            loadError instanceof Error ? loadError.message : 'Журнал переключений недоступен',
          )
        }
      }
    }
    void loadSelectionHistory()
    const timer = window.setInterval(() => void loadSelectionHistory(), 30_000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const enabledCount = profiles.filter((profile) => profile.enabled).length
  const selectedOutboundMatch = runtime?.selected_outbound?.match(/^vless-profile-([1-9][0-9]*)$/)
  const selectedProfileId = runtime && runtime.selected_profile_id !== undefined
    ? runtime.selected_profile_id
    : selectedOutboundMatch ? Number(selectedOutboundMatch[1]) : null
  const automaticSelection = runtime?.selection_mode
    ? runtime.selection_mode === 'auto'
    : (!runtime?.selected_outbound || runtime.selected_outbound === 'vless-auto')
  const legacyRuntimeConfiguration = runtime?.runtime_config_mode === 'single_profile'
  const profileIdMap = selectionHistory?.profile_id_map
  const outboundTagForLocalProfile = (profileId: number): string | null => (
    getOutboundTagForLocalProfile(profileId, profileIdMap)
  )
  const profileForOutbound = (outbound: string | null | undefined) => (
    resolveVlessProfileForOutbound(profiles, outbound, profileIdMap)
  )

  // Prefer a recently observed appliance snapshot over a lagging runtime poll.
  const activeProfile = resolveDisplayedActiveVlessProfile(
    profiles,
    runtime,
    selectionHistory?.current,
    profileIdMap,
  )
  const activeProfileId = activeProfile?.id ?? null

  const activeUrltestTag = activeProfile ? outboundTagForLocalProfile(activeProfile.id) : null
  const activeUrltestSample = activeUrltestTag
    ? selectionHistory?.current?.profile_delays?.[activeUrltestTag]
    : undefined
  const activeManualSample = activeProfile ? delayResults[activeProfile.id] : undefined
  const activeMeasurementSource = getLatestMeasurementSource(activeManualSample, activeUrltestSample)
  const activeUrltestInterval = selectionHistory?.current?.urltest_interval ?? settings.urltest_interval
  const urltestProfileDelays = selectionHistory?.current?.profile_delays

  const visibleProfiles = useMemo(() => {
    const query = profileSearch.trim().toLocaleLowerCase()
    return profiles
      .filter((profile) => {
        const searchable = [profile.name, profile.address, profile.server_name ?? '', `${profile.address}:${profile.port}`]
        if (query && !searchable.some((value) => value.toLocaleLowerCase().includes(query))) return false
        const measured = Object.prototype.hasOwnProperty.call(delayResults, profile.id)
        if (profileFilter === 'available') return measured && delayResults[profile.id]?.reachable === true
        if (profileFilter === 'no-response') return measured && !!delayResults[profile.id]?.last_checked_at && delayResults[profile.id]?.reachable === false
        return true
      })
      .sort((a, b) => {
        const aTag = getOutboundTagForLocalProfile(a.id, profileIdMap)
        const bTag = getOutboundTagForLocalProfile(b.id, profileIdMap)
        const aSample = aTag ? urltestProfileDelays?.[aTag] : undefined
        const bSample = bTag ? urltestProfileDelays?.[bTag] : undefined
        const aDelay = getLatestMeasurementDelay(
          getLatestMeasurementSource(delayResults[a.id], aSample),
          delayResults[a.id],
          aSample,
        )
        const bDelay = getLatestMeasurementDelay(
          getLatestMeasurementSource(delayResults[b.id], bSample),
          delayResults[b.id],
          bSample,
        )
        return aDelay - bDelay || a.id - b.id
      })
  }, [profiles, delayResults, urltestProfileDelays, profileIdMap, profileSearch, profileFilter])

  function clearResults() {
    setError(null)
    setMessage(null)
    setBatchResult(null)
  }

  async function handleValidate() {
    const normalized = source.trim()
    clearResults()
    if (!normalized) {
      setError('Вставьте VLESS-ссылку или JSON-конфигурацию.')
      return
    }
    const validationLines = normalized.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
    const looksLikeBatch = validationLines.length > 1 && validationLines.some((line) => line.toLowerCase().startsWith('vless://'))
    if (looksLikeBatch) {
      setError('Пакетная проверка выполняется при импорте: результат будет показан отдельно для каждой строки.')
      return
    }
    setBusy(true)
    try {
      const result = await validateVlessProfile(normalized)
      setValidation(result)
      if (!result.valid) setError(result.reason ?? 'Конфигурация не прошла проверку.')
      else setMessage('Профиль прошёл проверку.')
    } catch (validateError) {
      setValidation(null)
      setError(errorText(validateError, 'Не удалось проверить профиль.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleImport() {
    const normalized = source.trim()
    clearResults()
    setValidation(null)
    if (!normalized) {
      setError('Вставьте VLESS-ссылку или JSON-конфигурацию.')
      return
    }

    const inputLines = normalized
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
    const lines = inputLines.length > 1 && inputLines.some((line) => line.toLowerCase().startsWith('vless://'))
      ? inputLines
      : []

    setBusy(true)
    try {
      if (lines.length > 1) {
        const result = await importVlessProfiles(lines)
        setBatchResult(result)
        setMessage(`Импорт завершён: добавлено ${result.imported} из ${result.total}; ошибок ${result.failed}; дублей ${result.duplicates}.`)
      } else {
        const singleSource = normalized
        const check = await validateVlessProfile(singleSource)
        setValidation(check)
        if (!check.valid) {
          setError(check.reason ?? 'Конфигурация не прошла проверку.')
          return
        }
        await importVlessProfile(singleSource, profileName.trim() || check.name || 'VLESS REALITY')
        setMessage('VLESS-сервер добавлен в список. Он будет включён в конфигурацию после следующего запуска sing-box.')
      }
      setSource('')
      await refreshData()
    } catch (importError) {
      setError(errorText(importError, 'Не удалось импортировать VLESS-серверы.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleRuntimeAction(action: RuntimeAction) {
    setRuntimeAction(action)
    setError(null)
    setMessage(null)
    try {
      const result = action === 'prepare'
        ? await prepareVlessRuntime()
        : action === 'start'
          ? await startVlessRuntime()
          : await stopVlessRuntime()
      setRuntime(result)
      setMessage(result.message)
      await refreshData()
    } catch (actionError) {
      setError(errorText(actionError, 'Не удалось выполнить действие sing-box.'))
      await refreshData()
    } finally {
      setRuntimeAction(null)
    }
  }

  async function handleSelect(profileId: number | null) {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await selectVlessOutbound(profileId)
      setRuntime(result)
      setMessage(profileId === null ? 'Автоматический выбор серверов включён.' : 'Выбран сервер вручную.')
      await refreshApplianceSyncStatus(true)
    } catch (selectError) {
      setError(errorText(selectError, 'Не удалось изменить выбранный сервер.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleToggle(profile: VlessProfile) {
    setBusy(true)
    clearResults()
    try {
      await setVlessProfileEnabled(profile.id, !profile.enabled)
      await refreshData()
      setMessage(`Состояние сервера «${profile.name}» изменено. Для применения новой конфигурации перезапустите sing-box.`)
    } catch (toggleError) {
      setError(errorText(toggleError, 'Не удалось изменить состояние сервера.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(profile: VlessProfile) {
    if (!window.confirm(`Удалить VLESS-сервер «${profile.name}»?`)) return
    setBusy(true)
    clearResults()
    try {
      await deleteVlessProfile(profile.id)
      await refreshData()
      setMessage(`Сервер «${profile.name}» удалён. Для применения новой конфигурации перезапустите sing-box.`)
    } catch (deleteError) {
      setError(errorText(deleteError, 'Не удалось удалить сервер.'))
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveSettings() {
    setSavingSettings(true)
    setError(null)
    setMessage(null)
    try {
      const saved = await updateVlessRuntimeSettings(prepareVlessRuntimeSettingsForSave(settings))
      setSettings(normalizeVlessRuntimeSettingsFromApi(saved))
      setMessage(runtime?.running
        ? 'Параметры сохранены. Остановите и запустите sing-box, чтобы применить их.'
        : 'Параметры автоматического выбора сохранены.')
    } catch (settingsError) {
      setError(errorText(settingsError, 'Не удалось сохранить параметры автоматического выбора.'))
    } finally {
      setSavingSettings(false)
    }
  }

  async function handleExportForAppliance() {
    setError(null)
    setMessage(null)
    try {
      const bundle = await exportVlessProfilesForAppliance()
      const blob = new Blob([JSON.stringify(bundle, null, 2) + '\n'], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'maxvpn-vless-profiles.json'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage(`Экспортировано профилей: ${bundle.profiles.length}. Файл содержит секреты подключения — храните его в безопасном месте.`)
    } catch (exportError) {
      setError(errorText(exportError, 'Не удалось экспортировать VLESS-профили.'))
    }
  }

  async function handleSynchronizeFromAppliance() {
    setSyncingAppliance(true)
    setError(null)
    setMessage(null)
    try {
      // Always re-read the diff just before asking for confirmation; a cached poll
      // may miss a router-side profile deletion that happened seconds ago.
      const latestStatus = await getVlessApplianceSyncStatus()
      acceptApplianceSyncStatus(latestStatus)
      const localOnly = latestStatus.local_only ?? []
      const confirmDeleteLocalOnly = localOnly.length > 0
        ? window.confirm(
            `На localhost:8080 есть ${localOnly.length} профиль(я), которых нет на maxvpn.lan. Синхронизация удалит их из локального списка и загрузит сохранённый список роутера. Продолжить?`,
          )
        : false
      if (localOnly.length > 0 && !confirmDeleteLocalOnly) return
      const result = await synchronizeVlessFromAppliance(confirmDeleteLocalOnly)
      acceptApplianceSyncStatus(result, true)
      await refreshData()
      const details = result.sync_result
      const settingsWarning = result.settings_changed
        ? ' Параметры URLTest на localhost:8080 не удалось полностью синхронизировать; проверьте настройки backend.'
        : ''
      setMessage(
        `Синхронизация с maxvpn.lan завершена: добавлено ${details?.imported ?? 0}, обновлено ${details?.updated ?? 0}, удалено ${details?.deleted ?? 0}. Сохранённый выбор роутера: ${result.selection_mode === 'manual' ? `ручной${result.selected_profile ? ` · ${result.selected_profile}` : ''}` : result.selection_mode === 'auto' ? 'автоматический' : 'не определён'}. sing-box не перезапускался.${result.selection_pending ? ` Выбор ещё не применён: работающий sing-box пока использует ${result.runtime_selection_mode === 'manual' ? 'ручной режим' : result.runtime_selection_mode === 'auto' ? 'автовыбор' : 'неподтверждённый режим'}. Нажмите «Применить и запустить / перезапустить» на maxvpn.lan.` : ''}${settingsWarning}`,
      )
    } catch (syncError) {
      setError(errorText(syncError, 'Не удалось синхронизировать состояние с maxvpn.lan.'))
      await refreshApplianceSyncStatus()
    } finally {
      setSyncingAppliance(false)
    }
  }

  async function handleToggleKillSwitch() {
    const current = applianceSyncStatus?.kill_switch_enabled
    if (typeof current !== 'boolean' || savingKillSwitch) return
    setSavingKillSwitch(true)
    setError(null)
    setMessage(null)
    try {
      const result = await setVlessApplianceKillSwitch(!current)
      setApplianceSyncStatus((previous) => previous
        ? { ...previous, kill_switch_enabled: result.kill_switch_enabled }
        : previous)
      setMessage(result.kill_switch_enabled
        ? 'Kill Switch включён: при отказе всех VPN-серверов трафик LAN будет заблокирован.'
        : result.wan_fallback_active
          ? 'Kill Switch выключен; переход LAN через WAN уже активен.'
          : 'Kill Switch выключен: при отказе всех VPN-серверов роутер сможет переключить LAN на WAN.')
      await refreshApplianceSyncStatus()
    } catch (killSwitchError) {
      setError(errorText(killSwitchError, 'Не удалось изменить Kill Switch на maxvpn.lan.'))
      await refreshApplianceSyncStatus()
    } finally {
      setSavingKillSwitch(false)
    }
  }

  async function handleTestDelays() {
    setTestingDelays(true)
    setError(null)
    setMessage(null)
    try {
      const result: VlessProfileDelayResponse = await testVlessProfileDelays()
      setDelayResults((current) => ({ ...current, ...Object.fromEntries(result.results.map((item) => [item.profile_id, item] as const)) }))
      const reachable = result.results.filter((item) => item.reachable).length
      setMessage(`Проверка завершена: доступны ${reachable} из ${result.results.length} включённых серверов.`)
    } catch (testError) {
      setError(errorText(testError, 'Не удалось измерить задержку. Убедитесь, что sing-box запущен.'))
    } finally {
      setTestingDelays(false)
    }
  }

  const actionBusy = runtimeAction !== null
  const applianceSyncRequired = Boolean(applianceSyncStatus?.sync_required || selectionModeChanged || applianceSyncStatus?.selection_pending)

  return (
    <section className="vless-card" aria-labelledby="vless-card-title">
      <div className="vless-card-header">
        <div>
          <div className="vless-eyebrow">ALTERNATIVE VPN</div>
          <h2 id="vless-card-title">VLESS + REALITY</h2>
          <p className="vless-subtitle">До 50 серверов · автоматический выбор по задержке · sing-box</p>
        </div>
        <div className="vless-button-row">
          <button type="button" className="button button-secondary" onClick={() => void handleSynchronizeFromAppliance()} disabled={!applianceSyncStatus || Boolean(applianceSyncError) || syncingAppliance || busy || actionBusy}>
            {syncingAppliance ? 'Синхронизация…' : 'Синхронизировать с maxvpn.lan'}
          </button>
          <button type="button" className="button button-secondary" onClick={() => void handleExportForAppliance()} disabled={busy || actionBusy || profiles.length === 0}>
            Экспорт для maxvpn.lan
          </button>
          <button type="button" className="button button-secondary" onClick={() => { void refreshData(); void refreshApplianceSyncStatus() }} disabled={refreshing || busy || actionBusy}>
            {refreshing ? 'Обновление…' : 'Обновить'}
          </button>
        </div>
      </div>

      <div className="vless-important-note" role="note">
        <strong>Маршрутизация LAN управляется отдельно.</strong>
        <span>Конфигурация использует maxvpn0 и не меняет существующие правила DIRECT. Кнопка «Экспорт для maxvpn.lan» создаёт файл переноса с текущими профилями и настройками; он содержит секреты подключения.</span>
      </div>

      <div className="vless-runtime-summary">
        <div className="vless-state-item"><span>sing-box</span><strong className={runtime?.installed ? 'is-ready' : 'is-muted'}>{initialLoading ? 'Проверка…' : runtime?.installed ? 'Подготовлен' : 'Не установлен'}</strong></div>
        <div className="vless-state-item"><span>Процесс</span><strong className={runtime?.running ? 'is-ready' : 'is-muted'}>{initialLoading ? 'Проверка…' : runtime?.running ? 'Запущен' : 'Остановлен'}</strong></div>
        <div className="vless-state-item"><span>Включено серверов</span><strong>{enabledCount} / 50</strong></div>
        <div className="vless-state-item"><span>LAN через VLESS</span><strong className="is-muted">{runtime?.lan_routing_enabled ? 'Включён' : 'Не включён'}</strong></div>
      </div>

      {legacyRuntimeConfiguration && runtime?.running && (
        <div className="vless-important-note" role="status">
          <strong>Работающая конфигурация ещё не обновлена.</strong>
          <span>Сейчас sing-box использует один сервер из ранее установленной конфигурации. Список сохранённых серверов и автоматический выбор ещё не применены. Чтобы включить автовыбор, нужно перезапустить sing-box после проверки новой конфигурации.</span>
        </div>
      )}
      {error && <div className="vless-alert vless-alert-error" role="alert">{error}</div>}
      {message && <div className="vless-alert vless-alert-success" role="status">{message}</div>}
      {applianceSyncError && <div className="vless-alert vless-alert-error" role="alert">Не удалось проверить синхронизацию с maxvpn.lan: {applianceSyncError}</div>}
      {applianceSyncRequired && applianceSyncStatus && (
        <div className="vless-alert vless-alert-warning" role="status">
          <strong>Состояние VLESS + REALITY отличается от maxvpn.lan.</strong>
          <span>
            На роутере только: {applianceSyncStatus.on_router_only.length}; локально только: {applianceSyncStatus.local_only.length}; требуют обновления: {applianceSyncStatus.updated.length}; параметры URLTest отличаются: {applianceSyncStatus.settings_changed ? 'да' : 'нет'}.
            {selectionModeChanged ? ' Сохранённый режим или вручную закреплённый сервер на роутере изменился после последней синхронизации.' : ''}
            {applianceSyncStatus.selection_pending ? ` На maxvpn.lan есть выбор, ожидающий применения; сейчас работающий sing-box остаётся в режиме «${applianceSyncStatus.runtime_selection_mode === 'manual' ? 'ручной' : applianceSyncStatus.runtime_selection_mode === 'auto' ? 'автовыбор' : 'не подтверждён'}». Сначала примените изменения на роутере, затем повторите синхронизацию, если локальная панель должна отразить новый фактический режим.` : ''}
          </span>
          <span>Синхронизация заменит локальный список профилей данными роутера. Она не перезапускает sing-box и не меняет текущий маршрут.</span>
        </div>
      )}

      <div className="vless-runtime-controls">
        <div className="vless-card-header">
          <div>
            <h3>Kill Switch</h3>
            <p>
              {applianceSyncStatus?.kill_switch_enabled === true
                ? 'ON — если все VPN-серверы недоступны, трафик LAN блокируется.'
                : applianceSyncStatus?.kill_switch_enabled === false
                  ? 'OFF — если все VPN-серверы недоступны, разрешён переход LAN напрямую через WAN.'
                  : 'Состояние будет показано после подключения к maxvpn.lan.'}
            </p>
          </div>
          <button
            type="button"
            className={
              applianceSyncStatus?.kill_switch_enabled === false
                ? 'button button-danger'
                : 'button button-primary'
            }
            onClick={() => void handleToggleKillSwitch()}
            disabled={
              !applianceSyncStatus?.connected
              || Boolean(applianceSyncError)
              || typeof applianceSyncStatus?.kill_switch_enabled !== 'boolean'
              || savingKillSwitch
              || busy
              || syncingAppliance
            }
            aria-pressed={applianceSyncStatus?.kill_switch_enabled === true}
          >
            {savingKillSwitch
              ? 'Сохранение…'
              : applianceSyncStatus?.kill_switch_enabled === true
                ? 'Kill Switch: ON'
                : applianceSyncStatus?.kill_switch_enabled === false
                  ? 'Kill Switch: OFF'
                  : 'Kill Switch: —'}
          </button>
        </div>
        {applianceSyncError && (
          <p className="vless-inline-hint">Нет подтверждённой связи с maxvpn.lan; переключатель временно недоступен.</p>
        )}
      </div>

      <div className="vless-runtime-controls">
        <h3>Параметры автоматического выбора</h3>
        <div className="vless-button-row">
          <label className="vless-field">
            <span>Интервал проверки</span>
            <select value={settings.urltest_interval} onChange={(event) => setSettings((current) => ({ ...current, urltest_interval: event.target.value as VlessRuntimeSettings['urltest_interval'] }))} disabled={savingSettings || busy}>
              <option value="30s">30 секунд</option><option value="1m">1 минута</option><option value="2m">2 минуты</option><option value="3m">3 минуты</option><option value="5m">5 минут</option><option value="10m">10 минут</option>
            </select>
          </label>
          <label className="vless-field">
            <span>Допуск переключения (мс)</span>
            <input type="number" min={0} max={5000} step={25} value={normalizeUrltestToleranceMs(settings.urltest_tolerance_ms)} onChange={(event) => setSettings((current) => ({ ...current, urltest_tolerance_ms: Math.max(0, Math.min(5000, Number(event.target.value) || 0)) }))} disabled={savingSettings || busy} />
          </label>
          <button type="button" className="button button-secondary" onClick={() => void handleSaveSettings()} disabled={savingSettings || busy}>{savingSettings ? 'Сохранение…' : 'Сохранить параметры'}</button>
        </div>
        <p className="vless-inline-hint">Меньший допуск чаще переключает серверы. Больший допуск снижает переключения при незначительной разнице задержки.</p>
      </div>

      <div className="vless-runtime-controls">
        <div className="vless-card-header">
          <div><h3>Список серверов</h3><p>Автовыбор использует HTTPS-проверку через каждый VLESS-узел с заданным интервалом и допуском.</p></div>
          <button type="button" className="button button-secondary" onClick={() => void handleTestDelays()} disabled={!runtime?.running || testingDelays || busy}>
            {testingDelays ? 'Измерение…' : 'Проверить задержки'}
          </button>
        </div>
        <div className="vless-button-row">
          <button type="button" className="button button-primary" onClick={() => void handleSelect(null)} disabled={!runtime?.running || busy || automaticSelection}>
            {automaticSelection ? 'Автовыбор активен' : 'Включить автовыбор'}
          </button>
          <span className="vless-inline-hint">Текущий режим: {automaticSelection ? 'автоматический' : 'ручной'}{selectedProfileId ? ` · профиль №${selectedProfileId}` : ''}</span>
        </div>

        {profiles.length === 0 ? (
          <p className="vless-inline-hint">Серверы ещё не добавлены.</p>
        ) : (
          <>
            <div className="vless-active-server">
              <div className="vless-active-server-main">
                <span className="vless-section-label">
                  {activeProfile
                    ? automaticSelection
                      ? 'СЕЙЧАС ИСПОЛЬЗУЕТСЯ · АВТОВЫБОР'
                      : legacyRuntimeConfiguration
                        ? 'СЕЙЧАС ИСПОЛЬЗУЕТСЯ · ТЕКУЩАЯ КОНФИГУРАЦИЯ'
                        : 'ТЕКУЩИЙ СЕРВЕР · РУЧНОЙ ВЫБОР'
                    : runtime?.selection_mode === 'unknown'
                      ? 'ТЕКУЩИЙ СЕРВЕР НЕ ОПРЕДЕЛЁН'
                      : automaticSelection ? 'АВТОМАТИЧЕСКИЙ ВЫБОР' : 'РУЧНОЙ ВЫБОР'}
                </span>
                <strong>{activeProfile
                  ? <ServerCountryLabel source={activeProfile} />
                  : runtime?.active_server_address
                    ? <ServerCountryLabel source={{
                        address: runtime.active_server_address,
                        server_name: '',
                        name: runtime.active_server_address,
                      }} />
                    : automaticSelection
                      ? 'Автовыбор — активный узел не определён'
                      : 'Активный сервер не определён'}</strong>
                <span className="vless-profile-address">
                  {activeProfile
                    ? `${activeProfile.address}:${activeProfile.port}`
                    : runtime?.active_server_address
                      ? `${runtime.active_server_address}:${runtime.active_server_port ?? '—'}`
                      : runtime?.running
                        ? runtime?.selection_mode === 'unknown'
                          ? 'Не удалось определить действующий узел sing-box'
                          : `sing-box выбирает из ${enabledCount} включённых серверов`
                        : 'Текущий сервер отобразится после запуска sing-box'}
                </span>
              </div>
              <div className="vless-active-server-actions">
                {activeProfile && (
                  <>
                    <span className="vless-active-server-badge">{automaticSelection ? 'Автовыбор' : legacyRuntimeConfiguration ? 'Активная конфигурация' : 'Выбран вручную'}</span>
                    <div className="vless-active-latest-measurement" aria-label="Самый свежий результат измерения активного сервера">
                      {activeMeasurementSource === 'manual' ? (
                        <>
                          <strong className={activeManualSample?.reachable === false ? 'vless-urltest-result-manual-failed' : undefined} title={formatDelayDetails(activeManualSample)}>
                            Ручная проверка: {formatDelay(activeManualSample, clockNow)}
                          </strong>
                          <small className={isMeasurementStale(activeManualSample?.last_checked_at, activeUrltestInterval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                            {formatLatestManualMeasurementAge(activeManualSample, activeUrltestInterval, clockNow)}
                          </small>
                        </>
                      ) : activeMeasurementSource === 'urltest' ? (
                        <>
                          <strong className={activeUrltestSample?.delay_ms == null ? 'vless-urltest-result-no-delay' : undefined}>
                            URLTest · sing-box: {typeof activeUrltestSample?.delay_ms === 'number' ? `${activeUrltestSample.delay_ms} мс` : 'Нет измерения'}
                          </strong>
                          <small className={isMeasurementStale(activeUrltestSample?.observed_at, activeUrltestInterval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                            {formatUrltestProfileMeasurement(activeUrltestSample, activeUrltestInterval, clockNow)}
                          </small>
                        </>
                      ) : (
                        <strong className="vless-urltest-result-no-delay">Нет измерений</strong>
                      )}
                    </div>
                    {automaticSelection && runtime?.running && activeProfile.enabled && (
                      <button type="button" className="button button-secondary" onClick={() => void handleSelect(activeProfile.id)} disabled={busy}>
                        Закрепить сервер
                      </button>
                    )}
                    {!automaticSelection && runtime?.running && (
                      <button type="button" className="button button-secondary" onClick={() => void handleSelect(null)} disabled={busy}>
                        Вернуться к автовыбору
                      </button>
                    )}
                  </>
                )}
                {!activeProfile && <span className="vless-active-server-badge">{automaticSelection ? 'Автовыбор' : 'Нет данных'}</span>}
              </div>
            </div>

            <section className="vless-urltest-results" aria-labelledby="vless-urltest-results-title">
              <div className="vless-urltest-results-header">
                <div>
                  <h3 id="vless-urltest-results-title">Задержки серверов</h3>
                  <p className="vless-inline-hint">
                    Для каждого сервера показывается только самый свежий результат: ручная проверка или автоматический URLTest из sing-box.
                  </p>
                </div>
                <span className="vless-urltest-results-meta">
                  Интервал: {selectionHistory?.current?.urltest_interval ?? settings.urltest_interval} · допуск: {selectionHistory?.current?.urltest_tolerance_ms == null ? `${settings.urltest_tolerance_ms} мс` : `${selectionHistory?.current?.urltest_tolerance_ms} мс`}
                </span>
              </div>
              {selectionHistoryError && (
                <p className="vless-selection-history-error" role="status">
                  Не удалось обновить снимок URLTest: {selectionHistoryError}
                </p>
              )}
              {!selectionHistory?.current ? (
                <p className="vless-inline-hint">
                  Снимок URLTest пока недоступен. Нажмите «Обновить» после проверки, что sing-box запущен.
                </p>
              ) : (
                <>
                  <p className="vless-urltest-results-snapshot">
                    Снимок sing-box получен: {formatTimestamp(selectionHistory.current.observed_at)} · режим: {selectionHistory.current.selection_mode ?? '—'} · активный узел: {formatVlessOutboundLabel(profiles, selectionHistory.current.active_outbound, profileIdMap)}.
                  </p>
                  <div className="vless-urltest-results-list">
                    {sortProfilesByLatestMeasurement(
                    profiles.filter((profile) => profile.enabled),
                    (profile) => {
                      const tag = outboundTagForLocalProfile(profile.id)
                      const sample = tag ? selectionHistory.current?.profile_delays?.[tag] : undefined
                      const manualSample = delayResults[profile.id]
                      return getLatestMeasurementDelay(
                        getLatestMeasurementSource(manualSample, sample),
                        manualSample,
                        sample,
                      )
                    },
                  ).map((profile) => {
                      const tag = outboundTagForLocalProfile(profile.id)
                      const sample = tag ? selectionHistory.current?.profile_delays?.[tag] : undefined
                      const manualSample = delayResults[profile.id]
                      const latestSource = getLatestMeasurementSource(manualSample, sample)
                      const interval = selectionHistory.current?.urltest_interval ?? settings.urltest_interval
                      const active = tag != null && selectionHistory.current?.active_outbound === tag
                      return (
                        <article className={active ? 'vless-urltest-result vless-urltest-result-active' : 'vless-urltest-result'} key={profile.id}>
                          <div className="vless-urltest-result-server">
                            <strong><ServerCountryLabel source={profile} /></strong>
                            <span>{profile.address}:{profile.port}</span>
                            {active && <small>Активный узел</small>}
                          </div>
                          <div className="vless-urltest-result-measurement">
                            {latestSource === 'manual' ? (
                              <>
                                <strong
                                  className={manualSample?.reachable === false ? 'vless-urltest-result-manual-failed' : undefined}
                                  title={formatDelayDetails(manualSample)}
                                >
                                  Ручная проверка: {formatDelay(manualSample, clockNow)}
                                </strong>
                                <span className={isMeasurementStale(manualSample?.last_checked_at, interval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                                  {formatLatestManualMeasurementAge(manualSample, interval, clockNow)}
                                </span>
                              </>
                            ) : latestSource === 'urltest' ? (
                              <>
                                <strong className={sample?.delay_ms == null ? 'vless-urltest-result-no-delay' : undefined}>
                                  URLTest · sing-box: {sample?.delay_ms == null ? 'Нет измерения' : `${sample.delay_ms} мс`}
                                </strong>
                                <span className={isMeasurementStale(sample?.observed_at, interval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                                  {formatUrltestProfileMeasurement(sample, interval, clockNow)}
                                </span>
                              </>
                            ) : (
                              <strong className="vless-urltest-result-no-delay">Нет измерений</strong>
                            )}
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </>
              )}
              <p className="vless-inline-hint vless-urltest-results-note">
                «Обновить» перечитывает последние значения, уже имеющиеся в sing-box, и не меняет маршрут или выбранный сервер. Ручные замеры обновляются кнопкой «Проверить задержки». В каждой карточке отображается только измерение с наиболее поздним временем.
              </p>
            </section>

            <section className="vless-selection-history">
              <button
                type="button"
                className="vless-selection-history-toggle"
                aria-expanded={selectionHistoryExpanded}
                aria-controls="vlessLocalSelectionHistoryContent"
                onClick={() => {
                  if (selectionHistoryExpanded) setVisibleSelectionHistoryCount(5)
                  setSelectionHistoryExpanded(!selectionHistoryExpanded)
                }}
              >
                <span className="vless-selection-history-heading">
                  <strong>История автоматического выбора</strong>
                  <span className="vless-inline-hint">
                    {selectionHistory?.monitor?.last_success_at
                      ? `Мониторинг · опрос каждые ${selectionHistory.monitor.interval_seconds} с`
                      : 'Журнал переключений'}
                  </span>
                </span>
                <span className="vless-history-toggle-label">{selectionHistoryExpanded ? 'Скрыть историю' : `Показать историю (${selectionHistory?.events.length ?? 0})`}</span>
              </button>
              {selectionHistoryExpanded && (
                <div id="vlessLocalSelectionHistoryContent" className="vless-selection-history-content">
              {selectionHistoryError && <p className="vless-selection-history-error">Не удалось загрузить журнал: {selectionHistoryError}</p>}
              {!selectionHistory && !selectionHistoryError && <p className="vless-inline-hint">Загрузка журнала переключений…</p>}
              {selectionHistory?.monitor?.last_error && <p className="vless-selection-history-error">Монитор: {selectionHistory.monitor.last_error}</p>}
              {selectionHistory?.current && (
                <div className="vless-selection-live-measurement">
                  <p className="vless-inline-hint">
                    Сейчас: <strong>{profileForOutbound(selectionHistory.current.active_outbound)?.name ?? selectionHistory.current.active_outbound ?? 'Не определён'}</strong>
                    {' · '}режим: {selectionHistory.current.selection_mode ?? '—'}
                    {' · '}допуск: {selectionHistory.current.urltest_tolerance_ms == null ? '—' : `${selectionHistory.current.urltest_tolerance_ms} мс`}
                  </p>
                  <p className={isMeasurementStale(selectionHistory.current.active_delay_observed_at, selectionHistory.current.urltest_interval, clockNow) ? 'vless-inline-hint vless-measurement-stale' : 'vless-inline-hint'}>
                    {formatUrltestMeasurement(selectionHistory.current, clockNow)}
                  </p>
                </div>
              )}
              {selectionHistory && selectionHistory.events.length === 0 && (
                <p className="vless-inline-hint">После запуска журнала переключения ещё не зафиксированы.</p>
              )}
              {(selectionHistory?.events ?? []).slice().reverse().slice(0, visibleSelectionHistoryCount).map((event) => {
                const profileName = (tag: string | null) => profileForOutbound(tag)?.name ?? tag ?? '—'
                return (
                  <article className="vless-selection-history-event" key={event.event_id}>
                    <div className="vless-selection-history-switch">
                      <strong>{profileName(event.previous_outbound)} → {profileName(event.active_outbound)}</strong>
                      <span>{formatTimestamp(event.observed_at)}</span>
                    </div>
                    <p>
                      Задержка: {event.previous_delay_ms == null ? 'нет измерения' : `${event.previous_delay_ms} мс`}
                      {' → '}{event.active_delay_ms == null ? 'нет измерения' : `${event.active_delay_ms} мс`}
                      {' · '}допуск {event.urltest_tolerance_ms == null ? '—' : `${event.urltest_tolerance_ms} мс`}
                    </p>
                    <p>
                      Время измерения задержки: предыдущий сервер — {event.previous_delay_observed_at ? formatTimestamp(event.previous_delay_observed_at) : 'время неизвестно'}
                      {' · '}новый сервер — {event.active_delay_observed_at ? formatTimestamp(event.active_delay_observed_at) : 'время неизвестно'}
                    </p>
                    <p>
                      Возраст при обнаружении: предыдущий — {event.previous_delay_age_seconds == null ? 'неизвестен' : formatDuration(event.previous_delay_age_seconds)}
                      {' · '}новый — {event.active_delay_age_seconds == null ? 'неизвестен' : formatDuration(event.active_delay_age_seconds)}
                      {' · '}{selectionFreshnessLabel(event.measurement_freshness)}
                    </p>
                    <p><strong>{event.diagnostic_origin === 'retrospective' ? 'Ретроспективная оценка' : 'Диагностика'} — {selectionDiagnosticLabel(event.diagnostic_status)}</strong>: {event.diagnostic_details || event.reason_details}</p>
                  </article>
                )
              })}
              {(selectionHistory?.events.length ?? 0) > 5 && (
                <div className="vless-selection-history-pagination">
                  <p className="vless-inline-hint">
                    Показано {Math.min(visibleSelectionHistoryCount, selectionHistory?.events.length ?? 0)} из {selectionHistory?.events.length ?? 0} событий
                  </p>
                  {visibleSelectionHistoryCount < (selectionHistory?.events.length ?? 0) && (
                    <button
                      type="button"
                      className="button button-secondary"
                      onClick={() => setVisibleSelectionHistoryCount((count) => Math.min(count + 5, selectionHistory?.events.length ?? 0))}
                    >
                      Показать ещё {Math.min(5, (selectionHistory?.events.length ?? 0) - visibleSelectionHistoryCount)}
                    </button>
                  )}
                </div>
              )}
                </div>
              )}
            </section>
            <div className="vless-profiles-list-controls">
              <button
                type="button"
                className="button button-secondary"
                aria-expanded={showAllProfiles}
                onClick={() => setShowAllProfiles((visible) => !visible)}
              >
                {showAllProfiles ? 'Скрыть список серверов' : `Показать все серверы (${profiles.length})`}
              </button>
              <span className="vless-inline-hint">Включено: {enabledCount} из {profiles.length}</span>
            </div>

            {showAllProfiles && (
              <>
                <div className="vless-profile-list-tools">
                  <input
                    type="search"
                    value={profileSearch}
                    onChange={(event) => setProfileSearch(event.target.value)}
                    placeholder="Поиск по названию, адресу или SNI"
                    aria-label="Поиск VLESS-сервера"
                    className="vless-profile-search"
                  />
                  <select
                    value={profileFilter}
                    onChange={(event) => setProfileFilter(event.target.value as ProfileFilter)}
                    aria-label="Фильтр доступности VLESS-серверов"
                    className="vless-profile-filter"
                  >
                    <option value="all">Все серверы</option>
                    <option value="available">Доступные по последней проверке</option>
                    <option value="no-response">Нет ответа по последней проверке</option>
                  </select>
                  <span className="vless-inline-hint">Показано {visibleProfiles.length} из {profiles.length}. С измеренной задержкой — сначала самые быстрые.</span>
                  <span className="vless-inline-hint">История ниже относится только к проверкам backend localhost:8080 и не объединяется с проверками BRUME 3. «Первый отказ» — время первой неудачной проверки этого контура, а не точное время начала сбоя.</span>
                </div>
                {visibleProfiles.length === 0 ? (
                  <p className="vless-inline-hint">Нет серверов, соответствующих поиску или выбранному фильтру.</p>
                ) : (
                  <div className="vless-profiles-list">
                    {visibleProfiles.map((profile) => {
                      const selected = selectedProfileId === profile.id && !automaticSelection
                      const active = activeProfileId === profile.id
                      const unavailable = Boolean(delayResults[profile.id]?.first_failed_at)
                      const profileTag = outboundTagForLocalProfile(profile.id)
                      const urltestSample = profileTag
                        ? selectionHistory?.current?.profile_delays?.[profileTag]
                        : undefined
                      const manualSample = delayResults[profile.id]
                      const latestSource = getLatestMeasurementSource(manualSample, urltestSample)
                      const measurementInterval = selectionHistory?.current?.urltest_interval ?? settings.urltest_interval

                      return (
                        <div className={unavailable ? "vless-saved-profile vless-saved-profile-unavailable" : "vless-saved-profile"} key={profile.id}>
                          <div>
                            <span className="vless-section-label">
                              {profile.enabled ? 'ВКЛЮЧЁН' : 'ОТКЛЮЧЁН'} · #{profile.id}
                            </span>
                            <strong><ServerCountryLabel source={profile} /></strong>
                            <span className="vless-profile-address">
                              {profile.address}:{profile.port}
                            </span>
                          </div>
                          <div className="vless-profile-metadata">
                            <span>
                              {profile.security.toUpperCase()}{profile.flow ? ` · ${profile.flow}` : ''}
                            </span>
                            {profile.server_name && <span>SNI: {profile.server_name}</span>}
                            {latestSource === 'urltest' ? (
                              <>
                                <span
                                  className={urltestSample?.delay_ms == null ? 'vless-urltest-result-no-delay' : undefined}
                                  title={formatUrltestProfileMeasurement(urltestSample, measurementInterval, clockNow)}
                                >
                                  URLTest · sing-box: {urltestSample?.delay_ms == null ? 'Нет измерения' : `${urltestSample.delay_ms} мс`}
                                </span>
                                <span className={isMeasurementStale(urltestSample?.observed_at, measurementInterval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                                  {formatUrltestProfileMeasurement(urltestSample, measurementInterval, clockNow)}
                                </span>
                              </>
                            ) : latestSource === 'manual' ? (
                              <>
                                <span className={unavailable ? "vless-delay-unavailable" : undefined} title={formatDelayDetails(manualSample)}>
                                  Ручная проверка: {formatDelay(manualSample, clockNow)}
                                </span>
                                <span className={isMeasurementStale(manualSample?.last_checked_at, measurementInterval, clockNow) ? 'vless-measurement-age vless-measurement-stale' : 'vless-measurement-age'}>
                                  {formatManualMeasurementAge(manualSample, measurementInterval, clockNow)}
                                </span>
                              </>
                            ) : (
                              <span className="vless-urltest-result-no-delay">Нет измерения в снимке API sing-box</span>
                            )}
                            {delayResults[profile.id]?.first_failed_at && <span className="vless-inline-hint vless-outage-hint">Первый отказ localhost: {formatTimestamp(delayResults[profile.id].first_failed_at)} · неудачных проверок localhost подряд: {delayResults[profile.id].consecutive_failures}</span>}
                            {!delayResults[profile.id]?.first_failed_at && delayResults[profile.id]?.last_recovered_at && <span className="vless-inline-hint">Последнее восстановление: {formatTimestamp(delayResults[profile.id].last_recovered_at)}; простой: {formatDuration(delayResults[profile.id].last_outage_duration_seconds ?? 0)}</span>}
                            {active && <span className="vless-validation-ok">Сейчас используется</span>}
                            {selected && <span className="vless-validation-ok">Закреплён вручную</span>}
                            {runtime?.running && profile.enabled && (
                              <button
                                type="button"
                                className="button button-secondary"
                                onClick={() => void handleSelect(profile.id)}
                                disabled={busy || selected}
                              >
                                Выбрать
                              </button>
                            )}
                            <button
                              type="button"
                              className="button button-secondary"
                              onClick={() => void handleToggle(profile)}
                              disabled={busy || (profile.enabled && enabledCount <= 1)}
                            >
                              {profile.enabled ? 'Отключить' : 'Включить'}
                            </button>
                            <button
                              type="button"
                              className="button button-secondary"
                              onClick={() => void handleDelete(profile)}
                              disabled={busy || (profile.enabled && enabledCount <= 1)}
                            >
                              Удалить
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      <div className="vless-import-form">
        <h3>Добавить серверы</h3>
        <p>Можно вставить до 50 ссылок VLESS — по одной ссылке на строку. Ошибочные и повторные ссылки будут отмечены отдельно; корректные серверы сохранятся. Все ссылки обрабатываются локальным backend MaxVPN.</p>
        <label className="vless-field">
          <span>Название одиночного профиля (необязательно)</span>
          <input type="text" value={profileName} maxLength={100} placeholder="По названию из ссылки" onChange={(event) => setProfileName(event.target.value)} disabled={busy} />
        </label>
        <label className="vless-field">
          <span>VLESS-ссылки или JSON-конфигурация</span>
          <textarea rows={8} maxLength={200_000} value={source} onChange={(event) => { setSource(event.target.value); setValidation(null); setBatchResult(null); setError(null); setMessage(null) }} placeholder={'vless://…\nvless://…\nvless://…'} spellCheck={false} autoCapitalize="off" autoComplete="off" disabled={busy} />
          <small>Пакетный импорт поддерживает ссылки vless://, разделённые переводом строки. JSON-конфигурацию можно импортировать отдельно.</small>
        </label>
        {validation && <div className={`vless-validation ${validation.valid ? 'vless-validation-ok' : 'vless-validation-bad'}`}><strong>{validation.valid ? 'Профиль корректен' : 'Профиль не прошёл проверку'}</strong>{validation.valid && validation.address && validation.port && <span>{validation.address}:{validation.port} · {validation.security ?? 'security не указан'}</span>}{validation.valid && validation.server_name && <span>SNI: {validation.server_name}</span>}{!validation.valid && validation.reason && <span>{validation.reason}</span>}</div>}
        <div className="vless-button-row">
          <button type="button" className="button button-secondary" onClick={() => void handleValidate()} disabled={busy || !source.trim()}>Проверить профиль</button>
          <button type="button" className="button button-primary" onClick={() => void handleImport()} disabled={busy || !source.trim() || profiles.length >= 50}>{busy ? 'Импорт…' : 'Импортировать'}</button>
        </div>
        {batchResult && <div className="vless-batch-results"><strong>Результат пакетного импорта</strong><p>Добавлено: {batchResult.imported}; ошибок: {batchResult.failed}; дубликатов: {batchResult.duplicates}; не помещается в лимит: {batchResult.limit_reached}.</p>{batchResult.items.map((item) => <div key={item.index}><span>#{item.index} — {item.status === 'imported' ? `добавлен: ${item.profile?.name ?? ''}` : item.status === 'duplicate' ? 'дубликат' : item.status === 'limit_reached' ? 'лимит 50' : 'ошибка'}</span>{item.reason && <small> — {item.reason}</small>}</div>)}</div>}
      </div>

      <div className="vless-runtime-controls">
        <h3>Управление sing-box</h3>
        <p>Автовыбор применяется в новой конфигурации после запуска sing-box. Подготовка не запускает процесс и не меняет маршруты LAN.</p>
        <div className="vless-button-row">
          <button type="button" className="button button-secondary" onClick={() => void handleRuntimeAction('prepare')} disabled={actionBusy || busy || enabledCount === 0 || Boolean(runtime?.running)}>{runtimeAction === 'prepare' ? 'Подготовка…' : 'Подготовить на роутере'}</button>
          <button type="button" className="button button-primary" onClick={() => void handleRuntimeAction('start')} disabled={actionBusy || busy || enabledCount === 0 || Boolean(runtime?.running)}>{runtimeAction === 'start' ? 'Запуск…' : 'Запустить sing-box'}</button>
          <button type="button" className="button button-secondary" onClick={() => void handleRuntimeAction('stop')} disabled={actionBusy || busy || (!runtime?.running && !runtime?.installed)}>{runtimeAction === 'stop' ? 'Остановка…' : 'Остановить sing-box'}</button>
        </div>
        {runtime?.running && <p className="vless-inline-hint">Чтобы применить изменение списка серверов, остановите sing-box и запустите снова. Если LAN-маршрутизация была включена, проверьте её состояние после запуска.</p>}
      </div>
    </section>
  )
}
