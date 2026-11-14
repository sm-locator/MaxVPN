export interface ServerCountrySource {
  address?: string | null
  server_name?: string | null
  name?: string | null
}

export interface ServerCountry {
  code: string
  name: string
  flag: string
  aliases: string[]
}

// Keep this list aligned with the country mapping in appliance/maxvpn/index.html.
const SERVER_COUNTRIES: ServerCountry[] = [
  { code: 'nl', name: 'Нидерланды', flag: '🇳🇱', aliases: ['netherlands', 'holland', 'нидерланд', 'голланд'] },
  { code: 'pl', name: 'Польша', flag: '🇵🇱', aliases: ['poland', 'polska', 'польш'] },
  { code: 'us', name: 'США', flag: '🇺🇸', aliases: ['usa', 'united states', 'america', 'сша', 'соединенные штаты', 'соединённых штатов', 'америка'] },
  { code: 'ca', name: 'Канада', flag: '🇨🇦', aliases: ['canada', 'канада'] },
  { code: 'tr', name: 'Турция', flag: '🇹🇷', aliases: ['turkey', 'türkiye', 'turkiye', 'турция', 'турец'] },
  { code: 'at', name: 'Австрия', flag: '🇦🇹', aliases: ['austria', 'австри'] },
  { code: 'kz', name: 'Казахстан', flag: '🇰🇿', aliases: ['kazakhstan', 'казахстан'] },
  { code: 'lt', name: 'Литва', flag: '🇱🇹', aliases: ['lithuania', 'литв'] },
  { code: 'lv', name: 'Латвия', flag: '🇱🇻', aliases: ['latvia', 'латви'] },
  { code: 'ru', name: 'Россия', flag: '🇷🇺', aliases: ['russia', 'russian federation', 'россия', 'россий'] },
  { code: 'gb', name: 'Великобритания', flag: '🇬🇧', aliases: ['uk', 'united kingdom', 'great britain', 'britain', 'великобритани', 'британи', 'англия'] },
  { code: 'se', name: 'Швеция', flag: '🇸🇪', aliases: ['sweden', 'швеци'] },
  { code: 'fr', name: 'Франция', flag: '🇫🇷', aliases: ['france', 'франци'] },
  { code: 'de', name: 'Германия', flag: '🇩🇪', aliases: ['germany', 'deutschland', 'германи'] },
  { code: 'it', name: 'Италия', flag: '🇮🇹', aliases: ['italy', 'italia', 'итали'] },
  { code: 'fi', name: 'Финляндия', flag: '🇫🇮', aliases: ['finland', 'финлянд'] },
  { code: 'ch', name: 'Швейцария', flag: '🇨🇭', aliases: ['switzerland', 'schweiz', 'швейцари'] },
  { code: 'ae', name: 'ОАЭ', flag: '🇦🇪', aliases: ['uae', 'united arab emirates', 'эмираты', 'оаэ'] },
  { code: 'jp', name: 'Япония', flag: '🇯🇵', aliases: ['japan', 'япони'] },
  { code: 'hk', name: 'Гонконг', flag: '🇭🇰', aliases: ['hong kong', 'гонконг'] },
]

// UK is a common provider-side alias for GB; both resolve to the same flag.
const COUNTRY_CODES: Record<string, ServerCountry> = Object.fromEntries([
  ...SERVER_COUNTRIES.map((country) => [country.code, country] as const),
  ['uk', SERVER_COUNTRIES.find((country) => country.code === 'gb')!],
])

function normalizeText(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase('ru-RU')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
}

function getHost(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^[a-z][a-z0-9+.-]*:\/\//, '')
    .split(/[/?#]/, 1)[0]
    .replace(/:\d+$/, '')
}

function findCountryInHost(host: string): ServerCountry | undefined {
  const match = host.match(/^(nl|pl|us|ca|tr|at|kz|lt|lv|ru|uk|gb|se|fr|de|it|fi|ch|ae|jp|hk)\d*(?=\.|$)/i)
  return match ? COUNTRY_CODES[match[1].toLowerCase()] : undefined
}

function findCountryInName(value: string): ServerCountry | undefined {
  const text = normalizeText(value)
  const codeMatch = text.match(/(?:^|[^a-z0-9])([a-z]{2})(?:$|[^a-z0-9])/i)
  if (codeMatch) {
    const byCode = COUNTRY_CODES[codeMatch[1].toLowerCase()]
    if (byCode) return byCode
  }

  for (const country of SERVER_COUNTRIES) {
    if (country.aliases.some((alias) => text.includes(normalizeText(alias)))) {
      return country
    }
  }
  return undefined
}

export function getServerCountry(source: ServerCountrySource): ServerCountry | null {
  const hostCandidates = [source.address, source.server_name, source.name]
  for (const value of hostCandidates) {
    if (!value) continue
    const country = findCountryInHost(getHost(value))
    if (country) return country
  }

  // Country names and standalone two-letter codes are only considered in the
  // profile name, avoiding false positives from arbitrary domain suffixes.
  if (source.name) return findCountryInName(source.name) ?? null
  return null
}

export function getServerCountryLabel(source: ServerCountrySource): string {
  const country = getServerCountry(source)
  return country ? `${country.flag} ${country.name}` : '🌐 Страна не определена'
}
