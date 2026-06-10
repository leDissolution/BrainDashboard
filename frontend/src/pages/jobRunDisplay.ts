import type { JobRun as DashboardJobRun, JobSubjob } from '../data/dashboard'
import type { JobParameterValue, JobQueueRequest, JobRun as ApiJobRun } from '../lib/api'

export type SchedulerLane = {
  name: string
  value: string
  detail: string
}

export type DisplayJobRun = DashboardJobRun & {
  id: string
  definitionId: string
  canCancel: boolean
  canRestart: boolean
  parameters: Record<string, JobParameterValue>
  restartParameters: Record<string, JobParameterValue>
  restartPriority: NonNullable<JobQueueRequest['priority']>
  queuedAt: string
  startedAt: string | null
  finishedAt: string | null
}

export function buildDisplayJobRuns(runs: ApiJobRun[], now = Date.now()): DisplayJobRun[] {
  return runs.map((run) => buildDisplayJobRun(run, now))
}

export function buildDisplayJobRun(run: ApiJobRun, now = Date.now()): DisplayJobRun {
  const parameters = jobParameterValuesFromEffectiveParameters(run.effective_parameters)
  return {
    id: run.id,
    definitionId: run.definition_id,
    name: run.definition_name ?? run.definition_id,
    status: run.state,
    priority: run.priority,
    progress: progressForRun(run),
    resource: formatRunResource(run),
    eta: formatRunEta(run, now),
    subjobCount: run.subjob_count,
    subjobSummary: run.subjob_summary,
    subjobs: run.subjobs.map(displaySubjobFromApi),
    canCancel: canCancelRun(run.state),
    canRestart: canCopyRun(run.state),
    parameters,
    restartParameters: parameters,
    restartPriority: run.priority,
    queuedAt: run.queued_at,
    startedAt: run.started_at,
    finishedAt: run.finished_at,
  }
}

export function recentFinishedJobRuns(
  runs: DisplayJobRun[],
  rangeHours = 12,
  now = Date.now(),
): DisplayJobRun[] {
  const cutoff = now - rangeHours * 60 * 60 * 1000
  return runs.filter((run) => {
    if (isActiveDisplayRun(run.status) || run.finishedAt === null) {
      return false
    }

    const finishedAt = Date.parse(run.finishedAt)
    return Number.isFinite(finishedAt) && finishedAt >= cutoff
  })
}

export function buildSchedulerLanes(
  runs: ApiJobRun[],
  isLoading: boolean,
  isError: boolean,
): SchedulerLane[] {
  if (isError) {
    return [
      { name: 'Running', value: '-', detail: 'runs unavailable' },
      { name: 'Queued', value: '-', detail: 'runs unavailable' },
      { name: 'Blocked', value: '-', detail: 'runs unavailable' },
    ]
  }

  if (isLoading) {
    return [
      { name: 'Running', value: '-', detail: 'loading runs' },
      { name: 'Queued', value: '-', detail: 'loading runs' },
      { name: 'Blocked', value: '-', detail: 'loading runs' },
    ]
  }

  const activeRuns = runs.filter((run) => isActiveDisplayRun(run.state))
  const runningRuns = runs.filter((run) =>
    ['admitted', 'starting', 'running', 'cancel_requested'].includes(run.state),
  )
  const queuedRuns = runs.filter((run) => ['queued', 'held'].includes(run.state))
  const blockedRuns = runs.filter((run) =>
    ['blocked_by_policy', 'blocked_by_resources'].includes(run.state),
  )

  return [
    {
      name: 'Running',
      value: runningRuns.length.toString(),
      detail: formatSchedulerLaneDetail(runningRuns, 'active now'),
    },
    {
      name: 'Queued',
      value: queuedRuns.length.toString(),
      detail: formatSchedulerLaneDetail(queuedRuns, activeRuns.length ? 'waiting' : 'idle'),
    },
    {
      name: 'Blocked',
      value: blockedRuns.length.toString(),
      detail: formatSchedulerLaneDetail(blockedRuns, 'none blocked'),
    },
  ]
}

export function isActiveDisplayRun(state: string): boolean {
  return [
    'queued',
    'blocked_by_policy',
    'blocked_by_resources',
    'held',
    'admitted',
    'starting',
    'running',
    'cancel_requested',
  ].includes(state)
}

function formatSchedulerLaneDetail(runs: ApiJobRun[], emptyDetail: string): string {
  if (!runs.length) {
    return emptyDetail
  }

  const stateCounts = runs.reduce<Record<string, number>>((counts, run) => {
    counts[run.state] = (counts[run.state] ?? 0) + 1
    return counts
  }, {})

  return Object.entries(stateCounts)
    .map(([state, count]) => `${count} ${formatRunStateLabel(state)}`)
    .join(', ')
}

function formatRunStateLabel(state: string): string {
  return state.replaceAll('_', ' ')
}

