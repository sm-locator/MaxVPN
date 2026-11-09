export type TokenResponse = {
  access_token: string
  token_type: string
}

export type CurrentUser = {
  id: number
  email: string
}

export type SmartRoutingTargetType = 'cidr' | 'domain'
export type SmartRoutingAction = 'direct' | 'vpn'
export type SmartRoutingAddressFamily = 'any' | 'ipv4' | 'ipv6'

export type SmartRoutingRule = {
  id: number
  target_type: SmartRoutingTargetType
  target: string
  action: SmartRoutingAction
  priority: number
  address_family: SmartRoutingAddressFamily
  enabled: boolean
  comment?: string
}

export type SmartRoutingRuleCreate = {
  target_type: SmartRoutingTargetType
  target: string
  action: SmartRoutingAction
  priority: number
  address_family: SmartRoutingAddressFamily
  enabled: boolean
}

export type SmartRoutingRuleUpdate = Partial<SmartRoutingRuleCreate>


export type SmartRoutingRouteTestIpSet = {
  ok: boolean
  available: boolean
  raw: string
}

export type SmartRoutingRouteTestRoute = {
  ok: boolean
  raw: string
  dev: string | null
  via: string | null
  command: string[]
  returncode: number
  probe_client_ip: string | null
  probe_client_state: string | null
}

export type SmartRoutingRouteTestDestination = {
  ip: string
  family: string
  direct_ipset: SmartRoutingRouteTestIpSet
  static_ipset: SmartRoutingRouteTestIpSet
  static_net_ipset: SmartRoutingRouteTestIpSet
  marked_route: SmartRoutingRouteTestRoute
  unmarked_route: SmartRoutingRouteTestRoute
  decision: string
  reason: string[]
}

export type SmartRoutingRouteTestConfiguration = {
  config_hash: string
  applied_config_hash: string
  config_dirty: boolean
  applied: boolean
}

export type SmartRoutingRouteTestResolution = {
  ok: boolean
  addresses: string[]
}

export type SmartRoutingRouteTestRuntime = {
  direct_ipset: boolean
  static_ipset: boolean
  static_net_ipset: boolean
  mangle_direct: boolean
  mangle_static: boolean
  mangle_static_net: boolean
  mangle_direct_count: number
  mangle_static_count: number
  mangle_static_net_count: number
  policy_rules: string
  table_200: string
  wan_interface: string
  wan_gateway: string
  vpn_interface: string
}

export type SmartRoutingRouteTestSummary = {
  resolved: number
  direct: number
  vpn: number
  not_applied: number
  disabled: number
  unknown: number
}

export type SmartRoutingRouteTestRule = SmartRoutingRule & {
  comment?: string
}

export type SmartRoutingRouteTest = {
  rule: SmartRoutingRouteTestRule
  configuration: SmartRoutingRouteTestConfiguration
  resolution: SmartRoutingRouteTestResolution
  runtime: SmartRoutingRouteTestRuntime
  overall: string
  destinations: SmartRoutingRouteTestDestination[]
  summary: SmartRoutingRouteTestSummary
  remote_rule_id: number
  remote_rule: SmartRoutingRouteTestRule
}

export type SmartRoutingRuleTestResponse = {
  local_rule: SmartRoutingRule & {
    comment?: string
  }
  route_test: SmartRoutingRouteTest
}

export type SmartRoutingDomainDiagnosticChecks = {
  direct_ipset_readable: boolean
  dnsmasq_mapping_present: boolean
  marking_rule_present: boolean
  policy_rule_present: boolean
  forward_chain_attached: boolean
  direct_forward_rule_present: boolean
  nat_chain_attached: boolean
  nat_masquerade_rule_present: boolean
}

export type SmartRoutingDomainDiagnosticResult = {
  domain: string
  dns_ipv4_addresses: string[]
  present_ipv4_addresses: string[]
  missing_ipv4_addresses: string[]
  stale_ipv4_addresses: string[]
  route_results: string[]
  healthy: boolean
  reason: string | null
  checks: SmartRoutingDomainDiagnosticChecks
}

export type ComponentStatus = {
  status: string
  reason: string | null
}

