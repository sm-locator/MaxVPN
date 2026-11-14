import type { VlessSelectionHistoryResponse } from '../types/api'
import type { VlessApplianceSyncStatus } from '../types/api'
import type {
  CurrentUser,
  MaxVPNStatus,
  OpenWrtTrafficRoutingResult,
  VpnProfile,
  VpnProfileConfig,
  VpnProfileConfigUpdate,
  VpnProfileApplyResult,
  VpnProfileValidation,
  AuthTokenResponse,
  BootstrapStatusResponse,
  VpnRuntime,
  VpnRuntimeModeResponse,
  VpnTrafficMode,
  SmartRoutingRule,
  SmartRoutingRuleCreate,
  SmartRoutingRuleUpdate,
  SmartRoutingDomainDiagnosticResult,
  TokenResponse,
  RussianDirectPresetResponse,
  SmartRoutingImportPreviewResponse,
  SmartRoutingImportResponse,
  RussianDirectPresetDomainsResponse,
  DependencyDiagnosticResult,
  DependencyDiagnosticStartRequest,
  DependencyDiagnosticCommitResponse,
  DependencyGroup,
  SmartRoutingRuleTestResponse,
  VlessProfile,
  VlessProfileBatchImportResponse,
  VlessProfileDelayResponse,
  VlessProfileValidation,
  VlessRuntime,
  VlessRuntimeSettings,
} from '../types/api'

import type {
  SmartRoutingSyncPreview,
  SmartRoutingSyncPullResponse,
  SmartRoutingSyncPushResponse,
  SmartRoutingSyncEnabledResponse,
} from '../types/api'

const API_BASE = '/api/v1'
const TOKEN_KEY = 'maxvpn_access_token'
export const SESSION_EXPIRED_EVENT = 'maxvpn:session-expired'

