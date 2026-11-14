export interface VlessProfileIdentity {
  id: number
  address: string
  port: number
}

export interface VlessRuntimeIdentity {
  active_outbound?: string | null
  active_server_address?: string | null
  active_server_port?: number | null
}

export type VlessProfileIdMap = Record<string, number> | undefined

/** Parse only the expected multi-profile outbound tag format. */
export function parseVlessProfileIdFromOutbound(
  outbound: string | null | undefined,
): number | null {
  const match = outbound?.match(/^vless-profile-([1-9][0-9]*)$/)
  return match ? Number(match[1]) : null
}

/** Resolve the local profile selected by the actual runtime identity. */
export function resolveActiveVlessProfile<T extends VlessProfileIdentity>(
  profiles: readonly T[],
  runtime: VlessRuntimeIdentity | null | undefined,
): T | null {
  const activeProfileId = parseVlessProfileIdFromOutbound(runtime?.active_outbound)
  if (runtime?.active_server_address != null) {
    const runtimeAddress = runtime.active_server_address.toLowerCase().replace(/^\[|\]$/g, '')
    return profiles.find((profile) => (
      profile.port === runtime.active_server_port
      && profile.address.toLowerCase().replace(/^\[|\]$/g, '') === runtimeAddress
    )) ?? null
  }
  return profiles.find((profile) => profile.id === activeProfileId) ?? null
}

/** Convert a local profile ID into its appliance outbound tag.
 * If the API omitted the map, retain compatibility with older backend responses.
 * If the API explicitly supplied a map but no entry exists, do not guess a tag.
 */
export function getOutboundTagForLocalProfile(
  profileId: number,
  profileIdMap: VlessProfileIdMap,
): string | null {
  if (!Number.isInteger(profileId) || profileId <= 0) return null
  if (profileIdMap === undefined) return `vless-profile-${profileId}`
  let matchedOutbound: string | null = null
  for (const [outbound, localProfileId] of Object.entries(profileIdMap)) {
    if (typeof localProfileId === 'number' && Number.isInteger(localProfileId) && localProfileId > 0 && localProfileId === profileId) {
      matchedOutbound = outbound
    }
  }
  return matchedOutbound
}

/** Map a raw appliance outbound tag back to a localhost profile. */
export function resolveVlessProfileForOutbound<T extends Pick<VlessProfileIdentity, 'id'>>(
  profiles: readonly T[],
  outbound: string | null | undefined,
  profileIdMap: VlessProfileIdMap,
): T | null {
  if (!outbound) return null
  let localProfileId: number | null
  if (profileIdMap !== undefined) {
    const mapped = profileIdMap[outbound]
    localProfileId = typeof mapped === 'number' && Number.isInteger(mapped) && mapped > 0 ? mapped : null
  } else {
    localProfileId = parseVlessProfileIdFromOutbound(outbound)
  }
  if (localProfileId === null) return null
  return profiles.find((profile) => profile.id === localProfileId) ?? null
}


/** Display an outbound as its mapped profile endpoint when identity is known. */
export function formatVlessOutboundLabel<T extends VlessProfileIdentity>(
  profiles: readonly T[],
  outbound: string | null | undefined,
  profileIdMap: VlessProfileIdMap,
): string {
  if (!outbound) return 'не определён'
  const profile = resolveVlessProfileForOutbound(profiles, outbound, profileIdMap)
  return profile ? `${profile.address}:${profile.port}` : outbound
}

/** Identity fields from a live appliance selection snapshot. */
export interface VlessSelectionSnapshotIdentity {
  active_outbound?: string | null
  observed_at?: string | null
}

/**
 * The appliance monitor runs every 15 seconds. Accept only a recent snapshot
 * so a delayed history response cannot override a newer live runtime state.
 */
export function isVlessSelectionSnapshotFresh(
  observedAt: string | null | undefined,
  nowMs = Date.now(),
  maxAgeMs = 45_000,
): boolean {
  if (!observedAt) return false

  const observedAtMs = Date.parse(observedAt)
  if (!Number.isFinite(observedAtMs)) return false

  const ageMs = nowMs - observedAtMs
  return ageMs >= -10_000 && ageMs <= maxAgeMs
}

/**
 * Prefer the mapped appliance snapshot when the runtime is running and the
 * snapshot is recent. If it is stale, resolve the profile from runtime data.
 * Never fall back to a different profile when a fresh snapshot cannot map.
 */
export function resolveDisplayedActiveVlessProfile<
  T extends VlessProfileIdentity,
>(
  profiles: readonly T[],
  runtime: (VlessRuntimeIdentity & { running?: boolean | null }) | null | undefined,
  snapshot: VlessSelectionSnapshotIdentity | null | undefined,
  profileIdMap: VlessProfileIdMap,
  nowMs = Date.now(),
): T | null {
  if (
    runtime?.running === true
    && isVlessSelectionSnapshotFresh(snapshot?.observed_at, nowMs)
  ) {
    return resolveVlessProfileForOutbound(
      profiles,
      snapshot?.active_outbound,
      profileIdMap,
    )
  }

  return resolveActiveVlessProfile(profiles, runtime)
}