export type MaxVPNStatus = {
  router: ComponentStatus
  vpn: ComponentStatus
  smart_routing: ComponentStatus
}

export type OpenWrtTrafficRoutingResult = {
  healthy: boolean
  direct_ipset_exists: boolean
  direct_rule_count: number
  routing_table_exists: boolean
  direct_route_exists: boolean
  reason: string | null
}


export type VpnTrafficMode = 'vpn' | 'wan' | 'vless'

export interface VpnRuntimeModeResponse {
  mode: VpnTrafficMode
  message: string
}

export interface VpnRuntime {
  interface: string
  healthy: boolean
  interface_exists: boolean
  interface_up: boolean
  traffic_mode: VpnTrafficMode
  expected_peer_found: boolean
  expected_endpoint: boolean
  endpoint_route_ok: boolean
  listen_port: number | null
  latest_handshake: string | null
  handshake_age_seconds: number | null
  rx_bytes: number
  tx_bytes: number
  reason: string | null
  checked_at: string
  in_sync: boolean
}

export interface VpnProfile {
  id: number
  name: string
  enabled: boolean
  has_private_key: boolean
  has_preshared_key: boolean
}

export interface VpnProfileValidation {
  valid: boolean
  interface_address: string | null
  endpoint: string | null
  allowed_ips: string[]
  has_private_key: boolean
  has_preshared_key: boolean
  reason: string | null
}

export interface VpnProfileApplyResult {
  applied: boolean
  verified: boolean
  no_change: boolean
  rolled_back: boolean
  rollback_verified: boolean
  health_failed: boolean
  reason: string | null
}

export interface VpnProfileConfig {
  name: string
  enabled: boolean

  address: string
  dns: string | null
  mtu: number | null

  jc: number | null
  jmin: number | null
  jmax: number | null

  s1: number | null
  s2: number | null
  s3: number | null
  s4: number | null

  h1: string | null
  h2: string | null
  h3: string | null
  h4: string | null

  i1: string | null
  i2: string | null
  i3: string | null
  i4: string | null
  i5: string | null

  public_key: string
  allowed_ips: string[]
  persistent_keepalive: number | null
  endpoint: string
}

export type VpnProfileConfigUpdate = VpnProfileConfig


export interface AuthTokenResponse {
  id: number
  email: string
  access_token: string
  token_type: string
}


export interface BootstrapStatusResponse {
  available: boolean
}

export interface AdminCredentialsUpdate {
  email: string
  password: string
}

export type RussianDirectPresetResponse = {
  preset: string
  requested: number
  added: number
  already_present: number
  total_domains: number
  rules: SmartRoutingRule[]
}


export type SmartRoutingImportStatus =
  | 'valid'
  | 'duplicate'
  | 'already_exists'
  | 'invalid'

export type SmartRoutingImportItem = {
  line: number
  resource: string
  target_type: SmartRoutingTargetType | null
  address_family: SmartRoutingAddressFamily | null
  status: SmartRoutingImportStatus
  error: string | null
}

export type SmartRoutingImportPreviewResponse = {
  filename: string | null
  total: number
  new: number
  duplicates: number
  already_exists: number
  invalid: number
  items: SmartRoutingImportItem[]
}

export type SmartRoutingImportResponse = {
  filename: string | null
  requested: number
  added: number
  already_exists: number
  duplicates: number
  invalid: number
  rules: SmartRoutingRule[]
}


export type RussianDirectPresetDomainsResponse = {
  preset: string
  total_domains: number
  domains: string[]
}


export type DependencyDiagnosticStartRequest = {
  site_domain: string
  client_ip?: string
  duration_seconds: number
}

export type DependencyDiagnosticResource = {
  hostname: string
  ips: string[]
  cname_chain: string[]
  query_count: number
  relation: 'same_site' | 'external'
  routing: string
  covered_by_rule: boolean
  rule_domain: string | null
  candidate_for_direct: boolean
  synthetic: boolean
  observed_hostnames: string[]
  relevance: 'required' | 'likely' | 'possible' | 'background'
  relevance_score: number
  dependency_reasons: string[]
  related_hostnames: string[]
  recommended_for_direct: boolean
  category: 'target_site' | 'external_candidate' | 'background'
  category_detail: string
  brand_alias: boolean
  selection_allowed: boolean
}

