import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  getSmartRoutingDomainDiagnostic,
  setVlessApplianceKillSwitch,
} from './client'

const fetchMock = vi.fn()

describe('getSmartRoutingDomainDiagnostic', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => 'test-access-token'),
    })
  })

  afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it('uses the authenticated diagnostic endpoint and URL-encodes the domain', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        domain: 'cian.ru',
        dns_ipv4_addresses: ['51.250.123.126'],
        present_ipv4_addresses: ['51.250.123.126'],
        missing_ipv4_addresses: [],
        stale_ipv4_addresses: [],
        route_results: [],
        healthy: true,
        reason: null,
        checks: {},
      }),
    })

    await getSmartRoutingDomainDiagnostic('cian.ru.')

    const [url, options] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ]
    const headers = options.headers as Headers

    expect(url).toBe(
      '/api/v1/smart-routing/domain-diagnostic?domain=cian.ru.',
    )
    expect(headers.get('Authorization')).toBe('Bearer test-access-token')
  })

  it('sends an authenticated PUT when changing the appliance Kill Switch', async () => {
    const response = {
      kill_switch_enabled: true,
      wan_fallback_active: false,
    }
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response,
    })

    await expect(setVlessApplianceKillSwitch(true)).resolves.toEqual(response)

    const [url, options] = fetchMock.mock.calls[0] as [
      string,
      RequestInit,
    ]
    const headers = options.headers as Headers

    expect(url).toBe('/api/v1/vless/appliance/kill-switch')
    expect(options.method).toBe('PUT')
    expect(options.body).toBe(JSON.stringify({ enabled: true }))
    expect(headers.get('Authorization')).toBe('Bearer test-access-token')
  })

  it('preserves a 401 as ApiError so the UI can end the expired session', async () => {
    vi.stubGlobal('localStorage', {
      getItem: vi.fn(() => null),
    })
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Not authenticated' }),
    })

    await expect(
      getSmartRoutingDomainDiagnostic('cian.ru'),
    ).rejects.toMatchObject({
      name: 'ApiError',
      status: 401,
      detail: 'Not authenticated',
    })
  })
})
