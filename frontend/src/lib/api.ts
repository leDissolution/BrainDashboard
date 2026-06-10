const apiBaseUrl = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

export type HealthResponse = {
  status: string
  service: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/api/health`)

  if (!response.ok) {
    throw new Error(`Health check failed with ${response.status}`)
  }

  return response.json() as Promise<HealthResponse>
}

export type HostSnapshot = {
  timestamp: string
  cpu_percent: number
  cpu_count: number
  cpu_temperature_c: number | null
  memory_percent: number
  memory_used_gib: number
  memory_total_gib: number
  swap_percent: number
  disk_percent: number
  disk_free_gib: number
  disk_total_gib: number
  disks: DiskSnapshot[]
}

export type DiskSnapshot = {
  device: string
  mountpoint: string
  filesystem: string
  percent: number
  free_gib: number
  total_gib: number
}

export type GpuSnapshot = {
  timestamp: string
  index: number
  name: string
  utilization_gpu_percent: number | null
  memory_used_mib: number | null
  memory_total_mib: number | null
  temperature_c: number | null
  power_draw_w: number | null
  power_limit_w: number | null
  clocks_graphics_mhz: number | null
  clocks_memory_mhz: number | null
}

export type NetworkSnapshot = {
  timestamp: string
  interface_name: string
  bytes_sent_per_second: number
  bytes_recv_per_second: number
  packets_sent_per_second: number
  packets_recv_per_second: number
  internet_reachable: boolean
  internet_latency_ms: number | null
}

export type HardwareSnapshot = {
  host: HostSnapshot
  gpus: GpuSnapshot[]
  network: NetworkSnapshot
}

export type HardwareBucket = {
  bucket_start: string
  bucket_seconds: number
  scope: 'host' | 'gpu'
  device_key: string
  device_name: string | null
  run_id: string | null
  sample_count: number
  missing_sample_count: number
  observed_seconds: number
  cpu_percent_avg: number | null
  cpu_percent_min: number | null
  cpu_percent_max: number | null
  memory_percent_avg: number | null
  memory_percent_min: number | null
  memory_percent_max: number | null
  gpu_utilization_percent_avg: number | null
  gpu_utilization_percent_min: number | null
  gpu_utilization_percent_max: number | null
  vram_used_mib_avg: number | null
  vram_used_mib_min: number | null
  vram_used_mib_max: number | null
  vram_total_mib_avg: number | null
  temperature_c_avg: number | null
  temperature_c_min: number | null
  temperature_c_max: number | null
  power_draw_w_avg: number | null
  power_draw_w_min: number | null
  power_draw_w_max: number | null
  energy_kwh: number | null
  cost_amount: number | null
}

export type HardwareHistoryResponse = {
  buckets: HardwareBucket[]
}

export type ClockRange = {
  min: number
  max: number
}

export type ClockOffsetMap = Record<string, number>

export type GpuProfileDefinition = {
  name: string
  label: string
  description: string
  gpu_index: number
  lact_device_id: string | null
  power_limit_watts: number | null
  persistence_mode: boolean | null
  graphics_clocks_mhz: ClockRange | null
  reset_graphics_clocks: boolean
  memory_clocks_mhz: ClockRange | null
  reset_memory_clocks: boolean
  gpu_clock_offsets: ClockOffsetMap | null
  mem_clock_offsets: ClockOffsetMap | null
}

export type GpuProfilesResponse = {
  profiles: GpuProfileDefinition[]
}

export type GpuProfileCommandResponse = {
  status: 'applied' | 'reset'
  profile_name: string | null
  detail: string
  commands: string[]
  warnings: string[]
}

export async function fetchHardwareSnapshot(): Promise<HardwareSnapshot> {
  const response = await fetch(`${apiBaseUrl}/api/hardware/snapshot`)

  if (!response.ok) {
    throw new Error(`Hardware snapshot failed with ${response.status}`)
  }

  return response.json() as Promise<HardwareSnapshot>
}

export async function fetchHardwareHistory(
  rangeHours = 6,
  options: { scope?: HardwareBucket['scope']; deviceKey?: string; limit?: number } = {},
): Promise<HardwareHistoryResponse> {
  const params = new URLSearchParams({ range_hours: String(rangeHours), bucket_seconds: '60' })
  if (options.scope) {
    params.set('scope', options.scope)
  }
  if (options.deviceKey) {
    params.set('device_key', options.deviceKey)
  }
  if (options.limit) {
    params.set('limit', String(options.limit))
  }
  const response = await fetch(`${apiBaseUrl}/api/hardware/history?${params.toString()}`)

  if (!response.ok) {
    throw new Error(`Hardware history failed with ${response.status}`)
  }

  return response.json() as Promise<HardwareHistoryResponse>
}

export async function fetchGpuProfiles(): Promise<GpuProfilesResponse> {
  const response = await fetch(`${apiBaseUrl}/api/gpu/profiles`)

  if (!response.ok) {
    throw new Error(`GPU profiles failed with ${response.status}`)
  }

  return response.json() as Promise<GpuProfilesResponse>
}

export async function applyGpuProfile(profileName: string): Promise<GpuProfileCommandResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/gpu/profiles/${encodeURIComponent(profileName)}/apply`,
    { method: 'POST' },
  )

  if (!response.ok) {
    throw new Error(`GPU profile apply failed with ${response.status}`)
  }

  return response.json() as Promise<GpuProfileCommandResponse>
}