class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    const normalizedDetail = detail.trim().toLowerCase()
    const localizedDetail =
      normalizedDetail === 'invalid authentication credentials' ||
      normalizedDetail === 'invalid email or password'
        ? 'Неверный email или пароль.'
        : detail

    super(localizedDetail)
    this.name = 'ApiError'
    this.status = status
    this.detail = localizedDetail
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY)

  const headers = new Headers(options.headers)

  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`

    try {
      const data = (await response.json()) as { detail?: unknown }

      if (typeof data.detail === 'string') {
        detail = data.detail
      } else if (Array.isArray(data.detail)) {
        const messages = data.detail
          .map((item) => {
            if (
              typeof item === 'object' &&
              item !== null &&
              'msg' in item &&
              typeof item.msg === 'string'
            ) {
              return item.msg
            }

            return null
          })
          .filter((message): message is string => message !== null)

        if (messages.length > 0) {
          detail = messages.join('. ')
        }
      }
    } catch {
      // Keep default HTTP error text.
    }

    if (
      response.status === 401 && token &&
      localStorage.getItem(TOKEN_KEY) === token
    ) {
      logout()
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
      detail = 'Сессия завершена. Войдите снова.'
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export async function getBootstrapStatus(): Promise<BootstrapStatusResponse> {
  return request<BootstrapStatusResponse>('/auth/bootstrap/status')
}

export async function bootstrapAdmin(
  email: string,
  password: string,
): Promise<AuthTokenResponse> {
  return request<AuthTokenResponse>('/auth/bootstrap', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
    }),
  })
}

export async function updateMyCredentials(
  email: string,
  password: string,
): Promise<AuthTokenResponse> {
  return request<AuthTokenResponse>('/auth/me/credentials', {
    method: 'PUT',
    body: JSON.stringify({
      email,
      password,
    }),
  })
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const body = new URLSearchParams()

  body.set('username', email)
  body.set('password', password)

  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  })

  if (!response.ok) {
    let detail = 'Не удалось войти'

    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) {
        detail = data.detail
      }
    } catch {
      // Keep default message.
    }

    throw new ApiError(response.status, detail)
  }

  const token = (await response.json()) as TokenResponse
  localStorage.setItem(TOKEN_KEY, token.access_token)

  return token
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY)
}

export function hasToken(): boolean {
  return Boolean(localStorage.getItem(TOKEN_KEY))
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>('/auth/me')
}

export async function getStatus(): Promise<MaxVPNStatus> {
  return request<MaxVPNStatus>('/status')
}

export async function getVpnRuntime(): Promise<VpnRuntime> {
  return request<VpnRuntime>('/vpn/runtime')
}

export async function getVpnTrafficMode(): Promise<VpnRuntimeModeResponse> {
  return request<VpnRuntimeModeResponse>('/vpn/mode')
}

export async function setVpnTrafficMode(
  mode: VpnTrafficMode,
): Promise<VpnRuntimeModeResponse> {
  return request<VpnRuntimeModeResponse>('/vpn/mode', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

export async function startVpn(): Promise<VpnRuntime> {
  return request<VpnRuntime>('/vpn/start', {
    method: 'POST',
  })
}

export async function stopVpn(): Promise<VpnRuntime> {
  return request<VpnRuntime>('/vpn/stop', {
    method: 'POST',
  })
}

export async function getVpnProfile(): Promise<VpnProfile | null> {
  return request<VpnProfile | null>('/vpn/profile')
}

export async function getVpnProfileConfig(): Promise<VpnProfileConfig | null> {
  return request<VpnProfileConfig | null>('/vpn/profile/config')
}

export async function updateVpnProfileConfig(
  config: VpnProfileConfigUpdate,
): Promise<VpnProfile> {
  return request<VpnProfile>('/vpn/profile/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function validateVpnProfileConfig(
  config: VpnProfileConfigUpdate,
): Promise<VpnProfileValidation> {
  return request<VpnProfileValidation>('/vpn/profile/config/validate', {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

export async function saveVpnProfile(
  profile: {
    name: string
    enabled: boolean
    provider_config: string
  },
): Promise<VpnProfile> {
  return request<VpnProfile>('/vpn/profile', {
    method: 'POST',
    body: JSON.stringify(profile),
  })
}

export async function validateVpnProfile(
  provider_config: string,
): Promise<VpnProfileValidation> {
  return request<VpnProfileValidation>('/vpn/profile/validate', {
    method: 'POST',
    body: JSON.stringify({ provider_config }),
  })
}

export async function applyVpnProfile(): Promise<VpnProfileApplyResult> {
  return request<VpnProfileApplyResult>('/vpn/profile/apply', {
    method: 'POST',
  })
}

export async function importCurrentVpnRuntime(): Promise<void> {
  await request('/vpn/profile/import-current-runtime', {
    method: 'POST',
  })
}


export async function getVlessProfile(): Promise<VlessProfile | null> {
  return request<VlessProfile | null>('/vless/profile')
}

export async function validateVlessProfile(
  source: string,
): Promise<VlessProfileValidation> {
  return request<VlessProfileValidation>('/vless/profile/validate', {
    method: 'POST',
    body: JSON.stringify({ source }),
  })
}

export async function importVlessProfile(
  source: string,
  name: string,
): Promise<VlessProfile> {
  return request<VlessProfile>('/vless/profile/import', {
    method: 'POST',
    body: JSON.stringify({ source, name, enabled: true }),
  })
}

export async function getVlessProfiles(): Promise<VlessProfile[]> {
  return request<VlessProfile[]>('/vless/profiles')
}

export interface VlessProfileExportBundle {
  format: 'maxvpn-vless-profiles'
  version: number
  profiles: Array<{ id: number; name: string; enabled: boolean; source: string }>
  settings: VlessRuntimeSettings
  warning: string
}

export async function exportVlessProfilesForAppliance(): Promise<VlessProfileExportBundle> {
  return request<VlessProfileExportBundle>('/vless/profiles/export')
}

export async function importVlessProfiles(
  sources: string[],
): Promise<VlessProfileBatchImportResponse> {
  return request<VlessProfileBatchImportResponse>('/vless/profiles/import-batch', {
    method: 'POST',
    body: JSON.stringify({ sources }),
  })
}

export async function setVlessProfileEnabled(
  id: number,
  enabled: boolean,
): Promise<VlessProfile> {
  return request<VlessProfile>(`/vless/profiles/${id}/enabled`, {
    method: 'PATCH',
    body: JSON.stringify({ enabled }),
  })
}

export async function deleteVlessProfile(id: number): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/vless/profiles/${id}`, { method: 'DELETE' })
}

