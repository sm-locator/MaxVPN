import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const html = readFileSync(new URL('../../appliance/maxvpn/index.html', import.meta.url), 'utf8')

test('appliance shows measured outages and requires confirmation for every profile', async ({ page }) => {
  const now = Date.now()
  const profile = { id: 1, name: 'Test A', enabled: true, address: 'a.example.test', port: 443 }
  let profiles = [profile, { ...profile, id: 2, enabled: false }]
  const deletes: unknown[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('http://appliance.test/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/') return route.fulfill({ contentType: 'text/html', body: html })
    if (path.endsWith('/vless/profiles') && route.request().method() === 'DELETE') {
      deletes.push(route.request().postDataJSON())
      profiles = []
      return route.fulfill({ json: { deleted: 2, traffic_mode: 'wan' } })
    }
    if (path.endsWith('/vless')) return route.fulfill({ json: {
      profiles, running: !!profiles.length, traffic_mode: profiles.length ? 'vless' : 'wan',
      settings: { wan_fallback_enabled: true, urltest_interval: '3m' }, delete_revision: 'test-revision',
    } })
    if (path.endsWith('/selection-history')) return route.fulfill({ json: {
      profile_availability: { '1': { source: 'urltest', last_checked_at: new Date(now).toISOString(),
        first_failed_at: new Date(now - 600_000).toISOString() } },
    } })
    return route.fulfill({ json: {} })
  })
  await page.goto('http://appliance.test/')
  await page.locator('[data-page="vless"]').click()
  await expect(page.locator('#vlessUrltestMeasurementsPanel')).toContainText('Нет ответа · 10')
  await page.locator('#vlessProfilesToggle').click()
  await page.locator('#vlessFilter').selectOption('failed')
  await expect(page.locator('#vlessProfilesBody tr')).toHaveCount(1)
  await expect(page.locator('#vlessProfilesBody')).toContainText('Первый отказ')
  const button = page.getByRole('button', { name: 'Удалить все VLESS-серверы' })
  page.once('dialog', dialog => dialog.dismiss())
  await button.click()
  expect(deletes).toEqual([])
  page.on('dialog', async dialog => {
    if (dialog.type() === 'confirm') {
      expect(dialog.message()).toContain('(2)')
      expect(dialog.message()).toContain('напрямую на WAN')
    }
    await dialog.accept()
  })
  await button.click()
  await expect(button).toBeDisabled()
  expect(deletes).toEqual([{ confirm: true, revision: 'test-revision', allow_wan: true }])
  expect(errors).toEqual([])
})