export async function resetGpuProfile(): Promise<GpuProfileCommandResponse> {
  const response = await fetch(`${apiBaseUrl}/api/gpu/reset`, { method: 'POST' })

  if (!response.ok) {
    throw new Error(`GPU profile reset failed with ${response.status}`)
  }

  return response.json() as Promise<GpuProfileCommandResponse>
}

export type ServiceStatus = 'healthy' | 'degraded' | 'offline'

export type ServiceSnapshotItem = {
  name: string
  status: ServiceStatus
  detail: string
  checked_at: string
  parent_name: string | null
  is_active: boolean | null
  latency_ms: number | null
  version: string | null
  model_count: number | null
  active_model: string | null
  running_models: string[] | null
  recent_request_count: number | null
  recent_error_count: number | null
  recent_average_duration_ms: number | null
}

export type ServiceSnapshot = {
  checked_at: string
  services: ServiceSnapshotItem[]
}

export type LlamaSwapUnloadResponse = {
  status: string
  detail: string
}

export type VllmMetricsStatus = 'online' | 'offline'

export type VllmMetricsSample = {
  timestamp: string
  status: VllmMetricsStatus
  detail: string
  model_names: string[]
  running_requests: number | null
  waiting_requests: number | null
  kv_cache_usage_percent: number | null
  prompt_tokens_total: number | null
  prompt_compute_tokens_total: number | null
  prompt_cached_tokens_total: number | null
  generation_tokens_total: number | null
  request_success_total: number | null
  prefix_cache_hits_total: number | null
  prefix_cache_queries_total: number | null
  prefix_cache_hit_percent: number | null
  prompt_tokens_per_second: number | null
  prompt_compute_tokens_per_second: number | null
  prompt_cached_tokens_per_second: number | null
  generation_tokens_per_second: number | null
  requests_per_second: number | null
  ttft_seconds_p50: number | null
  ttft_seconds_p95: number | null
  e2e_latency_seconds_p50: number | null
  e2e_latency_seconds_p95: number | null
  queue_seconds_p50: number | null
  queue_seconds_p95: number | null
}

export type VllmMetricsHistoryResponse = {
  checked_at: string
  endpoint: string
  latest: VllmMetricsSample | null
  samples: VllmMetricsSample[]
}

export type JobExecutionMode = 'native' | 'docker' | 'api'

export type JobResourceHints = {
  gpu_count: number
  min_vram_gib: number | null
  exclusive_gpu: boolean
  docker_required: boolean
}

export type JobRetryPolicy = {
  max_attempts: number
  backoff_seconds: number
}

export type JobParameterValue = string | number | boolean | null

