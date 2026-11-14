import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { randomUUID } from 'node:crypto'

const state = process.env.MAXVPN_LIVE_STATE
if (!state?.startsWith('/tmp/maxvpn-live-e2e-')) throw new Error('An isolated live test state is required')
const root = resolve('..')
const email = 'live-admin@example.com'
const password = 'live-disposable-password'

function clientDns() {
  execFileSync('python3', [resolve(root, 'scripts/openwrt_lab.py'), '--state', `${state}/lab`, 'exec', 'client', 'nslookup assets.example.test 192.168.77.1'], { timeout: 30_000 })
}

async function headers(page: Page) {
  return { Authorization: 'Bearer ' + await page.evaluate(() => localStorage.getItem('maxvpn_access_token')) }
}

async function login(page: Page, secret = password) {
  await page.goto('/')
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Пароль', { exact: true }).fill(secret)
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Управление маршрутизацией' })).toBeVisible()
}

test.describe.serial('real browser, API, PostgreSQL and OpenWrt', () => {
  test('bootstrap, encrypted profile, rules, DNS diagnostic, push/apply and login persistence', async ({ page }) => {
    const bootstrap = await page.request.get('/api/v1/auth/bootstrap/status')
    await page.goto('/')
    if ((await bootstrap.json()).available) {
      await page.getByRole('button', { name: 'Первый запуск — создать администратора' }).click()
      await page.getByLabel('Email администратора', { exact: true }).fill(email)
      await page.getByLabel('Пароль', { exact: true }).fill(password)
      await page.getByLabel('Повторите пароль', { exact: true }).fill(password)
      await page.getByRole('button', { name: 'Создать администратора', exact: true }).click()
      await expect(page.getByRole('heading', { name: 'Управление маршрутизацией' })).toBeVisible()
    } else await login(page)

    const auth = await headers(page)
    // Only clean this disposable administrator's records, through the real API.
    for (const rule of await (await page.request.get('/api/v1/smart-routing/rules', { headers: auth })).json()) {
      expect((await page.request.delete(`/api/v1/smart-routing/rules/${rule.id}`, { headers: auth })).ok()).toBeTruthy()
    }
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Управление маршрутизацией' })).toBeVisible()
    const uuid = randomUUID()
    const metadata = JSON.parse(readFileSync(`${state}/state.json`, 'utf8'))
    const source = JSON.stringify({ remarks: 'Live profile', outbounds: [{ protocol: 'vless', settings: { vnext: [{ address: '198.18.0.1', port: 24443, users: [{ id: uuid }] }] }, streamSettings: { network: 'tcp', security: 'none' } }] })
    await page.getByLabel('VLESS-ссылки или JSON-конфигурация').fill(source)
    const imported = page.waitForResponse(response => response.url().endsWith('/vless/profile/import') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Импортировать', exact: true }).click()
    expect((await imported).ok()).toBeTruthy()
    const profiles = await page.request.get('/api/v1/vless/profiles', { headers: auth })
    expect(await profiles.text()).not.toContain(uuid)
    const exported = await page.request.get('/api/v1/vless/profiles/export', { headers: auth })
    expect(await exported.text()).toContain(uuid)
    execFileSync(metadata.python, [resolve(root, 'scripts/live_e2e.py'), '--state', state!, 'verify-encryption'], { input: uuid, timeout: 15_000 })

    await page.getByRole('button', { name: 'IP-адрес / CIDR', exact: true }).click()
    await page.locator('.rule-form input').fill('203.0.113.30/32')
    await page.getByRole('button', { name: 'Добавить', exact: true }).click()
    await page.getByRole('button', { name: /Мои исключения/ }).click()
    const row = page.locator('.rule-row').filter({ hasText: '203.0.113.30/32' })
    // Stable accessible controls are scoped to the only manually created rule.
    await row.getByRole('button', { name: 'Отключить правило', exact: true }).click()
    await expect(row.getByRole('button', { name: 'Включить правило', exact: true })).toBeEnabled()
    await row.getByRole('button', { name: 'Включить правило', exact: true }).click()
    await expect(row.getByRole('button', { name: 'Отключить правило', exact: true })).toBeEnabled()

    await page.getByLabel('Сайт', { exact: true }).fill('example.test')
    await page.getByText('Указать IP другого устройства', { exact: true }).click()
    await page.getByLabel('IP клиента (необязательно)').fill('192.168.77.10')
    await page.getByLabel('Время наблюдения').selectOption('20')
    await page.getByRole('button', { name: 'Запустить диагностику' }).click()
    await expect(page.getByText(/Диагностика запущена для клиента/)).toBeVisible()
    clientDns()
    await expect(page.getByRole('button', { name: 'Запустить диагностику' })).toBeEnabled({ timeout: 40_000 })
    const candidate = page.locator('.dependency-table tr').filter({ hasText: 'assets.example.test' })
    await expect(candidate.getByRole('checkbox')).toBeVisible()
    await candidate.getByRole('checkbox').check()
    const committed = page.waitForResponse(response => /dependency-diagnostic\/.+\/rules$/.test(response.url()) && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Добавить выбранные в DIRECT (1)', exact: true }).click()
    expect((await committed).status()).toBe(201)
    const groups = await page.request.get('/api/v1/smart-routing/dependency-groups', { headers: auth })
    expect(await groups.text()).toContain('example.test')

    page.on('dialog', dialog => dialog.accept())
    const sync = page.locator('.smart-routing-sync')
    await sync.getByRole('button', { name: 'Обновить', exact: true }).click()
    const pushed = page.waitForResponse(response => response.url().endsWith('/smart-routing/sync/push'))
    await page.getByRole('button', { name: /^Отправить \d+$/ }).click()
    expect((await pushed).ok()).toBeTruthy()
    const applied = page.waitForResponse(response => response.url().endsWith('/smart-routing/apply'))
    await page.getByRole('button', { name: 'Применить runtime', exact: true }).click()
    expect((await applied).ok()).toBeTruthy()
    await expect(page.getByRole('heading', { name: 'Применён', exact: true })).toBeVisible()
    execFileSync(metadata.python, [resolve(root, 'scripts/live_e2e.py'), '--state', state!, 'verify-routing'], { timeout: 60_000, stdio: ['ignore', 'pipe', 'pipe'] })

    await page.getByRole('button', { name: 'Выйти', exact: true }).click()
    await login(page)
    const rules = await page.request.get('/api/v1/smart-routing/rules', { headers: await headers(page) })
    expect(await rules.text()).toContain('assets.example.test')
    const bundle = await page.request.get('/api/v1/vless/profiles/export', { headers: await headers(page) })
    expect(await bundle.text()).toContain(uuid)
  })

  test('real user isolation and password change revoke earlier sessions', async ({ page }) => {
    await login(page)
    const old = await headers(page)
    const member = { email: 'live-member@example.com', password: 'member-disposable-password', role: 'admin' }
    const registered = await page.request.post('/api/v1/auth/register', { data: member })
    expect([200, 409]).toContain(registered.status())
    const logged = await page.request.post('/api/v1/auth/login', { form: { username: member.email, password: member.password } })
    const memberAuth = { Authorization: 'Bearer ' + (await logged.json()).access_token }
    for (const path of ['/vless/appliance-sync', '/vpn/start', '/smart-routing/apply']) {
      expect((await page.request.post('/api/v1' + path, { headers: memberAuth, data: {} })).status()).toBe(403)
    }
    expect(await (await page.request.get('/api/v1/vless/profiles', { headers: memberAuth })).json()).toEqual([])
    const own = await page.request.post('/api/v1/smart-routing/rules', { headers: memberAuth, data: {
      target_type: 'domain', target: 'member.example.test', action: 'direct', priority: 1, address_family: 'any', enabled: true,
    } })
    expect(own.status()).toBe(201)
    const ownId = (await own.json()).id
    expect((await page.request.delete(`/api/v1/smart-routing/rules/${ownId}`, { headers: memberAuth })).status()).toBe(204)
    const adminRules = await (await page.request.get('/api/v1/smart-routing/rules', { headers: old })).json()
    expect((await page.request.get(`/api/v1/smart-routing/rules/${adminRules[0].id}`, { headers: memberAuth })).status()).toBe(404)

    await page.getByRole('button', { name: 'Настройки', exact: true }).click()
    const settings = page.locator('.admin-settings-card')
    await settings.getByLabel('Новый пароль', { exact: true }).fill('changed-disposable-password')
    await settings.getByLabel('Повторите пароль', { exact: true }).fill('changed-disposable-password')
    await settings.getByRole('button', { name: /Сохранить/ }).click()
    await expect(settings).toHaveCount(0)
    expect((await page.request.get('/api/v1/auth/me', { headers: old })).status()).toBe(401)
    await page.getByRole('button', { name: 'Выйти', exact: true }).click()
    await login(page, 'changed-disposable-password')
    expect((await page.request.get('/api/v1/vless/profiles/export', { headers: await headers(page) })).ok()).toBeTruthy()
    const metadata = JSON.parse(readFileSync(`${state}/state.json`, 'utf8'))
    const token = await page.evaluate(() => localStorage.getItem('maxvpn_access_token'))
    const expired = execFileSync(metadata.python, [resolve(root, 'scripts/live_e2e.py'), '--state', state!, 'expired-token'], { input: token!, encoding: 'utf8' }).trim()
    await page.evaluate(value => localStorage.setItem('maxvpn_access_token', value), expired)
    await page.getByRole('button', { name: 'Обновить состояние', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Войти', exact: true })).toBeEnabled()
    expect(await page.evaluate(() => localStorage.getItem('maxvpn_access_token'))).toBeNull()
    await login(page, 'changed-disposable-password')
  })
})