export type DependencyDiagnosticSummary = {
  observed: number
  direct: number
  vpn: number
  partial: number
  unknown: number
  uncovered: number
}

export type DependencyDiagnosticResult = {
  token: string
  site_domain: string
  client_ip: string
  started_at: number
  expires_at: number
  running: boolean
  remaining_seconds: number
  summary?: DependencyDiagnosticSummary
  resources?: DependencyDiagnosticResource[]
}

export type DependencyDiagnosticCommitRule = SmartRoutingRule

export type DependencyDiagnosticCommitResponse = {
  token: string
  site_domain: string
  group_id: number
  created_rules: DependencyDiagnosticCommitRule[]
  reused_rules: DependencyDiagnosticCommitRule[]
  rule_ids: number[]
  apply_required: boolean
}

export type DependencyGroupItem = {
  id: number
  rule_id: number
  source: string
  rule: SmartRoutingRule | null
}

export type DependencyGroup = {
  id: number
  site_domain: string
  title: string
  items: DependencyGroupItem[]
}

export type SmartRoutingSyncDiff = {
  same: SmartRoutingRule[]
  local_only: SmartRoutingRule[]
  remote_only: SmartRoutingRule[]
  semantic_mismatches: Array<{
    target_type: SmartRoutingTargetType
    target: string
    local: SmartRoutingRule
    remote: SmartRoutingRule
  }>
  order_mismatches: Array<{
    position: number
    local: SmartRoutingRule | null
    remote: SmartRoutingRule | null
  }>
  protected_local_only: SmartRoutingRule[]
  unprotected_local_only: SmartRoutingRule[]
  diagnostic_relinks: SmartRoutingRule[]
}

export type SmartRoutingSyncPreview = {
  local: {
    total: number
    rules: SmartRoutingRule[]
  }
  remote: {
    total: number
    rules: SmartRoutingRule[]
    runtime: Record<string, unknown>
    fingerprint: string
  }
  diff: SmartRoutingSyncDiff
}

export type SmartRoutingSyncPullResponse = {
  pulled: boolean
  reason?: string
  created: SmartRoutingRule[]
  created_count?: number
  preserved_local_only: SmartRoutingRule[]
  unprotected_local_only: SmartRoutingRule[]
  relinked?: Array<{
    id: number
    target_type: SmartRoutingTargetType
    target: string
    group_domain: string
  }>
  relinked_count?: number
  remote_total: number
  local_total?: number
  local_total_before?: number
  local_total_after?: number
  remote_fingerprint: string
  apply_required: boolean
}


export type SmartRoutingSyncEnabledResponse = {
  synced: boolean
  updated_count: number
  unchanged_count: number
  matched_count: number
  remote_only_count: number
  remote_total: number
  remote_fingerprint: string
}


export type SmartRoutingSyncPushResponse = {
  pushed: boolean
  reason?: string
  created: SmartRoutingRule[]
  created_count?: number
  remote_total: number
  remote_fingerprint: string
  apply_required: boolean
}

export interface VlessProfile {
  id: number
  name: string
  enabled: boolean
  address: string
  port: number
  flow: string | null
  security: string
  server_name: string | null
  fingerprint: string | null
  has_uuid: boolean
}

export interface VlessProfileValidation {
  valid: boolean
  name: string | null
  address: string | null
  port: number | null
  flow: string | null
  security: string | null
  server_name: string | null
  fingerprint: string | null
  reason: string | null
}

export interface VlessProfileBatchImportItem {
  index: number
  status: 'imported' | 'invalid' | 'duplicate' | 'limit_reached'
  profile: VlessProfile | null
  reason: string | null
}

export interface VlessProfileBatchImportResponse {
  limit: number
  total: number
  imported: number
  failed: number
  duplicates: number
  limit_reached: number
  items: VlessProfileBatchImportItem[]
}

export interface VlessSelectionDelaySample {
  delay_ms: number | null
  observed_at: string | null
}