function jobParameterValuesFromEffectiveParameters(
  parameters: ApiJobRun['effective_parameters'],
): Record<string, JobParameterValue> {
  return Object.fromEntries(
    Object.entries(parameters).filter((entry): entry is [string, JobParameterValue] => {
      const value = entry[1]
      return (
        value === null ||
        typeof value === 'string' ||
        typeof value === 'number' ||
        typeof value === 'boolean'
      )
    }),
  )
}

function displaySubjobFromApi(subjob: ApiJobRun['subjobs'][number]): JobSubjob {
  return {
    id: subjob.id,
    label: subjob.label,
    status: subjob.status,
    type: subjob.type ?? 'subjob',
    progress: subjob.progress?.percent ?? progressForSubjobStatus(subjob.status),
    detail: subjob.message ?? subjob.phase ?? subjob.latest_event_type,
    index: typeof subjob.index === 'number' ? subjob.index : undefined,
    total: typeof subjob.total === 'number' ? subjob.total : undefined,
  }
}

function progressForSubjobStatus(status: string): number {
  if (status === 'complete' || status === 'completed' || status === 'succeeded') {
    return 100
  }
  if (status === 'running') {
    return 45
  }
  if (status === 'failed') {
    return 100
  }
  return 0
}

function progressForRun(run: ApiJobRun): number {
  return run.progress?.percent ?? progressForRunState(run.state)
}

function progressForRunState(state: ApiJobRun['state']): number {
  if (state === 'succeeded') {
    return 100
  }
  if (state === 'running' || state === 'cancel_requested') {
    return 45
  }
  if (state === 'starting' || state === 'admitted') {
    return 20
  }
  return 0
}

function formatRunResource(run: ApiJobRun): string {
  const failureMessage = failureSummaryMessage(run.failure_summary)
  if (failureMessage !== null) {
    return failureMessage
  }
  return run.effective_command[0] ?? 'native'
}

function failureSummaryMessage(summary: Record<string, unknown> | null): string | null {
  const message = summary?.message
  return typeof message === 'string' && message.length > 0 ? message : null
}

function formatRunEta(run: ApiJobRun, now: number): string {
  if (run.state === 'queued') {
    return 'waiting'
  }
  if (run.state === 'cancel_requested') {
    return 'canceling'
  }
  if (run.state === 'running' || run.state === 'starting' || run.state === 'admitted') {
    return estimateRunEta(run, now) ?? 'active'
  }
  if (run.finished_at !== null) {
    return 'done'
  }
  return 'review'
}

function estimateRunEta(run: ApiJobRun, now: number): string | null {
  const startedAt = run.started_at ?? run.admitted_at
  if (startedAt === null || run.progress === null) {
    return null
  }

  const startedAtMs = Date.parse(startedAt)
  if (!Number.isFinite(startedAtMs)) {
    return null
  }

  const progressPercent = progressPercentForEta(run)
  if (progressPercent === null) {
    return null
  }
  if (progressPercent >= 99.95) {
    return 'finishing'
  }

  const elapsedMs = now - startedAtMs
  if (elapsedMs <= 30_000) {
    return null
  }

  const estimatedTotalMs = elapsedMs / (progressPercent / 100)
  const estimatedRemainingMs = estimatedTotalMs - elapsedMs
  if (!Number.isFinite(estimatedRemainingMs) || estimatedRemainingMs <= 0) {
    return null
  }

  return formatDurationEstimate(estimatedRemainingMs)
}

function progressPercentForEta(run: ApiJobRun): number | null {
  const percent = run.progress?.percent
  if (typeof percent === 'number' && Number.isFinite(percent) && percent > 0) {
    return Math.min(percent, 100)
  }

  const current = run.progress?.current
  const total = run.progress?.total
  if (
    typeof current === 'number' &&
    typeof total === 'number' &&
    Number.isFinite(current) &&
    Number.isFinite(total) &&
    current > 0 &&
    total > 0
  ) {
    return Math.min((current / total) * 100, 100)
  }

  return null
}

function formatDurationEstimate(milliseconds: number): string {
  const totalMinutes = Math.max(1, Math.round(milliseconds / 60_000))
  if (totalMinutes < 60) {
    return `${totalMinutes}m`
  }

  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (minutes === 0) {
    return `${hours}h`
  }
  return `${hours}h ${minutes}m`
}

function canCancelRun(state: ApiJobRun['state']): boolean {
  return ['queued', 'admitted', 'starting', 'running'].includes(state)
}

function canCopyRun(state: ApiJobRun['state']): boolean {
  return [
    'queued',
    'blocked_by_policy',
    'blocked_by_resources',
    'held',
    'admitted',
    'starting',
    'running',
    'cancel_requested',
    'succeeded',
    'failed',
    'canceled',
    'timed_out',
    'lost',
    'needs_review',
  ].includes(state)
}
