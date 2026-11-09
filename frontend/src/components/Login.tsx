import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { bootstrapAdmin, getBootstrapStatus } from '../api/client'

type LoginProps = {
  loading: boolean
  error: string | null
  onLogin: (email: string, password: string) => Promise<void>
}

export function Login({
  loading,
  error,
  onLogin,
}: LoginProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const [bootstrapMode, setBootstrapMode] = useState(false)
  const [bootstrapEmail, setBootstrapEmail] = useState('')
  const [bootstrapPassword, setBootstrapPassword] = useState('')
  const [bootstrapPassword2, setBootstrapPassword2] = useState('')
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [bootstrapAvailable, setBootstrapAvailable] = useState(false)

  useEffect(() => {
    let cancelled = false

    getBootstrapStatus()
      .then((result) => {
        if (!cancelled) {
          setBootstrapAvailable(result.available)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBootstrapAvailable(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  async function submit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()
    await onLogin(email, password)
  }

  async function submitBootstrap(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()
    setBootstrapError(null)

    if (bootstrapPassword !== bootstrapPassword2) {
      setBootstrapError('Пароли не совпадают.')
      return
    }

    setBootstrapLoading(true)

    try {
      const result = await bootstrapAdmin(
        bootstrapEmail,
        bootstrapPassword,
      )

      localStorage.setItem(
        'maxvpn_access_token',
        result.access_token,
      )

      window.location.reload()
    } catch (error) {
      setBootstrapError(
        error instanceof Error
          ? error.message
          : 'Не удалось создать администратора.',
      )
    } finally {
      setBootstrapLoading(false)
    }
  }

  return (
    <main className="auth-shell">
      <div className="auth-card">
        <div className="brand-mark">M</div>

        <div className="eyebrow">MAXVPN</div>

        {bootstrapMode ? (
          <>
            <h1>Создание администратора</h1>

            <p className="muted">
              Создайте администратора для первого запуска MaxVPN.
            </p>

            <form
              onSubmit={submitBootstrap}
              className="auth-form"
            >
              <label>
                Email администратора
                <input
                  type="email"
                  autoComplete="email"
                  value={bootstrapEmail}
                  onChange={(event) =>
                    setBootstrapEmail(event.target.value)
                  }
                  placeholder="admin@example.com"
                  required
                />
              </label>

              <label>
                Пароль
                <input
                  type="password"
                  autoComplete="new-password"
                  value={bootstrapPassword}
                  onChange={(event) =>
                    setBootstrapPassword(event.target.value)
                  }
                  placeholder="Введите пароль"
                  required
                />
              </label>

              <label>
                Повторите пароль
                <input
                  type="password"
                  autoComplete="new-password"
                  value={bootstrapPassword2}
                  onChange={(event) =>
                    setBootstrapPassword2(event.target.value)
                  }
                  placeholder="Повторите пароль"
                  required
                />
              </label>

              {bootstrapError && (
                <div className="alert alert-error">
                  {bootstrapError}
                </div>
              )}

              <button
                type="submit"
                className="button button-primary"
                disabled={bootstrapLoading}
              >
                {bootstrapLoading
                  ? 'Создание...'
                  : 'Создать администратора'}
              </button>

              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  setBootstrapMode(false)
                  setBootstrapError(null)
                }}
              >
                Вернуться ко входу
              </button>
            </form>
          </>
        ) : (
          <>
            <h1>Управление VPN</h1>

            <p className="muted">
              Войдите, чтобы управлять маршрутизацией вашего
              роутера.
            </p>

            <form
              onSubmit={submit}
              className="auth-form"
            >
              <label>
                Email
                <input
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  placeholder="you@example.com"
                  required
                />
              </label>

              <label>
                Пароль
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) =>
                    setPassword(event.target.value)
                  }
                  placeholder="••••••••"
                  required
                />
              </label>

              {error && (
                <div className="alert alert-error">
                  {error}
                </div>
              )}

              <button
                type="submit"
                className="button button-primary"
                disabled={loading}
              >
                {loading ? 'Вход...' : 'Войти'}
              </button>
            </form>

            {bootstrapAvailable && (
              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  setBootstrapMode(true)
                  setBootstrapError(null)
                }}
              >
                Первый запуск — создать администратора
              </button>
            )}
          </>
        )}
      </div>
    </main>
  )
}
