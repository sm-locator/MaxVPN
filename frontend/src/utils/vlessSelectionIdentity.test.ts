import { describe, expect, it } from 'vitest'
import {
  formatVlessOutboundLabel,
  getOutboundTagForLocalProfile,
  isVlessSelectionSnapshotFresh,
  parseVlessProfileIdFromOutbound,
  resolveActiveVlessProfile,
  resolveDisplayedActiveVlessProfile,
  resolveVlessProfileForOutbound,
} from './vlessSelectionIdentity'

const profiles = [
  { id: 4, name: 'Poland local profile', address: 'pl1.japancase.site', port: 443 },
  { id: 9, name: 'US local profile', address: '45.91.248.151', port: 443 },
]
const applianceMap = {
  'vless-profile-17': 4,
  'vless-profile-2': 9,
}

describe('parseVlessProfileIdFromOutbound', () => {
  it.each([
    ['vless-profile-4', 4],
    ['vless-profile-17', 17],
    ['vless-auto', null],
    ['other-profile-4', null],
    ['vless-profile-0', null],
    ['vless-profile-04', null],
    [null, null],
    [undefined, null],
  ] as Array<[string | null | undefined, number | null]>)('parses %s as %s', (outbound, expected) => {
    expect(parseVlessProfileIdFromOutbound(outbound)).toBe(expected)
  })
})

describe('appliance outbound ↔ local profile mapping', () => {
  it('resolves an appliance tag using its mapped local ID, not the number in the tag', () => {
    expect(resolveVlessProfileForOutbound(profiles, 'vless-profile-17', applianceMap)).toEqual(profiles[0])
  })

  it('maps a local profile ID back to the appliance tag', () => {
    expect(getOutboundTagForLocalProfile(4, applianceMap)).toBe('vless-profile-17')
  })

  it('keeps backward compatibility when the backend omits the map', () => {
    expect(getOutboundTagForLocalProfile(4, undefined)).toBe('vless-profile-4')
    expect(resolveVlessProfileForOutbound(profiles, 'vless-profile-9', undefined)).toEqual(profiles[1])
    expect(resolveVlessProfileForOutbound(profiles, 'vless-profile-4', undefined)).toEqual(profiles[0])
  })

  it('does not guess when an explicit map lacks a profile', () => {
    expect(getOutboundTagForLocalProfile(12, applianceMap)).toBeNull()
    expect(resolveVlessProfileForOutbound(profiles, 'vless-profile-4', {})).toBeNull()
  })

  it('rejects empty or invalid profile IDs', () => {
    expect(getOutboundTagForLocalProfile(0, applianceMap)).toBeNull()
    expect(getOutboundTagForLocalProfile(1.5, applianceMap)).toBeNull()
    expect(resolveVlessProfileForOutbound(profiles, null, applianceMap)).toBeNull()
    expect(resolveVlessProfileForOutbound(profiles, 'vless-profile-17', {
      'vless-profile-17': Number.NaN,
    })).toBeNull()
  })
})

describe('resolveActiveVlessProfile', () => {
  it('prefers the actual runtime endpoint when appliance and local IDs differ', () => {
    const result = resolveActiveVlessProfile(profiles, {
      active_outbound: 'vless-profile-17',
      active_server_address: 'pl1.japancase.site',
      active_server_port: 443,
    })
    expect(result).toEqual(profiles[0])
  })

  it('uses the outbound tag when runtime endpoint identity is unavailable', () => {
    expect(resolveActiveVlessProfile(profiles, {
      active_outbound: 'vless-profile-9',
      active_server_address: null,
      active_server_port: null,
    })).toEqual(profiles[1])
  })

  it('does not fall back to the tag when an explicit but unmatched endpoint is reported', () => {
    expect(resolveActiveVlessProfile(profiles, {
      active_outbound: 'vless-profile-4',
      active_server_address: 'unknown.example',
      active_server_port: 443,
    })).toBeNull()
  })

  it('returns null when neither endpoint nor outbound can be resolved', () => {
    expect(resolveActiveVlessProfile(profiles, null)).toBeNull()
    expect(resolveActiveVlessProfile(profiles, { active_outbound: 'vless-auto' })).toBeNull()
  })
})


describe('formatVlessOutboundLabel', () => {
  it('displays the mapped endpoint when appliance and local profile IDs differ', () => {
    const localProfiles = [
      { id: 42, name: 'Netherlands NL2', address: 'nl2.japancase.site', port: 443 },
    ]
    const map = { 'vless-profile-1': 42 }

    expect(formatVlessOutboundLabel(localProfiles, 'vless-profile-1', map))
      .toBe('nl2.japancase.site:443')
  })

  it('keeps an unknown outbound visible for diagnostics', () => {
    expect(formatVlessOutboundLabel(profiles, 'vless-profile-1', {}))
      .toBe('vless-profile-1')
    expect(formatVlessOutboundLabel(profiles, null, applianceMap))
      .toBe('не определён')
  })
})

describe('isVlessSelectionSnapshotFresh', () => {
  const nowMs = Date.parse('2026-10-26T12:00:00.000Z')

  it('accepts a recently observed appliance snapshot', () => {
    const observedAt = new Date(nowMs - 15_000).toISOString()
    expect(isVlessSelectionSnapshotFresh(observedAt, nowMs)).toBe(true)
  })

  it('rejects stale, invalid and implausibly future-dated snapshots', () => {
    expect(
      isVlessSelectionSnapshotFresh(
        new Date(nowMs - 60_000).toISOString(),
        nowMs,
      ),
    ).toBe(false)
    expect(isVlessSelectionSnapshotFresh('not-a-timestamp', nowMs)).toBe(false)
    expect(
      isVlessSelectionSnapshotFresh(
        new Date(nowMs + 20_000).toISOString(),
        nowMs,
      ),
    ).toBe(false)
  })
})

describe('resolveDisplayedActiveVlessProfile', () => {
  const nowMs = Date.parse('2026-10-26T12:00:00.000Z')
  const localProfiles = [
    { id: 42, name: 'Netherlands NL2', address: 'nl2.japancase.site', port: 443 },
    { id: 9, name: 'US local profile', address: '45.91.248.151', port: 443 },
  ]
  const runtime = {
    running: true,
    active_outbound: 'vless-profile-9',
    active_server_address: '45.91.248.151',
    active_server_port: 443,
  }

  it('uses a fresh mapped appliance snapshot over a lagging runtime response', () => {
    const snapshot = {
      active_outbound: 'vless-profile-17',
      observed_at: new Date(nowMs - 15_000).toISOString(),
    }

    expect(
      resolveDisplayedActiveVlessProfile(
        localProfiles,
        runtime,
        snapshot,
        { 'vless-profile-17': 42 },
        nowMs,
      )?.id,
    ).toBe(42)
  })

  it('falls back to runtime identity when the appliance snapshot is stale', () => {
    const snapshot = {
      active_outbound: 'vless-profile-17',
      observed_at: new Date(nowMs - 60_000).toISOString(),
    }

    expect(
      resolveDisplayedActiveVlessProfile(
        localProfiles,
        runtime,
        snapshot,
        { 'vless-profile-17': 42 },
        nowMs,
      )?.id,
    ).toBe(9)
  })

  it('does not display a different stale profile when a fresh snapshot cannot be mapped', () => {
    const snapshot = {
      active_outbound: 'vless-profile-17',
      observed_at: new Date(nowMs - 15_000).toISOString(),
    }

    expect(
      resolveDisplayedActiveVlessProfile(
        localProfiles,
        runtime,
        snapshot,
        {},
        nowMs,
      ),
    ).toBeNull()
  })
})
