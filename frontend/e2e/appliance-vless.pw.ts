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

test('appliance refreshes outage, recovery and stale measurements consistently', async ({ page }) => {
  const now = Date.now()
  const ago = (seconds: number) =>
    new Date(now - seconds * 1000).toISOString()

  const profile = {
    id: 1,
    name: 'Recovery Test',
    enabled: true,
    address: 'nl1.example.test',
    port: 443,
  }

  let phase = 'outage'
  const errors: string[] = []

  page.on('pageerror', error => errors.push(error.message))

  function availability() {
    if (phase === 'recovered') {
      return {
        source: 'urltest',
        last_checked_at: ago(20),
        first_failed_at: null,
        last_recovered_at: ago(20),
        last_outage_duration_seconds: 580,
        delay_ms: 48,
      }
    }

    if (phase === 'stale') {
      return {
        source: 'urltest',
        last_checked_at: ago(400),
        first_failed_at: null,
        delay_ms: 48,
      }
    }

    if (phase === 'stale-outage') {
      return {
        source: 'manual',
        last_checked_at: ago(400),
        first_failed_at: ago(900),
        delay_ms: null,
      }
    }

    return {
      source: 'manual',
      last_checked_at: ago(25),
      first_failed_at: ago(600),
      delay_ms: null,
    }
  }

  await page.route('http://appliance.test/**', async route => {
    const path = new URL(route.request().url()).pathname

    if (path === '/') {
      return route.fulfill({
        contentType: 'text/html',
        body: html,
      })
    }

    if (path.endsWith('/selection-history')) {
      return route.fulfill({
        json: {
          current: { urltest_interval: '3m' },
          profile_availability: {
            '1': availability(),
          },
        },
      })
    }

    if (path.endsWith('/vless')) {
      return route.fulfill({
        json: {
          profiles: [profile],
          running: true,
          traffic_mode: 'vless',
          settings: {
            urltest_interval: '3m',
            wan_fallback_enabled: false,
          },
        },
      })
    }

    return route.fulfill({ json: {} })
  })

  await page.goto('http://appliance.test/')
  await page.locator('[data-page="vless"]').click()
  await page.locator('#vlessProfilesToggle').click()

  const cards = page.locator('#vlessUrltestMeasurementsPanel')
  const rows = page.locator('#vlessProfilesBody')

  async function refresh() {
    await cards.getByRole('button', {
      name: 'Обновить',
    }).click()
  }

  // 1. Confirmed outage.
  await expect(cards).toContainText('Нет ответа')
  await page.locator('#vlessFilter').selectOption('failed')
  await expect(rows.locator('tr')).toHaveCount(1)
  await expect(rows).toContainText('Первый отказ')

  console.log('BROWSER_OUTAGE=PASS')

  // 2. A new successful URLTest restores the profile.
  phase = 'recovered'
  await refresh()

  await expect(cards).toContainText('48 мс')
  await expect(cards.locator('.vless-urltest-age'))
    .toHaveAttribute('title', /Восстановлен/)

  // The failed filter must no longer include this profile.
  await expect(rows).toContainText('Серверы не найдены')

  await page.locator('#vlessFilter').selectOption('reachable')
  await expect(rows.locator('tr')).toHaveCount(1)
  await expect(rows).toContainText('Восстановлен')
  await expect(rows).toContainText('48 мс')

  console.log('BROWSER_RECOVERY=PASS')

  // 3. An old success is no longer considered fresh.
  phase = 'stale'
  await refresh()

  await expect(rows).toContainText('Серверы не найдены')

  await page.locator('#vlessFilter').selectOption('stale')
  await expect(rows.locator('tr')).toHaveCount(1)
  await expect(rows).toContainText('Проверка устарела')
  await expect(cards).toContainText('проверка устарела')

  console.log('BROWSER_STALE_RESULT=PASS')

  // 4. Stale manual failure remains labeled as an outage,
  // but must not be presented as a fresh measurement.
  phase = 'stale-outage'
  await refresh()

  await expect(rows.locator('tr')).toHaveCount(1)
  await expect(rows).toContainText('Нет ответа')
  await expect(rows).toContainText('Первый отказ')
  await expect(cards).toContainText('Ручная проверка BRUME 3')
  await expect(cards).toContainText('проверка устарела')

  await page.locator('#vlessFilter').selectOption('failed')
  await expect(rows.locator('tr')).toHaveCount(1)

  console.log('BROWSER_STALE_OUTAGE=PASS')

  expect(errors).toEqual([])
})
