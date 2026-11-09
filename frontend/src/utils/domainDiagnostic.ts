import type { SmartRoutingDomainDiagnosticChecks } from '../types/api'

type DomainDiagnosticCheckDefinition = {
  key: keyof SmartRoutingDomainDiagnosticChecks
  label: string
  description: string
}

export const domainDiagnosticCheckDefinitions = [
  {
    key: 'direct_ipset_readable',
    label: 'IPSet MAXVPN_DIRECT',
    description: 'Набор IP-адресов DIRECT доступен для чтения.',
  },
  {
    key: 'dnsmasq_mapping_present',
    label: 'DNSMasq mapping',
    description: 'В runtime-конфигурации dnsmasq есть сопоставление домена с MAXVPN_DIRECT.',
  },
  {
    key: 'marking_rule_present',
    label: 'Маркировка пакетов',
    description: 'PREROUTING помечает DIRECT-трафик меткой 0x64.',
  },
  {
    key: 'policy_rule_present',
    label: 'Policy routing',
    description: 'Правило fwmark направляет трафик в таблицу 200.',
  },
  {
    key: 'forward_chain_attached',
    label: 'Цепочка FORWARD',
    description: 'Цепочка MAXVPN_LAN_FORWARD подключена.',
  },
  {
    key: 'direct_forward_rule_present',
    label: 'DIRECT FORWARD',
    description: 'Маркированный трафик br-lan → eth1 разрешён.',
  },
  {
    key: 'nat_chain_attached',
    label: 'Цепочка NAT',
    description: 'Цепочка MAXVPN_DIRECT_NAT подключена.',
  },
  {
    key: 'nat_masquerade_rule_present',
    label: 'DIRECT NAT',
    description: 'Маркированный DIRECT-трафик маскируется через eth1.',
  },
] as const satisfies readonly DomainDiagnosticCheckDefinition[]

const reasonLabels: Record<string, string> = {
  domain_dns_ipv4_not_found: 'DNS не вернул IPv4-адреса для домена.',
  direct_ipset_unavailable_or_incomplete:
    'Набор MAXVPN_DIRECT недоступен или прочитан не полностью.',
  dnsmasq_direct_mapping_missing:
    'Для домена нет DNSMasq-сопоставления с MAXVPN_DIRECT.',
  direct_marking_rule_missing:
    'Не найдено правило маркировки DIRECT-трафика.',
  direct_policy_rule_missing:
    'Не найдено policy rule для маркированного DIRECT-трафика.',
  direct_forward_chain_not_attached:
    'Цепочка FORWARD для DIRECT-трафика не подключена.',
  direct_forward_accept_rule_missing:
    'Не найдено разрешающее правило FORWARD для DIRECT-трафика.',
  direct_nat_chain_not_attached:
    'Цепочка NAT для DIRECT-трафика не подключена.',
  direct_nat_masquerade_rule_missing:
    'Не найдено правило NAT MASQUERADE для DIRECT-трафика.',
  marked_route_verification_failed:
    'Проверка маршрута с меткой DIRECT завершилась ошибкой.',
}

export function formatDomainDiagnosticReason(reason: string | null): string {
  if (!reason) {
    return 'Нет: проверка завершилась успешно.'
  }

  const missingAddressPrefix = 'dns_ipv4_missing_from_direct_ipset:'

  if (reason.startsWith(missingAddressPrefix)) {
    const addresses = reason.slice(missingAddressPrefix.length)
    return 'DNS IPv4 отсутствуют в MAXVPN_DIRECT: ' + addresses
  }

  return reasonLabels[reason] ?? reason
}