export async function getVlessProfileDelayHistory(): Promise<VlessProfileDelayResponse> {
  return request<VlessProfileDelayResponse>('/vless/profiles/delays/history')
}

export async function getVlessSelectionHistory(): Promise<VlessSelectionHistoryResponse> {
  return request<VlessSelectionHistoryResponse>('/vless/runtime/selection-history')
}

export async function getVlessApplianceSyncStatus(): Promise<VlessApplianceSyncStatus> {
  return request<VlessApplianceSyncStatus>('/vless/appliance-sync/status')
}

export async function setVlessApplianceKillSwitch(
  enabled: boolean,
): Promise<{ kill_switch_enabled: boolean; wan_fallback_active: boolean }> {
  return request<{ kill_switch_enabled: boolean; wan_fallback_active: boolean }>(
    '/vless/appliance/kill-switch',
    {
      method: 'PUT',
      body: JSON.stringify({ enabled }),
    },
  )
}

export async function synchronizeVlessFromAppliance(confirmDeleteLocalOnly = false): Promise<VlessApplianceSyncStatus> {
  return request<VlessApplianceSyncStatus>('/vless/appliance-sync', {
    method: 'POST',
    body: JSON.stringify({ confirm_delete_local_only: confirmDeleteLocalOnly }),
  })
}

export async function testVlessProfileDelays(): Promise<VlessProfileDelayResponse> {
  return request<VlessProfileDelayResponse>('/vless/profiles/delays')
}

export async function selectVlessOutbound(profileId: number | null): Promise<VlessRuntime> {
  return request<VlessRuntime>('/vless/runtime/select', {
    method: 'POST',
    body: JSON.stringify({ profile_id: profileId }),
  })
}

export async function getVlessRuntimeSettings(): Promise<VlessRuntimeSettings> {
  return request<VlessRuntimeSettings>('/vless/runtime/settings')
}

export async function updateVlessRuntimeSettings(
  settings: VlessRuntimeSettings,
): Promise<VlessRuntimeSettings> {
  return request<VlessRuntimeSettings>('/vless/runtime/settings', {
    method: 'PUT',
    body: JSON.stringify(settings),
  })
}

export async function getVlessRuntime(): Promise<VlessRuntime> {
  return request<VlessRuntime>('/vless/runtime')
}

export async function prepareVlessRuntime(): Promise<VlessRuntime> {
  return request<VlessRuntime>('/vless/runtime/prepare', { method: 'POST' })
}

export async function startVlessRuntime(): Promise<VlessRuntime> {
  return request<VlessRuntime>('/vless/runtime/start', { method: 'POST' })
}

export async function stopVlessRuntime(): Promise<VlessRuntime> {
  return request<VlessRuntime>('/vless/runtime/stop', { method: 'POST' })
}

export async function getRules(): Promise<SmartRoutingRule[]> {
  return request<SmartRoutingRule[]>('/smart-routing/rules')
}

export async function getSmartRoutingDomainDiagnostic(
  domain: string,
): Promise<SmartRoutingDomainDiagnosticResult> {
  const query = new URLSearchParams({ domain })

  return request<SmartRoutingDomainDiagnosticResult>(
    '/smart-routing/domain-diagnostic?' + query.toString(),
  )
}

export async function testRule(
  id: number,
): Promise<SmartRoutingRuleTestResponse> {
  return request<SmartRoutingRuleTestResponse>(
    `/smart-routing/rules/${id}/test`,
    {
      method: 'POST',
    },
  )
}

export async function createRule(
  rule: SmartRoutingRuleCreate,
): Promise<SmartRoutingRule> {
  return request<SmartRoutingRule>('/smart-routing/rules', {
    method: 'POST',
    body: JSON.stringify(rule),
  })
}

