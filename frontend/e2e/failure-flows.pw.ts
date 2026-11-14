import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

const rule = {
  id: 7, target_type: 'domain', target: 'example.test', action: 'direct',
  priority: 100, address_family: 'any', enabled: true,
}
const diagnostic = {
  token: 'lab-run', site_domain: 'example.test', client_ip: '192.0.2.10',
  running: false, remaining_seconds: 0, resources: [], summary: { direct: 0, vpn: 0 },
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function openDashboard(page: Page) {
  await page.addInitScript(() => localStorage.setItem('maxvpn_access_token', 'disposable-browser-token'))
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '')
    const responses: Record<string, unknown> = {
      '/auth/me': { id: 1, email: 'browser@example.test' },
      '/auth/bootstrap/status': { available: false },
      '/smart-routing/rules': [rule],
      '/smart-routing/presets/russia-direct': { domains: [] },
      '/smart-routing/dependency-groups': [],
      '/status': { router: { status: 'connected' }, smart_routing: { status: 'healthy' } },
      '/vpn/runtime': { traffic_mode: 'wan', rx_bytes: 0, tx_bytes: 0, checked_at: '2026-11-11T00:00:00Z' },
      '/vpn/profile': null,
      '/vless/runtime': null,
      '/vless/profiles': [],
    }
    if (Object.hasOwn(responses, path)) await json(route, responses[path])
    else await json(route, { detail: 'Unavailable in isolated browser fixture' }, 503)
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Управление маршрутизацией' })).toBeVisible()
  await page.getByRole('button', { name: /Мои исключения/ }).click()
}

test('expired authentication on a rule change ends the session and permits login', async ({ page }) => {
  await openDashboard(page)
  await page.route('**/api/v1/smart-routing/rules/7', route => json(route, { detail: 'Invalid authentication credentials' }, 401))
  await page.getByRole('button', { name: 'Отключить правило', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeEnabled()
  await expect(page.getByText('Сессия завершена. Войдите снова.', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => localStorage.getItem('maxvpn_access_token'))).toBeNull()
  await expect(page.getByText(rule.target, { exact: true })).toHaveCount(0)
})

test('a 401 during diagnostic polling also ends the session', async ({ page }) => {
  await openDashboard(page)
  await page.route('**/dependency-diagnostic/start', route => json(route, { ...diagnostic, running: true }))
  await page.route('**/dependency-diagnostic/lab-run', route => json(route, { detail: 'Invalid authentication credentials' }, 401))
  await page.getByLabel('Сайт', { exact: true }).fill('example.test')
  await page.getByRole('button', { name: 'Запустить диагностику' }).click()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeEnabled()
  expect(await page.evaluate(() => localStorage.getItem('maxvpn_access_token'))).toBeNull()
})

test('logging out during a pending poll prevents further diagnostic polling', async ({ page }) => {
  await openDashboard(page)
  await page.route('**/dependency-diagnostic/start', route => json(route, { ...diagnostic, running: true }))
  let poll: Route | undefined
  let calls = 0
  await page.route('**/dependency-diagnostic/lab-run', route => { calls += 1; poll = route })
  await page.getByLabel('Сайт', { exact: true }).fill('example.test')
  await page.getByRole('button', { name: 'Запустить диагностику' }).click()
  await expect.poll(() => calls).toBe(1)
  await page.getByRole('button', { name: 'Выйти', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeVisible()
  await json(poll!, { ...diagnostic, running: true })
  // Advance actual browser timers past the poll delay after its pending response.
  await page.clock.install()
  await page.clock.runFor(2000)
  expect(calls).toBe(1)
})

test('lost connection leaves refresh usable and preserves the session for recovery', async ({ page }) => {
  await openDashboard(page)
  const refresh = page.getByRole('button', { name: 'Обновить состояние', exact: true })
  await page.route('**/api/v1/status', route => route.abort('connectionreset'))
  await refresh.click()
  await expect(page.getByText('Failed to fetch', { exact: true }).first()).toBeVisible()
  await expect(refresh).toBeEnabled()
  expect(await page.evaluate(() => localStorage.getItem('maxvpn_access_token'))).toBeTruthy()
  await page.unroute('**/api/v1/status')
  await refresh.click()
  await expect(page.getByText('Failed to fetch', { exact: true })).toHaveCount(0)
  await expect(refresh).toBeEnabled()
})

test('diagnostic polling failure releases the form and a second run completes', async ({ page }) => {
  await openDashboard(page)
  let starts = 0
  await page.route('**/dependency-diagnostic/start', route => {
    starts += 1
    return json(route, { ...diagnostic, running: true })
  })
  await page.route('**/dependency-diagnostic/lab-run', route => starts === 1
    ? route.abort('connectionreset') : json(route, diagnostic))
  await page.getByLabel('Сайт', { exact: true }).fill('example.test')
  const start = page.getByRole('button', { name: 'Запустить диагностику' })
  await start.click()
  await expect(page.getByText('Failed to fetch', { exact: true })).toBeVisible()
  await expect(start).toBeEnabled()
  await expect(page.getByText(/Наблюдение:.*сек/)).toHaveCount(0)
  await start.click()
  await expect(page.getByText('Найдено DNS-ресурсов: 0', { exact: true })).toBeVisible()
  await expect(start).toBeEnabled()
  expect(starts).toBe(2)
})

test('failed toggle and delete preserve the rule and release its buttons', async ({ page }) => {
  const uncaught: string[] = []
  page.on('pageerror', error => uncaught.push(error.message))
  await openDashboard(page)
  await page.route('**/api/v1/smart-routing/rules/7', route => json(route, { detail: 'Lab rule change failed' }, 500))
  const toggle = page.getByRole('button', { name: 'Отключить правило', exact: true })
  const remove = page.getByRole('button', { name: 'Удалить правило', exact: true })
  for (const button of [toggle, remove]) {
    await button.click()
    await expect(page.getByText('Lab rule change failed', { exact: true })).toBeVisible()
    await expect(toggle).toBeEnabled()
    await expect(remove).toBeEnabled()
    await expect(page.getByText(rule.target, { exact: true })).toBeVisible()
  }
  expect(uncaught).toEqual([])
})