export interface VlessSelectionSnapshot {
  observed_at: string
  observed_at_epoch?: number
  selection_mode: string
  selected_outbound: string | null
  active_outbound: string | null
  active_delay_ms: number | null
  active_delay_observed_at: string | null
  profile_delays?: Record<string, VlessSelectionDelaySample>
  urltest_interval: string | null
  urltest_tolerance_ms: number | null
}

export interface VlessSelectionHistoryEvent {
  event_id: string
  observed_at: string
  previous_selection_mode: string | null
  selection_mode: string
  previous_outbound: string | null
  active_outbound: string | null
  previous_delay_ms: number | null
  active_delay_ms: number | null
  previous_delay_observed_at: string | null
  active_delay_observed_at: string | null
  previous_delay_age_seconds?: number | null
  active_delay_age_seconds?: number | null
  previous_delay_fresh?: boolean | null
  active_delay_fresh?: boolean | null
  measurement_freshness?: 'fresh' | 'stale' | 'incomplete'
  delay_improvement_ms?: number | null
  diagnostic_status?: string
  diagnostic_details?: string
  diagnostic_origin?: 'recorded' | 'retrospective'
  urltest_interval: string | null
  urltest_tolerance_ms: number | null
  reason: string
  reason_details: string
}

export interface VlessSelectionHistoryResponse {
  monitor: {
    enabled: boolean
    interval_seconds: number
    last_attempt_at: string | null
    last_success_at: string | null
    last_error: string | null
  }
  current: VlessSelectionSnapshot | null
  events: VlessSelectionHistoryEvent[]
  /** Appliance outbound tag -> localhost database profile ID. */
  profile_id_map?: Record<string, number>
}

export interface VlessProfileDelayItem {
  profile_id: number
  delay_ms: number | null
  reachable: boolean
  first_failed_at: string | null
  last_checked_at: string | null
  last_success_at: string | null
  last_outage_started_at: string | null
  last_recovered_at: string | null
  last_outage_duration_seconds: number | null
  consecutive_failures: number
  unavailable_seconds: number | null
}

export interface VlessProfileDelayResponse {
  results: VlessProfileDelayItem[]
}

export interface VlessRuntimeSettings {
  urltest_interval: '30s' | '1m' | '2m' | '3m' | '5m' | '10m'
  urltest_tolerance_ms: number
}

export interface VlessApplianceSyncProfileSummary {
  appliance_id?: number
  id?: number
  name: string
  address: string
  port: number
  enabled: boolean
}

export interface VlessApplianceSyncStatus {
  connected: boolean
  sync_required: boolean
  kill_switch_enabled?: boolean
  local_profile_count: number
  appliance_profile_count: number
  on_router_only: VlessApplianceSyncProfileSummary[]
  local_only: VlessApplianceSyncProfileSummary[]
  updated: VlessApplianceSyncProfileSummary[]
  settings_changed: boolean
  local_settings: VlessRuntimeSettings
  appliance_settings: VlessRuntimeSettings
  selection_mode: 'auto' | 'manual' | 'unknown'
  selected_profile: string | null
  selection_signature: string
  selection_pending?: boolean
  desired_outbound?: string
  runtime_selection_mode?: 'auto' | 'manual' | 'unknown'
  runtime_selected_outbound?: string | null
  runtime_active_outbound?: string | null
  checked_at: string
  synced?: boolean
  sync_result?: {
    imported: number
    updated: number
    deleted: number
    unchanged: number
    profiles: number
    settings_synchronized: boolean
  }
}

export interface VlessRuntime {
  installed: boolean
  running: boolean
  interface: string
  lan_routing_enabled: boolean
  message: string
  action: string | null
  prepared: boolean | null
  selected_outbound?: string | null
  selected_profile_id?: number | null
  active_outbound?: string | null
  active_server_name?: string | null
  active_server_address?: string | null
  active_server_port?: number | null
  selection_mode?: 'auto' | 'manual' | 'legacy' | 'unknown' | null
  runtime_config_mode?: 'multi_profile' | 'single_profile' | 'unknown' | null
}