export type JobParameter = {
  name: string
  label: string
  description: string
  value_type: 'string' | 'integer' | 'float' | 'boolean' | 'path' | 'choice' | 'flag'
  cli_flag: string
  default_value: JobParameterValue
  required_at_queue: boolean
  allow_queue_override: boolean
  choices: string[]
}

export type JobDefinition = {
  id: string
  name: string
  description: string
  enabled: boolean
  execution_mode: JobExecutionMode
  command: string[]
  working_directory: string | null
  image: string | null
  default_priority: 'low' | 'normal' | 'high'
  timeout_seconds: number | null
  event_contract: 'structured_stdout' | 'none'
  resource_hints: JobResourceHints
  retry_policy: JobRetryPolicy
  parameters: JobParameter[]
}

export type JobDefinitionsResponse = {
  definitions: JobDefinition[]
}

export type JobRunState =
  | 'queued'
  | 'blocked_by_policy'
  | 'blocked_by_resources'
  | 'held'
  | 'admitted'
  | 'starting'
  | 'running'
  | 'cancel_requested'
  | 'succeeded'
  | 'failed'
  | 'canceled'
  | 'timed_out'
  | 'lost'
  | 'needs_review'

export type JobQueueRequest = {
  parameters: Record<string, JobParameterValue>
  priority?: 'low' | 'normal' | 'high' | null
}

export type JobProgress = {
  current: number | null
  total: number | null
  unit: string | null
  percent: number | null
}

export type JobSubjob = {
  id: string
  type: string | null
  index: number | null
  total: number | null
  parent_id: string | null
  status: string
  label: string
  phase: string | null
  message: string | null
  latest_event_type: string
  progress: JobProgress | null
  metrics: Record<string, unknown>
  error: Record<string, unknown> | null
  metadata: Record<string, unknown>
}

export type JobSubjobSummary = {
  finished: number
  failed: number
  total: number
}

export type JobRun = {
  id: string
  definition_id: string
  definition_name: string | null
  state: JobRunState
  priority: 'low' | 'normal' | 'high'
  attempt: number
  effective_parameters: Record<string, unknown>
  effective_command: string[]
  timeout_seconds: number | null
  external_id: string | null
  log_stdout_path: string | null
  log_stderr_path: string | null
  exit_code: number | null
  failure_summary: Record<string, unknown> | null
  queued_at: string
  admitted_at: string | null
  started_at: string | null
  finished_at: string | null
  cancel_requested_at: string | null
  created_at: string
  updated_at: string
  progress: JobProgress | null
  subjob_count: number
  subjob_summary: JobSubjobSummary
  subjobs: JobSubjob[]
  hardware_usage: JobHardwareUsage | null
}

export type JobHardwareUsage = {
  bucket_count: number
  host_sample_count: number
  gpu_sample_count: number
  gpu_energy_kwh: number
  estimated_cost_amount: number | null
  cpu_percent_avg: number | null
  gpu_utilization_percent_avg: number | null
  gpu_power_draw_w_avg: number | null
  first_bucket_start: string | null
  last_bucket_start: string | null
}

export type JobRunsResponse = {
  runs: JobRun[]
}

export type JobEvent = {
  id: number
  run_id: string
  event_id: string | null
  sequence: number | null
  type: string
  timestamp: string | null
  stream: string
  line_number: number
  phase: string | null
  message: string | null
  progress: Record<string, unknown> | null
  metrics: Record<string, unknown>
  artifacts: Record<string, unknown>[]
  error: Record<string, unknown> | null
  metadata: Record<string, unknown>
  created_at: string
}

export type JobEventsResponse = {
  events: JobEvent[]
}

export type JobLogsResponse = {
  run_id: string
  stream: 'stdout' | 'stderr'
  path: string | null
  lines: string[]
}

export async function fetchServiceSnapshot(): Promise<ServiceSnapshot> {
  const response = await fetch(`${apiBaseUrl}/api/services/snapshot`)

  if (!response.ok) {
    throw new Error(`Service snapshot failed with ${response.status}`)
  }

  return response.json() as Promise<ServiceSnapshot>
}