export async function updateRule(
  id: number,
  rule: SmartRoutingRuleUpdate,
): Promise<SmartRoutingRule> {
  return request<SmartRoutingRule>(`/smart-routing/rules/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(rule),
  })
}

export async function deleteRule(id: number): Promise<void> {
  await request<void>(`/smart-routing/rules/${id}`, {
    method: 'DELETE',
  })
}

export async function addRussianDirectPreset(): Promise<RussianDirectPresetResponse> {
  return request<RussianDirectPresetResponse>(
    '/smart-routing/presets/russia-direct',
    {
      method: 'POST',
    },
  )
}

export async function applySmartRouting(expectedRemoteFingerprint?: string): Promise<OpenWrtTrafficRoutingResult> {
  return request<OpenWrtTrafficRoutingResult>('/smart-routing/apply', {
    method: 'POST',
    body: JSON.stringify({ expected_remote_fingerprint: expectedRemoteFingerprint }),
  })
}

export async function startDependencyDiagnostic(
  data: DependencyDiagnosticStartRequest,
): Promise<DependencyDiagnosticResult> {
  return request<DependencyDiagnosticResult>('/smart-routing/dependency-diagnostic/start', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function pollDependencyDiagnostic(
  token: string,
): Promise<DependencyDiagnosticResult> {
  return request<DependencyDiagnosticResult>(`/smart-routing/dependency-diagnostic/${token}`)
}

export async function commitDependencyDiagnosticRules(
  token: string,
  hostnames: string[],
  title?: string,
): Promise<DependencyDiagnosticCommitResponse> {
  return request<DependencyDiagnosticCommitResponse>(
    `/smart-routing/dependency-diagnostic/${token}/rules`,
    {
      method: 'POST',
      body: JSON.stringify({ hostnames, title }),
    },
  )
}

export async function getDependencyGroups(): Promise<DependencyGroup[]> {
  return request<DependencyGroup[]>('/smart-routing/dependency-groups')
}

export { ApiError }


export async function previewSmartRoutingImport(
  file: File,
): Promise<SmartRoutingImportPreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)

  return request<SmartRoutingImportPreviewResponse>(
    '/smart-routing/import/preview',
    {
      method: 'POST',
      body: formData,
    },
  )
}

export async function importSmartRouting(
  file: File,
): Promise<SmartRoutingImportResponse> {
  const formData = new FormData()
  formData.append('file', file)

  return request<SmartRoutingImportResponse>(
    '/smart-routing/import',
    {
      method: 'POST',
      body: formData,
    },
  )
}


export async function getRussianDirectPresetDomains(): Promise<RussianDirectPresetDomainsResponse> {
  return request<RussianDirectPresetDomainsResponse>(
    '/smart-routing/presets/russia-direct',
  )
}

export async function getSmartRoutingSyncPreview(): Promise<SmartRoutingSyncPreview> {
  return request<SmartRoutingSyncPreview>(
    `/smart-routing/sync?t=${Date.now()}`,
  )
}


export async function syncSmartRoutingEnabledFromBrume(): Promise<SmartRoutingSyncEnabledResponse> {
  return request<SmartRoutingSyncEnabledResponse>(
    '/smart-routing/sync/enabled-from-brume',
    {
      method: 'POST',
    },
  )
}


export async function pullSmartRoutingFromBrume(
  expectedRemoteFingerprint?: string,
): Promise<SmartRoutingSyncPullResponse> {
  return request<SmartRoutingSyncPullResponse>(
    '/smart-routing/sync/pull',
    {
      method: 'POST',
      body: JSON.stringify({
        confirm: true,
        expected_remote_fingerprint:
          expectedRemoteFingerprint ?? null,
      }),
    },
  )
}

export async function pushSmartRoutingToBrume(
  expectedRemoteFingerprint?: string,
): Promise<SmartRoutingSyncPushResponse> {
  return request<SmartRoutingSyncPushResponse>(
    '/smart-routing/sync/push',
    {
      method: 'POST',
      body: JSON.stringify({
        confirm: true,
        expected_remote_fingerprint:
          expectedRemoteFingerprint ?? null,
      }),
    },
  )
}
