import { describe, expect, it } from 'vitest'
import {
  domainDiagnosticCheckDefinitions,
  formatDomainDiagnosticReason,
} from './domainDiagnostic'

describe('domainDiagnostic helpers', () => {
  it('defines every individual DIRECT routing check for the UI', () => {
    expect(domainDiagnosticCheckDefinitions).toHaveLength(8)
    expect(domainDiagnosticCheckDefinitions.map((item) => item.key)).toEqual([
      'direct_ipset_readable',
      'dnsmasq_mapping_present',
      'marking_rule_present',
      'policy_rule_present',
      'forward_chain_attached',
      'direct_forward_rule_present',
      'nat_chain_attached',
      'nat_masquerade_rule_present',
    ])
  })

  it('makes an IPSet mismatch understandable without hiding its addresses', () => {
    expect(
      formatDomainDiagnosticReason(
        'dns_ipv4_missing_from_direct_ipset:1.1.1.1,2.2.2.2',
      ),
    ).toBe('DNS IPv4 отсутствуют в MAXVPN_DIRECT: 1.1.1.1,2.2.2.2')
  })
})
