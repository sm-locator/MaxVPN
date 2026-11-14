import { getServerCountry } from '../utils/serverCountry'
import type { ServerCountrySource } from '../utils/serverCountry'

interface Props {
  source: ServerCountrySource
}

function FlagArtwork({ code }: { code: string }) {
  switch (code.toLowerCase()) {
    case 'nl':
      return <><rect width="60" height="13.34" fill="#ae1c28" /><rect y="13.33" width="60" height="13.34" fill="#fff" /><rect y="26.66" width="60" height="13.34" fill="#21468b" /></>
    case 'pl':
      return <><rect width="60" height="20" fill="#fff" /><rect y="20" width="60" height="20" fill="#dc143c" /></>
    case 'us':
      return <>
        {Array.from({ length: 13 }, (_, i) => <rect key={i} y={i * (40 / 13)} width="60" height={40 / 13 + 0.1} fill={i % 2 === 0 ? '#b22234' : '#fff'} />)}
        <rect width="25" height="21.6" fill="#3c3b6e" />
        {Array.from({ length: 6 }, (_, row) => Array.from({ length: row % 2 === 0 ? 3 : 4 }, (_, col) => <circle key={`${row}-${col}`} cx={row % 2 === 0 ? 4.2 + col * 8 : 1.4 + col * 7.2} cy={2.5 + row * 3.3} r="0.9" fill="#fff" />))}
      </>
    case 'ca':
      return <><rect width="15" height="40" fill="#d80621" /><rect x="45" width="15" height="40" fill="#d80621" /><rect x="15" width="30" height="40" fill="#fff" /><path d="M30 7l3.2 7 5-2.2-1.8 6.2 5.1 2.2-6 2.3 1.7 5.6-5.4-2.3-1.8 6.2-2.4-6.2-5 2.4 1.2-6-5.4-2.1 5.1-2.3-1.7-5.8 5 2.1z" fill="#d80621" /></>
    case 'tr':
      return <><rect width="60" height="40" fill="#e30a17" /><circle cx="25" cy="20" r="11" fill="#fff" /><circle cx="29" cy="17" r="9" fill="#e30a17" /><polygon points="42,12 44.4,17 50,17.5 45.8,21.2 47,26.5 42,23.6 37.2,26.5 38.2,21.2 34,17.5 39.5,17" fill="#fff" /></>
    case 'at':
      return <><rect width="60" height="13.34" fill="#ed2939" /><rect y="13.33" width="60" height="13.34" fill="#fff" /><rect y="26.66" width="60" height="13.34" fill="#ed2939" /></>
    case 'kz':
      return <><rect width="60" height="40" fill="#00afca" />{Array.from({ length: 12 }, (_, i) => <line key={i} x1="30" y1="7" x2="30" y2="10" stroke="#f9d616" strokeWidth="1.2" transform={`rotate(${i * 30} 30 17)`} />)}<circle cx="30" cy="17" r="6" fill="#f9d616" /><path d="M16 29q7-7 14 0q7-7 14 0l-5-1-4 5-5-3-5 3-4-5z" fill="#f9d616" /></>
    case 'lt':
      return <><rect width="60" height="13.34" fill="#fdb913" /><rect y="13.33" width="60" height="13.34" fill="#006a44" /><rect y="26.66" width="60" height="13.34" fill="#c1272d" /></>
    case 'lv':
      return <><rect width="60" height="16" fill="#9e3039" /><rect y="16" width="60" height="8" fill="#fff" /><rect y="24" width="60" height="16" fill="#9e3039" /></>
    case 'ru':
      return <><rect width="60" height="13.34" fill="#fff" /><rect y="13.33" width="60" height="13.34" fill="#0039a6" /><rect y="26.66" width="60" height="13.34" fill="#d52b1e" /></>
    case 'gb':
      return <><rect width="60" height="40" fill="#012169" /><path d="M0 0L60 40M60 0L0 40" stroke="#fff" strokeWidth="10" /><path d="M0 0L60 40M60 0L0 40" stroke="#c8102e" strokeWidth="4" /><path d="M30 0V40M0 20H60" stroke="#fff" strokeWidth="14" /><path d="M30 0V40M0 20H60" stroke="#c8102e" strokeWidth="7" /></>
    case 'se':
      return <><rect width="60" height="40" fill="#006aa7" /><path d="M18 0V40M0 20H60" stroke="#fecc00" strokeWidth="6" /></>
    case 'fr':
      return <><rect width="20" height="40" fill="#0055a4" /><rect x="20" width="20" height="40" fill="#fff" /><rect x="40" width="20" height="40" fill="#ef4135" /></>
    case 'de':
      return <><rect width="60" height="13.34" fill="#000" /><rect y="13.33" width="60" height="13.34" fill="#dd0000" /><rect y="26.66" width="60" height="13.34" fill="#ffce00" /></>
    case 'it':
      return <><rect width="20" height="40" fill="#009246" /><rect x="20" width="20" height="40" fill="#fff" /><rect x="40" width="20" height="40" fill="#ce2b37" /></>
    case 'fi':
      return <><rect width="60" height="40" fill="#fff" /><path d="M18 0V40M0 20H60" stroke="#003580" strokeWidth="7" /></>
    case 'ch':
      return <><rect width="60" height="40" fill="#d52b1e" /><path d="M25 8H35V15H43V25H35V32H25V25H17V15H25Z" fill="#fff" /></>
    case 'ae':
      return <><rect width="14" height="40" fill="#f00" /><rect x="14" width="46" height="13.34" fill="#009a44" /><rect x="14" y="13.33" width="46" height="13.34" fill="#fff" /><rect x="14" y="26.66" width="46" height="13.34" fill="#000" /></>
    case 'jp':
      return <><rect width="60" height="40" fill="#fff" /><circle cx="30" cy="20" r="11" fill="#bc002d" /></>
    case 'hk':
      return <><rect width="60" height="40" fill="#de2910" />{Array.from({ length: 5 }, (_, i) => <ellipse key={i} cx={30 + Math.cos((i * 72 - 90) * Math.PI / 180) * 7} cy={20 + Math.sin((i * 72 - 90) * Math.PI / 180) * 7} rx="3.3" ry="7.3" fill="#fff" transform={`rotate(${i * 72} ${30 + Math.cos((i * 72 - 90) * Math.PI / 180) * 7} ${20 + Math.sin((i * 72 - 90) * Math.PI / 180) * 7})`} />)}<circle cx="30" cy="20" r="2.4" fill="#de2910" /></>
    default:
      return <><rect width="60" height="40" fill="#e5e7eb" /><circle cx="30" cy="20" r="13" fill="none" stroke="#64748b" strokeWidth="2" /><path d="M17 20H43M30 7V33" stroke="#64748b" strokeWidth="2" /></>
  }
}

export function ServerCountryLabel({ source }: Props) {
  const country = getServerCountry(source)
  if (!country) {
    return <span className="server-country-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}><span aria-hidden="true">🌐</span><span>Страна не определена</span></span>
  }

  return (
    <span className="server-country-label" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
      <svg className="server-country-flag" width="22" height="15" viewBox="0 0 60 40" style={{ display: 'inline-block', flexShrink: 0, verticalAlign: 'middle', borderRadius: 2 }} role="img" aria-label={`Флаг: ${country.name}`}>
        <title>{country.name}</title>
        <FlagArtwork code={country.code} />
        <rect x="0.5" y="0.5" width="59" height="39" fill="none" stroke="#000" strokeOpacity="0.14" />
      </svg>
      <span>{country.name}</span>
    </span>
  )
}
