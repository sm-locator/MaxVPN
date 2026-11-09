import { useEffect, useState } from 'react'
import './App.css'
import {
  addRussianDirectPreset,
  createRule,
  deleteRule,
  getCurrentUser,
  getRules,
  getRussianDirectPresetDomains,
  getStatus,
  getVpnRuntime,
  getVlessRuntime,
  setVpnTrafficMode,
  startVpn,
  stopVpn,
  hasToken,
  login,
  logout,
  updateRule,
} from './api/client'
import { Dashboard } from './components/Dashboard'
import { AdminSettings } from './components/AdminSettings'
import { Login } from './components/Login'
import type {
  CurrentUser,
  MaxVPNStatus,
  RussianDirectPresetResponse,
  SmartRoutingRule,
  VpnRuntime,
  VlessRuntime,
  VpnTrafficMode,
} from './types/api'

function App() {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [rules, setRules] = useState<SmartRoutingRule[]>([])
  const [russianDirectDomains, setRussianDirectDomains] = useState<string[]>([])
  const [loading, setLoading] = useState(() => hasToken())
  const [loggingIn, setLoggingIn] = useState(false)
  const [sessionChecked, setSessionChecked] = useState(() => !hasToken())
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<MaxVPNStatus | null>(null)
  const [runtime, setRuntime] = useState<VpnRuntime | null>(null)
  const [vlessRuntime, setVlessRuntime] = useState<VlessRuntime | null>(null)
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [runtimeStarting, setRuntimeStarting] = useState(false)
  const [runtimeStopping, setRuntimeStopping] = useState(false)
  const [modeChanging, setModeChanging] = useState(false)
  const [modeError, setModeError] = useState<string | null>(null)
  const [adminSettingsOpen, setAdminSettingsOpen] = useState(false)

  async function refreshDashboard() {
    const [
      currentRules,
      currentStatus,
      currentRuntime,
      currentRussianDirectPreset,
      currentVlessRuntime,
    ] = await Promise.all([
      getRules(),
      getStatus(),
      getVpnRuntime(),
      getRussianDirectPresetDomains(),
      getVlessRuntime().catch(() => null),
    ])

    setRules(currentRules)
    setStatus(currentStatus)
    setRuntime(currentRuntime)
    setVlessRuntime(currentVlessRuntime)
    setRussianDirectDomains(currentRussianDirectPreset.domains)
    setRuntimeError(null)
  }

  useEffect(() => {
    if (!user) {
      return
    }

    let cancelled = false
    let refreshing = false

    const refresh = async () => {
      if (
        cancelled ||
        refreshing ||
        document.visibilityState !== 'visible'
      ) {
        return
      }

      refreshing = true

      try {
        await refreshDashboard()

        if (!cancelled) {
          setRuntimeError(null)
        }
      } catch (error) {
        if (!cancelled) {
          setRuntimeError(
            error instanceof Error
              ? error.message
              : 'Не удалось автоматически обновить состояние.',
          )
        }
      } finally {
        refreshing = false
      }
    }

    const interval = window.setInterval(() => {
      void refresh()
    }, 15000)

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void refresh()
      }
    }

    document.addEventListener(
      'visibilitychange',
      handleVisibilityChange,
    )

    void refresh()

    return () => {
      cancelled = true
      window.clearInterval(interval)
      document.removeEventListener(
        'visibilitychange',
        handleVisibilityChange,
      )
    }
  }, [user])

  useEffect(() => {
    if (!hasToken()) {
      return
    }

    let cancelled = false

    async function bootstrap() {
      try {
        const [
          currentUser,
          currentRules,
          currentStatus,
          currentRuntime,
          currentRussianDirectPreset,
          currentVlessRuntime,
        ] = await Promise.all([
          getCurrentUser(),
          getRules(),
          getStatus(),
          getVpnRuntime(),
          getRussianDirectPresetDomains(),
          getVlessRuntime().catch(() => null),
        ])

        if (cancelled) {
          return
        }

        setUser(currentUser)
        setRules(currentRules)
        setRussianDirectDomains(currentRussianDirectPreset.domains)
        setStatus(currentStatus)
        setRuntime(currentRuntime)
        setVlessRuntime(currentVlessRuntime)
        setRuntimeError(null)
        setError(null)
      } catch (error) {
        if (cancelled) {
          return
        }

        logout()
        setUser(null)
        setRules([])
        setError(
          error instanceof Error
            ? error.message
            : 'Не удалось восстановить сессию.',
        )
      } finally {
        if (!cancelled) {
          setLoading(false)
          setSessionChecked(true)
        }
      }
    }

    void bootstrap()

    return () => {
      cancelled = true
    }
  }, [])

  async function handleLogin(email: string, password: string) {
    setLoggingIn(true)
    setError(null)

    try {
      await login(email, password)

      const [
        currentUser,
        currentRules,
        currentStatus,
        currentRuntime,
        currentRussianDirectPreset,
        currentVlessRuntime,
      ] = await Promise.all([
        getCurrentUser(),
        getRules(),
        getStatus(),
        getVpnRuntime(),
        getRussianDirectPresetDomains(),
        getVlessRuntime().catch(() => null),
      ])

      setUser(currentUser)
      setRules(currentRules)
      setRussianDirectDomains(currentRussianDirectPreset.domains)
      setStatus(currentStatus)
      setRuntime(currentRuntime)
      setVlessRuntime(currentVlessRuntime)
      setRuntimeError(null)
      setSessionChecked(true)
    } catch (error) {
      const message = error instanceof Error ? error.message : ''
      const normalizedMessage = message.trim().toLowerCase()
      const isInvalidCredentials =
        normalizedMessage === 'invalid authentication credentials' ||
        normalizedMessage === 'invalid email or password'

      setError(
        isInvalidCredentials
          ? 'Неверный email или пароль.'
          : message || 'Не удалось войти.',
      )
    } finally {
      setLoggingIn(false)
      setLoading(false)
      setSessionChecked(true)
    }
  }

  async function handleRefresh() {
    setLoading(true)
    setError(null)

    try {
      await refreshDashboard()
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Не удалось обновить состояние Dashboard.',
      )
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(
    target: string,
    targetType: 'cidr' | 'domain',
  ) {
    setError(null)

    const created = await createRule({
      target_type: targetType,
      target,
      action: 'direct',
      priority: nextPriority(rules),
      address_family: targetType === 'domain' ? 'any' : 'ipv4',
      enabled: true,
    })

    setRules((current) => [...current, created].sort(sortRules))
  }

  async function handleToggle(rule: SmartRoutingRule) {
    setError(null)

    const updated = await updateRule(rule.id, {
      enabled: !rule.enabled,
    })

    setRules((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    )
  }

  async function handleDelete(id: number) {
    setError(null)
    await deleteRule(id)
    setRules((current) => current.filter((rule) => rule.id !== id))
  }

  async function handleAddRussianDirectPreset(): Promise<RussianDirectPresetResponse> {
    setError(null)

    try {
      const result = await addRussianDirectPreset()
      await refreshDashboard()
      return result
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Не удалось добавить российские сервисы.',
      )
      throw error
    }
  }

  async function handleModeChange(mode: VpnTrafficMode) {
    setModeChanging(true)
    setModeError(null)
    try {
      await setVpnTrafficMode(mode)
      setRuntime(await getVpnRuntime())
      setVlessRuntime(await getVlessRuntime().catch(() => null))
      setRuntimeError(null)
    } catch (error) {
      setModeError(
        error instanceof Error
          ? error.message
          : 'Не удалось переключить режим маршрутизации.',
      )
      try {
        setRuntime(await getVpnRuntime())
        setVlessRuntime(await getVlessRuntime().catch(() => null))
      } catch {
        // Preserve the last known dashboard status if refresh fails too.
      }
    } finally {
      setModeChanging(false)
    }
  }

  async function handleRuntimeStart() {
    setRuntimeStarting(true)
    setRuntimeError(null)

    try {
      const currentRuntime = await startVpn()
      setRuntime(currentRuntime)
      setRuntimeError(null)
    } catch (error) {
      setRuntimeError(
        error instanceof Error
          ? error.message
          : 'Не удалось запустить VPN.',
      )
    } finally {
      setRuntimeStarting(false)
    }
  }

  async function handleRuntimeStop() {
    setRuntimeStopping(true)
    setRuntimeError(null)

    try {
      const currentRuntime = await stopVpn()
      setRuntime(currentRuntime)
      setRuntimeError(null)
    } catch (error) {
      setRuntimeError(
        error instanceof Error
          ? error.message
          : 'Не удалось остановить VPN.',
      )
    } finally {
      setRuntimeStopping(false)
    }
  }

  function handleLogout() {
    logout()
    setUser(null)
    setRules([])
    setRussianDirectDomains([])
    setStatus(null)
    setRuntime(null)
    setVlessRuntime(null)
    setRuntimeError(null)
    setError(null)
    setSessionChecked(true)
  }

  function handleSessionExpired() {
    logout()
    setUser(null)
    setRules([])
    setRussianDirectDomains([])
    setStatus(null)
    setRuntime(null)
    setVlessRuntime(null)
    setRuntimeError(null)
    setError('Сессия завершена. Войдите снова.')
    setSessionChecked(true)
  }

  if (!sessionChecked) {
    return (
      <main className="auth-shell">
        <div className="auth-card loading-card">
          <div className="brand-mark">M</div>
          <div className="eyebrow">MAXVPN</div>
          <h1>Подключение...</h1>
          <p className="muted">
            Проверяем сохранённую сессию.
          </p>
        </div>
      </main>
    )
  }

  if (!user) {
    return (
      <Login
        loading={loggingIn || loading}
        error={error}
        onLogin={handleLogin}
      />
    )
  }

  return (
    <>
      {adminSettingsOpen && (
        <AdminSettings
          user={user}
          onUpdated={setUser}
          onClose={() => setAdminSettingsOpen(false)}
        />
      )}

      <Dashboard
        user={user}
        rules={rules}
        russianDirectDomains={russianDirectDomains}
        loading={loading}
        error={error}
        status={status}
        onLogout={handleLogout}
        onSessionExpired={handleSessionExpired}
        onAdminSettings={() => setAdminSettingsOpen(true)}
        onRefresh={handleRefresh}
        onCreate={handleCreate}
        onToggle={handleToggle}
        onDelete={handleDelete}
        onAddRussianDirectPreset={handleAddRussianDirectPreset}
        runtime={runtime}
        vlessRuntime={vlessRuntime}
        runtimeStarting={runtimeStarting}
        runtimeStopping={runtimeStopping}
        runtimeError={runtimeError}
        modeChanging={modeChanging}
        modeError={modeError}
        onModeChange={(mode) => void handleModeChange(mode)}
        onRuntimeStart={() => void handleRuntimeStart()}
        onRuntimeStop={() => void handleRuntimeStop()}
      />
    </>
  )
}

function sortRules(
  a: SmartRoutingRule,
  b: SmartRoutingRule,
): number {
  return a.priority - b.priority || a.id - b.id
}

function nextPriority(rules: SmartRoutingRule[]): number {
  if (rules.length === 0) {
    return 100
  }

  return Math.max(...rules.map((rule) => rule.priority)) + 100
}

export default App