export async function unloadLlamaSwapModels(): Promise<LlamaSwapUnloadResponse> {
  const response = await fetch(`${apiBaseUrl}/api/services/llama-swap/unload`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(`llama-swap unload failed with ${response.status}`)
  }

  return response.json() as Promise<LlamaSwapUnloadResponse>
}

export async function fetchVllmMetricsHistory(): Promise<VllmMetricsHistoryResponse> {
  const response = await fetch(`${apiBaseUrl}/api/services/vllm/metrics?limit=360`)

  if (!response.ok) {
    throw new Error(`vLLM metrics failed with ${response.status}`)
  }

  return response.json() as Promise<VllmMetricsHistoryResponse>
}

export async function fetchJobDefinitions(): Promise<JobDefinitionsResponse> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/definitions`)

  if (!response.ok) {
    throw new Error(`Job definitions failed with ${response.status}`)
  }

  return response.json() as Promise<JobDefinitionsResponse>
}

export async function fetchJobRuns(
  limit = 200,
  options: { includeSubjobs?: boolean } = {},
): Promise<JobRunsResponse> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (options.includeSubjobs === true) {
    params.set('include_subjobs', 'true')
  }
  const response = await fetch(`${apiBaseUrl}/api/jobs/runs?${params.toString()}`)

  if (!response.ok) {
    throw new Error(`Job runs failed with ${response.status}`)
  }

  return response.json() as Promise<JobRunsResponse>
}

export async function fetchJobRun(runId: string): Promise<JobRun> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/runs/${encodeURIComponent(runId)}`)

  if (!response.ok) {
    throw new Error(`Job run failed with ${response.status}`)
  }

  return response.json() as Promise<JobRun>
}

export async function queueJobDefinition({
  definitionId,
  request,
}: {
  definitionId: string
  request: JobQueueRequest
}): Promise<JobRun> {
  const response = await fetch(
    `${apiBaseUrl}/api/jobs/definitions/${encodeURIComponent(definitionId)}/queue`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
  )

  if (!response.ok) {
    throw new Error(`Job queue failed with ${response.status}`)
  }

  return response.json() as Promise<JobRun>
}

export async function cancelJobRun(runId: string): Promise<JobRun> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })

  if (!response.ok) {
    throw new Error(`Job cancel failed with ${response.status}`)
  }

  return response.json() as Promise<JobRun>
}

export async function fetchJobRunEvents(runId: string): Promise<JobEventsResponse> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/runs/${encodeURIComponent(runId)}/events`)

  if (!response.ok) {
    throw new Error(`Job events failed with ${response.status}`)
  }

  return response.json() as Promise<JobEventsResponse>
}

export async function fetchJobRunLogs(
  runId: string,
  stream: 'stdout' | 'stderr' = 'stdout',
): Promise<JobLogsResponse> {
  const response = await fetch(
    `${apiBaseUrl}/api/jobs/runs/${encodeURIComponent(runId)}/logs?stream=${stream}`,
  )

  if (!response.ok) {
    throw new Error(`Job logs failed with ${response.status}`)
  }

  return response.json() as Promise<JobLogsResponse>
}

export async function createJobDefinition(definition: JobDefinition): Promise<JobDefinition> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/definitions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(definition),
  })

  if (!response.ok) {
    throw new Error(`Job definition create failed with ${response.status}`)
  }

  return response.json() as Promise<JobDefinition>
}

export async function updateJobDefinition(definition: JobDefinition): Promise<JobDefinition> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/definitions/${definition.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(definition),
  })

  if (!response.ok) {
    throw new Error(`Job definition update failed with ${response.status}`)
  }

  return response.json() as Promise<JobDefinition>
}

export async function deleteJobDefinition(definitionId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/jobs/definitions/${definitionId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(`Job definition delete failed with ${response.status}`)
  }
}

function normalizeApiBaseUrl(value: string | undefined): string {
  return value?.replace(/\/$/, '') ?? ''
}
