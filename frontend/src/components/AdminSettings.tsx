import { useState } from 'react'
import { updateMyCredentials } from '../api/client'
import type { CurrentUser } from '../types/api'

type AdminSettingsProps = {
  user: CurrentUser
  onUpdated: (user: CurrentUser) => void
  onClose: () => void
}

export function AdminSettings({
  user,
  onUpdated,
  onClose,
}: AdminSettingsProps) {
  const [email, setEmail] = useState(user.email)
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()
    setError(null)

    if (password.length < 8) {
      setError('Пароль должен содержать не менее 8 символов.')
      return
    }

    if (password !== password2) {
      setError('Пароли не совпадают.')
      return
    }

    if (!email.trim()) {
      setError('Введите email.')
      return
    }

    setSaving(true)

    try {
      const result = await updateMyCredentials(
        email.trim(),
        password,
      )

      localStorage.setItem(
        'maxvpn_access_token',
        result.access_token,
      )

      onUpdated({
        id: result.id,
        email: result.email,
      })

      setPassword('')
      setPassword2('')
      onClose()
    } catch (updateError) {
      setError(
        updateError instanceof Error
          ? updateError.message
          : 'Не удалось обновить учетные данные.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="admin-settings-overlay">
      <section className="admin-settings-card">
        <div className="admin-settings-header">
          <div>
            <div className="eyebrow">ADMIN</div>
            <h2>Учетная запись администратора</h2>
            <p className="muted">
              Изменение email или пароля администратора MaxVPN.
            </p>
          </div>

          <button
            type="button"
            className="button button-secondary"
            onClick={onClose}
            disabled={saving}
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>

        <form
          className="admin-settings-form"
          onSubmit={handleSubmit}
        >
          <label>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) =>
                setEmail(event.target.value)
              }
              disabled={saving}
              required
            />
          </label>

          <label>
            Новый пароль
            <input
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              disabled={saving}
              placeholder="Не менее 8 символов"
              required
            />
          </label>

          <label>
            Повторите пароль
            <input
              type="password"
              autoComplete="new-password"
              value={password2}
              onChange={(event) =>
                setPassword2(event.target.value)
              }
              disabled={saving}
              required
            />
          </label>

          {error && (
            <div className="alert alert-error">
              {error}
            </div>
          )}

          <div className="admin-settings-actions">
            <button
              type="button"
              className="button button-secondary"
              onClick={onClose}
              disabled={saving}
            >
              Отмена
            </button>

            <button
              type="submit"
              className="button button-primary"
              disabled={saving}
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}
