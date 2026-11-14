import { useEffect, useRef, useState } from 'react'
import {
  applyVpnProfile,
  getVpnProfile,
  saveVpnProfile,
  validateVpnProfile,
} from '../api/client'
import type { VpnProfileValidation } from '../types/api'

export function VpnProfileCard() {
  const inputRef = useRef<HTMLInputElement | null>(null)

  const [profileName, setProfileName] = useState('Current Brume VPN')
  const [enabled, setEnabled] = useState(true)
  const [profileExists, setProfileExists] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)

  const [fileName, setFileName] = useState<string | null>(null)
  const [fileText, setFileText] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)

  const [validation, setValidation] =
    useState<VpnProfileValidation | null>(null)

  const [profileSaved, setProfileSaved] = useState(false)

  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    getVpnProfile()
      .then((profile) => {
        if (cancelled || !profile) {
          return
        }

        setProfileExists(true)
        setProfileName(profile.name)
        setEnabled(profile.enabled)
      })
      .catch(() => {
        // Defaults remain usable for first import.
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  function resetResult() {
    setValidation(null)
    setError(null)
    setMessage(null)
  }

  async function readFile(file: File) {
    resetResult()
    setEditorOpen(true)

    if (!file.name.toLowerCase().endsWith('.conf')) {
      setError('Выберите файл конфигурации с расширением .conf.')
      return
    }

    if (file.size > 256 * 1024) {
      setError('Файл конфигурации слишком большой.')
      return
    }

    try {
      const text = await file.text()

      if (!text.trim()) {
        setError('Файл конфигурации пуст.')
        return
      }

      setFileName(file.name)
      setFileText(text)
      setProfileSaved(false)
    } catch {
      setFileName(null)
      setFileText(null)
      setError('Не удалось прочитать файл конфигурации.')
    }
  }

  function handleFileChange(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0]

    if (file) {
      void readFile(file)
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragActive(false)

    const file = event.dataTransfer.files[0]

    if (file) {
      void readFile(file)
    }
  }

  function openFileDialog() {
    inputRef.current?.click()
  }

  function toggleEditor() {
    setEditorOpen((value) => !value)
  }

  async function validateFile(): Promise<VpnProfileValidation | null> {
    if (!fileText) {
      setError('Сначала выберите файл конфигурации.')
      return null
    }

    const result = await validateVpnProfile(fileText)

    setValidation(result)

    if (!result.valid) {
      setMessage(null)
      setError(
        result.reason ?? 'Конфигурация не прошла проверку.',
      )
      return null
    }

    if (!result.has_private_key || !result.has_preshared_key) {
      setMessage(null)
      setError(
        'В конфигурации отсутствует PrivateKey или PresharedKey.',
      )
      return null
    }

    setError(null)

    return result
  }

  async function handleValidate() {
    setBusy(true)
    resetResult()

    try {
      await validateFile()
    } catch (validateError) {
      setValidation(null)
      setError(
        validateError instanceof Error
          ? validateError.message
          : 'Не удалось проверить конфигурацию.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleSave() {
    setBusy(true)
    resetResult()

    try {
      const result = await validateFile()

      if (!result || !fileText) {
        return
      }

      const saved = await saveVpnProfile({
        name: profileName.trim() || 'Current Brume VPN',
        enabled,
        provider_config: fileText,
      })

      setProfileExists(true)
      setProfileSaved(true)
      setMessage(
        `Профиль «${saved.name}» сохранён. Теперь его можно применить.`,
      )

      setFileText(null)
      setFileName(null)

      if (inputRef.current) {
        inputRef.current.value = ''
      }

      setEditorOpen(false)
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : 'Не удалось сохранить профиль.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleApplySaved() {
    setBusy(true)
    setError(null)
    setMessage(null)

    try {
      const result = await applyVpnProfile()

      if (result.no_change) {
        setMessage(
          'Активная конфигурация уже соответствует сохранённому профилю.',
        )
      } else if (result.verified) {
        setMessage(
          'Сохранённый профиль успешно применён и проверен.',
        )
      } else {
        setError(
          result.reason ?? 'Применение не прошло проверку.',
        )
      }
    } catch (applyError) {
      setError(
        applyError instanceof Error
          ? applyError.message
          : 'Не удалось применить сохранённый профиль.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function handleSaveAndApply() {
    setBusy(true)
    resetResult()

    try {
      const result = await validateFile()

      if (!result || !fileText) {
        return
      }

      const saved = await saveVpnProfile({
        name: profileName.trim() || 'Current Brume VPN',
        enabled,
        provider_config: fileText,
      })

      setProfileExists(true)

      if (!saved.enabled) {
        setError(
          'Профиль сохранён, но отключён. Включите профиль перед применением.',
        )
        return
      }

      const applyResult = await applyVpnProfile()

      if (applyResult.no_change) {
        setMessage(
          `Профиль «${saved.name}» сохранён. Активная конфигурация уже совпадает с ним.`,
        )
      } else if (applyResult.verified) {
        setMessage(
          `Профиль «${saved.name}» успешно сохранён, применён и проверен.`,
        )
      } else {
        setError(
          applyResult.reason ??
            'Профиль сохранён, но применение не прошло проверку.',
        )
      }

      setFileText(null)
      setFileName(null)
      setProfileSaved(true)

      if (inputRef.current) {
        inputRef.current.value = ''
      }

      setEditorOpen(false)
    } catch (applyError) {
      setError(
        applyError instanceof Error
          ? applyError.message
          : 'Не удалось сохранить и применить профиль.',
      )
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <section className="vpn-profile-card">
        <div className="eyebrow">VPN-ПРОФИЛЬ</div>
        <h2>Загрузка профиля...</h2>
      </section>
    )
  }

  return (
    <section className="vpn-profile-card">
      <div className="vpn-profile-summary">
        <div className="vpn-profile-summary-main">
          <div className="eyebrow">ПРОФИЛЬ VPN · AMNEZIAWG</div>

          <div className="vpn-profile-title-row">
            <h2>{profileName}</h2>

            <div
              className={`vpn-profile-status ${
                profileExists && enabled
                  ? 'is-enabled'
                  : 'is-disabled'
              }`}
            >
              <span className="vpn-profile-status-dot" />
              {profileExists
                ? enabled
                  ? 'Сохранён'
                  : 'Отключён'
                : 'Не настроен'}
            </div>
          </div>

          <p className="muted">
            {profileExists
              ? enabled
                ? 'Профиль сохранён и доступен для применения.'
                : 'Профиль сохранён, но отключён.'
              : 'Загрузите конфигурацию AmneziaWG для настройки VPN.'}
          </p>
        </div>

        <div className="vpn-profile-summary-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={toggleEditor}
          >
            {editorOpen ? 'Скрыть настройки' : 'Изменить профиль'}
          </button>

          {profileExists && enabled && (
            <button
              type="button"
              className="button button-primary"
              onClick={() => void handleApplySaved()}
              disabled={busy}
            >
              {busy ? 'Применение...' : 'Применить профиль'}
            </button>
          )}
        </div>
      </div>

      {message && (
        <div className="alert alert-success">{message}</div>
      )}

      {error && !editorOpen && (
        <div className="alert alert-error">{error}</div>
      )}

      {editorOpen && (
        <div className="vpn-profile-editor">
          <div className="vpn-profile-section">
            <div className="vpn-profile-section-title">
              Импорт конфигурации
            </div>

            <div
              className={`vpn-import-dropzone${
                dragActive ? ' is-dragging' : ''
              }${fileName ? ' has-file' : ''}`}
              onDragOver={(event) => {
                event.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={openFileDialog}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  openFileDialog()
                }
              }}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".conf"
                onChange={handleFileChange}
                hidden
              />

              {fileName ? (
                <>
                  <div className="vpn-import-icon success">✓</div>
                  <strong>{fileName}</strong>
                  <span>
                    Файл загружен. Нажмите «Проверить», чтобы проверить
                    конфигурацию.
                  </span>
                </>
              ) : (
                <>
                  <div className="vpn-import-icon">↑</div>
                  <strong>Перетащите файл .conf сюда</strong>
                  <span>или нажмите, чтобы выбрать файл</span>
                </>
              )}
            </div>
          </div>

          <div className="vpn-profile-import-fields">
            <label>
              Имя профиля
              <input
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
                maxLength={100}
              />
            </label>

            <label className="vpn-profile-toggle">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              <span>Профиль включён</span>
            </label>
          </div>

          <div className="vpn-import-security">
            <span>Секретные ключи</span>
            <strong>
              {validation?.has_private_key &&
              validation.has_preshared_key
                ? '✓ Найдены'
                : 'Будут обработаны автоматически'}
            </strong>
          </div>

          {validation?.valid && (
            <div className="vpn-import-summary">
              <div>
                <span>VPN адрес</span>
                <strong>{validation.interface_address}</strong>
              </div>

              <div>
                <span>Endpoint</span>
                <strong>{validation.endpoint}</strong>
              </div>

              <div>
                <span>AllowedIPs</span>
                <strong>{validation.allowed_ips.join(', ')}</strong>
              </div>

              <div>
                <span>PrivateKey</span>
                <strong>✓ Найден</strong>
              </div>

              <div>
                <span>PresharedKey</span>
                <strong>✓ Найден</strong>
              </div>
            </div>
          )}

          {error && (
            <div className="alert alert-error">{error}</div>
          )}

          <div className="vpn-profile-actions">
            <button
              type="button"
              className="button button-secondary"
              onClick={() => void handleValidate()}
              disabled={busy || !fileText}
            >
              {busy ? 'Проверка...' : 'Проверить'}
            </button>

            <button
              type="button"
              className="button button-secondary"
              onClick={() => void handleSave()}
              disabled={busy || !fileText}
            >
              {busy ? 'Сохранение...' : 'Сохранить'}
            </button>

            <button
              type="button"
              className="button button-primary"
              onClick={() =>
                profileSaved
                  ? void handleApplySaved()
                  : void handleSaveAndApply()
              }
              disabled={busy || (!fileText && !profileSaved) || !enabled}
            >
              {busy
                ? 'Выполнение...'
                : profileSaved
                  ? 'Применить сохранённый профиль'
                  : 'Сохранить и применить'}
            </button>
          </div>

          <div className="vpn-profile-footer">
            Конфигурация проверяется сервером перед сохранением.
            Секретные ключи не отображаются в интерфейсе.
          </div>
        </div>
      )}
    </section>
  )
}
