import { useState } from 'react'
import { metrics, gpuProfiles, type Metric, type GpuProfile } from '../data/dashboard'
import type {
  DiskSnapshot,
  GpuProfileDefinition,
  GpuSnapshot,
  HardwareBucket,
  HardwareHistoryResponse,
  HardwareSnapshot,
  NetworkSnapshot,
} from '../lib/api'

type HardwarePageProps = {
  snapshot: HardwareSnapshot | undefined
  snapshotIsError: boolean
  snapshotIsLoading: boolean
  history: HardwareHistoryResponse | undefined
  historyIsError: boolean
  historyIsLoading: boolean
  heatmapHistory: HardwareHistoryResponse | undefined
  heatmapHistoryIsError: boolean
  heatmapHistoryIsLoading: boolean
  profiles: GpuProfileDefinition[] | undefined
  profilesIsError: boolean
  profilesIsLoading: boolean
  isApplyingProfile: boolean
  applyProfileError: boolean
  applyProfileWarning: string | undefined
  applyingProfileName: string | undefined
  onApplyProfile: (profileName: string) => void
}

type HardwareSummaryGridProps = Omit<
  HardwarePageProps,
  | 'history'
  | 'historyIsError'
  | 'historyIsLoading'
  | 'heatmapHistory'
  | 'heatmapHistoryIsError'
  | 'heatmapHistoryIsLoading'
>

type ChartSeries = {
  label: string
  values: ChartPoint[]
  tone: 'primary' | 'secondary' | 'power'
}

type ChartPoint = {
  timestamp: string
  value: number
}

type HeatmapCell = {
  dateKey: string
  dayLabel: string
  hour: number
  value: number | null
  sampleCount: number
}

export function HardwarePage({
  snapshot,
  snapshotIsError,
  snapshotIsLoading,
  history,
  historyIsError,
  historyIsLoading,
  heatmapHistory,
  heatmapHistoryIsError,
  heatmapHistoryIsLoading,
  profiles,
  profilesIsError,
  profilesIsLoading,
  isApplyingProfile,
  applyProfileError,
  applyProfileWarning,
  applyingProfileName,
  onApplyProfile,
}: HardwarePageProps) {
  const [heatmapRangeDays, setHeatmapRangeDays] = useState<7 | 30>(7)
  const hostBuckets = history?.buckets.filter((bucket) => bucket.scope === 'host') ?? []
  const primaryGpuBuckets = selectPrimaryGpuBuckets(history?.buckets ?? [])
  const heatmapGpuBuckets = selectPrimaryGpuBuckets(heatmapHistory?.buckets ?? [])
  const heatmapCells = buildGpuHeatmapCells(heatmapGpuBuckets, heatmapRangeDays)
  const utilizationSeries = [
    buildSeries('CPU', hostBuckets, (bucket) => bucket.cpu_percent_avg, 'primary'),
    buildSeries('Memory', hostBuckets, (bucket) => bucket.memory_percent_avg, 'secondary'),
    buildSeries(
      'GPU load',
      primaryGpuBuckets,
      (bucket) => bucket.gpu_utilization_percent_avg,
      'power',
    ),
  ]
  const gpuPowerSeries = [
    buildSeries('GPU watts', primaryGpuBuckets, (bucket) => bucket.power_draw_w_avg, 'power'),
  ]
  const totalGpuEnergy = primaryGpuBuckets.reduce(
    (total, bucket) => total + (bucket.energy_kwh ?? 0),
    0,
  )
  const totalGpuCost = primaryGpuBuckets.reduce(
    (total, bucket) => total + (bucket.cost_amount ?? 0),
    0,
  )
  const hasCost = primaryGpuBuckets.some((bucket) => bucket.cost_amount !== null)

  return (
    <div className="hardware-workspace">
      <HardwareSummaryGrid
        snapshot={snapshot}
        snapshotIsError={snapshotIsError}
        snapshotIsLoading={snapshotIsLoading}
        profiles={profiles}
        profilesIsError={profilesIsError}
        profilesIsLoading={profilesIsLoading}
        isApplyingProfile={isApplyingProfile}
        applyProfileError={applyProfileError}
        applyProfileWarning={applyProfileWarning}
        applyingProfileName={applyingProfileName}
        onApplyProfile={onApplyProfile}
      />

      <section className="hardware-grid">
        <div className="surface hardware-chart-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Utilization</p>
              <h2>Six Hour Load</h2>
            </div>
            <span className="history-status">
              {historyIsError ? 'unavailable' : historyIsLoading ? 'loading' : `${history?.buckets.length ?? 0} buckets`}
            </span>
          </div>
          <LineChart
            series={utilizationSeries}
            unit="%"
            maxValue={100}
            emptyLabel={historyIsError ? 'History unavailable' : 'Waiting for buckets'}
          />
        </div>

        <div className="surface hardware-chart-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Power</p>
              <h2>GPU Draw</h2>
            </div>
            <span className="history-status">{formatEnergy(totalGpuEnergy)}</span>
          </div>
          <LineChart
            series={gpuPowerSeries}
            unit="W"
            emptyLabel={historyIsError ? 'History unavailable' : 'Waiting for GPU buckets'}
          />
          <div className="energy-strip">
            <span>
              <strong>{formatEnergy(totalGpuEnergy)}</strong>
              <small>GPU energy</small>
            </span>
            <span>
              <strong>{hasCost ? formatCurrency(totalGpuCost) : 'n/a'}</strong>
              <small>estimated cost</small>
            </span>
          </div>
        </div>
      </section>

      <section className="surface hardware-heatmap-surface">
        <div className="section-heading">
          <div>
            <p className="eyebrow">GPU Utilization</p>
            <h2>24 Hour Heatmap</h2>
          </div>
          <div className="heatmap-controls" aria-label="Heatmap range">
            {[7, 30].map((rangeDays) => (
              <button
                className={heatmapRangeDays === rangeDays ? 'active' : ''}
                type="button"
                key={rangeDays}
                onClick={() => setHeatmapRangeDays(rangeDays as 7 | 30)}
              >
                {rangeDays}d
              </button>
            ))}
          </div>
        </div>
        <GpuUsageHeatmap
          cells={heatmapCells}
          rangeDays={heatmapRangeDays}
          isError={heatmapHistoryIsError}
          isLoading={heatmapHistoryIsLoading}
        />
      </section>
    </div>
  )
}

export function HardwareSummaryGrid({
  snapshot,
  snapshotIsError,
  snapshotIsLoading,
  profiles,
  profilesIsError,
  profilesIsLoading,
  isApplyingProfile,
  applyProfileError,
  applyProfileWarning,
  applyingProfileName,
  onApplyProfile,
}: HardwareSummaryGridProps) {
  const [isGpuProfileMenuOpen, setIsGpuProfileMenuOpen] = useState(false)
  const [isStorageMenuOpen, setIsStorageMenuOpen] = useState(false)
  const metricCards = buildMetricCards(snapshot, snapshotIsError, snapshotIsLoading)
  const gpuProfileCards = buildGpuProfileCards(
    profiles,
    snapshot?.gpus,
    profilesIsError,
    profilesIsLoading,
  )

  return (
    <section className="summary-grid" aria-label="Resource summary">
      {metricCards.map((metric) =>
        metric.label === 'GPU' ? (
          <GpuMetricCard
            metric={metric}
            profiles={gpuProfileCards}
            isOpen={isGpuProfileMenuOpen}
            isApplying={isApplyingProfile}
            isError={applyProfileError}
            warning={applyProfileWarning}
            applyingProfileName={applyingProfileName}
            onToggle={() => setIsGpuProfileMenuOpen((isOpen) => !isOpen)}
            onApply={(profileName) => {
              onApplyProfile(profileName)
              setIsGpuProfileMenuOpen(false)
            }}
            key={metric.label}
          />
        ) : metric.label === 'Storage' ? (
          <StorageMetricCard
            metric={metric}
            disks={snapshot?.host.disks ?? []}
            isOpen={isStorageMenuOpen}
            onToggle={() => setIsStorageMenuOpen((isOpen) => !isOpen)}
            key={metric.label}
          />
        ) : (
          <MetricCard metric={metric} key={metric.label} />
        ),
      )}
    </section>
  )
}

function MetricCard({ metric }: { metric: Metric }) {
  return (
    <article className={`metric-card ${metric.tone}`}>
      <div className="metric-head">
        <metric.icon size={18} />
        <span>{metric.label}</span>
      </div>
      <strong>{metric.value}</strong>
      <span className="detail">{metric.detail}</span>
      <div className="meter" aria-hidden="true">
        <span style={{ width: `${metric.percent ?? 0}%` }} />
      </div>
    </article>
  )
}

function StorageMetricCard({
  metric,
  disks,
  isOpen,
  onToggle,
}: {
  metric: Metric
  disks: DiskSnapshot[]
  isOpen: boolean
  onToggle: () => void
}) {
  return (
    <article
      className={`metric-card storage-metric-card ${metric.tone} ${isOpen ? 'open' : ''}`}
      role="button"
      tabIndex={0}
      aria-expanded={isOpen}
      aria-haspopup="menu"
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onToggle()
        }
      }}
    >
      <div className="metric-head">
        <metric.icon size={18} />
        <span>{metric.label}</span>
      </div>
      <strong>{metric.value}</strong>
      <span className="detail">{metric.detail}</span>
      <div className="meter" aria-hidden="true">
        <span style={{ width: `${metric.percent ?? 0}%` }} />
      </div>
      {isOpen ? <StorageMenu disks={disks} /> : null}
    </article>
  )
}

function StorageMenu({ disks }: { disks: DiskSnapshot[] }) {
  return (
    <div
      className="storage-menu"
      role="menu"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      {disks.length ? (
        disks.map((disk) => (
          <article
            className={`storage-option ${toneForPercent(disk.percent)}`}
            key={`${disk.device}-${disk.mountpoint}`}
          >
            <div>
              <strong>{disk.mountpoint}</strong>
              <small>{[disk.device, disk.filesystem].filter(Boolean).join(' · ')}</small>
            </div>
            <div className="storage-specs">
              <span>{formatPercent(disk.percent)}</span>
              <small>
                {formatNumber(disk.free_gib)} / {formatNumber(disk.total_gib)} GiB free
              </small>
            </div>
            <div className="meter storage-meter" aria-hidden="true">
              <span style={{ width: `${disk.percent}%` }} />
            </div>
          </article>
        ))
      ) : (
        <article className="storage-option empty">
          <strong>No disk telemetry</strong>
          <small>Waiting for hardware snapshot</small>
        </article>
      )}
    </div>
  )
}

function GpuMetricCard({
  metric,
  profiles,
  isOpen,
  isApplying,
  isError,
  warning,
  applyingProfileName,
  onToggle,
  onApply,
}: {
  metric: Metric
  profiles: GpuProfile[]
  isOpen: boolean
  isApplying: boolean
  isError: boolean
  warning: string | undefined
  applyingProfileName: string | undefined
  onToggle: () => void
  onApply: (profileName: string) => void
}) {
  const activeProfile = profiles.find((profile) => profile.state === 'active')
  const hasSelectableProfiles = profiles.some((profile) => profile.profileName)
  const activeLabel =
    activeProfile?.name ?? (hasSelectableProfiles ? 'No profile' : 'Profiles unavailable')

  return (
    <article
      className={`metric-card gpu-metric-card ${metric.tone} ${isOpen ? 'open' : ''}`}
      role="button"
      tabIndex={0}
      aria-expanded={isOpen}
      aria-haspopup="menu"
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onToggle()
        }
      }}
    >
      <div className="metric-head">
        <metric.icon size={18} />
        <span>{metric.label}</span>
      </div>
      <strong>{metric.value}</strong>
      <div className="metric-detail-row">
        <span className="detail">{metric.detail}</span>
        <span className={`gpu-profile-chip ${activeProfile ? 'active' : ''}`}>
          {isApplying ? `Applying ${findProfileName(profiles, applyingProfileName)}` : activeLabel}
        </span>
      </div>
      <div className="meter" aria-hidden="true">
        <span style={{ width: `${metric.percent ?? 0}%` }} />
      </div>
      {isError ? <span className="gpu-profile-error">apply failed</span> : null}
      {!isError && warning ? (
        <span className="gpu-profile-warning" title={warning}>
          offset warning
        </span>
      ) : null}
      {isOpen ? (
        <GpuProfileMenu profiles={profiles} isApplying={isApplying} onApply={onApply} />
      ) : null}
    </article>
  )
}

function GpuProfileMenu({
  profiles,
  isApplying,
  onApply,
}: {
  profiles: GpuProfile[]
  isApplying: boolean
  onApply: (profileName: string) => void
}) {
  return (
    <div
      className="gpu-profile-menu"
      role="menu"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      {profiles.map((profile) => (
        <button
          className={`gpu-profile-option ${profile.state}`}
          type="button"
          role="menuitem"
          key={profile.name}
          disabled={!profile.profileName || isApplying}
          onClick={() => {
            if (profile.profileName) {
              onApply(profile.profileName)
            }
          }}
        >
          <span>
            <strong>{profile.name}</strong>
            <small>{profile.description || `${profile.power} · ${profile.clocks}`}</small>
          </span>
          <span className="gpu-profile-specs">
            <span>{profile.power}</span>
            <span>{profile.clocks}</span>
          </span>
        </button>
      ))}
    </div>
  )
}

function LineChart({
  series,
  unit,
  maxValue,
  emptyLabel,
}: {
  series: ChartSeries[]
  unit: string
  maxValue?: number
  emptyLabel: string
}) {
  const populatedSeries = series.filter((item) => item.values.length > 0)
  const allValues = populatedSeries.flatMap((item) => item.values.map((point) => point.value))
  const highestValue = maxValue ?? Math.max(...allValues, 1)

  if (allValues.length === 0) {
    return <div className="chart-empty">{emptyLabel}</div>
  }

  return (
    <div className="line-chart">
      <svg viewBox="0 0 640 220" role="img" aria-label="Hardware history chart">
        <g className="chart-grid" aria-hidden="true">
          {[0, 1, 2, 3].map((line) => (
            <line key={line} x1="0" x2="640" y1={line * 55} y2={line * 55} />
          ))}
        </g>
        {populatedSeries.map((item) => (
          <polyline
            key={item.label}
            className={`chart-line ${item.tone}`}
            points={polylinePoints(item.values, highestValue)}
          />
        ))}
      </svg>
      <div className="chart-legend">
        {populatedSeries.map((item) => {
          const latest = item.values[item.values.length - 1]?.value ?? 0
          return (
            <span className={`chart-legend-item ${item.tone}`} key={item.label}>
              <i aria-hidden="true" />
              {item.label}
              <strong>{formatChartValue(latest, unit)}</strong>
            </span>
          )
        })}
      </div>
    </div>
  )
}

function GpuUsageHeatmap({
  cells,
  rangeDays,
  isError,
  isLoading,
}: {
  cells: HeatmapCell[]
  rangeDays: 7 | 30
  isError: boolean
  isLoading: boolean
}) {
  const hasValues = cells.some((cell) => cell.value !== null)

  if (isError) {
    return <div className="chart-empty">GPU history unavailable</div>
  }

  if (!hasValues) {
    return (
      <div className="chart-empty">
        {isLoading ? 'Loading GPU history' : `Waiting for ${rangeDays} day GPU buckets`}
      </div>
    )
  }

  return (
    <div className={`gpu-heatmap days-${rangeDays}`}>
      <div className="heatmap-hour-axis" aria-hidden="true">
        {Array.from({ length: 24 }, (_, hour) => (
          <span key={hour}>{hour % 3 === 0 ? formatHour(hour) : ''}</span>
        ))}
      </div>
      <div className="heatmap-body">
        {chunkHeatmapRows(cells).map((row) => (
          <div className="heatmap-row" key={row[0]?.dateKey}>
            <span className="heatmap-day-label">{row[0]?.dayLabel}</span>
            <div className="heatmap-cells">
              {row.map((cell) => (
                <span
                  className="heatmap-cell"
                  style={{ backgroundColor: heatmapColor(cell.value) }}
                  title={`${cell.dayLabel} ${formatHour(cell.hour)}: ${
                    cell.value === null ? 'no data' : `${formatPercent(cell.value)} avg GPU`
                  }`}
                  aria-label={`${cell.dayLabel} ${formatHour(cell.hour)} ${
                    cell.value === null ? 'no data' : `${formatPercent(cell.value)} average GPU utilization`
                  }`}
                  key={`${cell.dateKey}-${cell.hour}`}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="heatmap-legend" aria-hidden="true">
        <span>0%</span>
        <span className="heatmap-gradient" />
        <span>100%</span>
      </div>
    </div>
  )
}

function buildMetricCards(
  snapshot: HardwareSnapshot | undefined,
  isError: boolean,
  isLoading: boolean,
): Metric[] {
  if (snapshot) {
    const primaryGpu = snapshot.gpus[0]

    return [
      {
        ...metrics[0],
        value: formatPercent(snapshot.host.cpu_percent),
        detail: [
          `${snapshot.host.cpu_count} cores`,
          formatTemperature(snapshot.host.cpu_temperature_c),
        ]
          .filter(Boolean)
          .join(' · '),
        tone: toneForPercent(snapshot.host.cpu_percent),
        percent: snapshot.host.cpu_percent,
      },
      {
        ...metrics[1],
        value: formatPercent(snapshot.host.memory_percent),
        detail: `${formatNumber(snapshot.host.memory_used_gib)} / ${formatNumber(
          snapshot.host.memory_total_gib,
        )} GiB used`,
        tone: toneForPercent(snapshot.host.memory_percent),
        percent: snapshot.host.memory_percent,
      },
      buildGpuMetric(primaryGpu),
      buildStorageMetric(snapshot.host),
      buildNetworkMetric(snapshot.network),
    ]
  }

  const detail = isError ? 'Telemetry API unavailable' : isLoading ? 'Collecting sample' : 'Waiting'
  return metrics.map((metric) => ({
    ...metric,
    value: isError ? 'n/a' : '...',
    detail,
    tone: isError ? 'danger' : 'neutral',
    percent: 0,
  }))
}

function buildGpuProfileCards(
  profiles: GpuProfileDefinition[] | undefined,
  gpus: GpuSnapshot[] | undefined,
  isError: boolean,
  isLoading: boolean,
): GpuProfile[] {
  if (profiles?.length) {
    return profiles.map((profile) => ({
      name: profile.label,
      power:
        profile.power_limit_watts === null
          ? 'power unchanged'
          : `${profile.power_limit_watts} W limit`,
      clocks: formatGpuProfileClocks(profile),
      state: isGpuProfileActive(profile, gpus) ? 'active' : 'available',
      profileName: profile.name,
      description: profile.description,
    }))
  }

  const detail = isError ? 'Profile API unavailable' : isLoading ? 'Loading /etc profiles' : 'Waiting'
  return gpuProfiles.map((profile) => ({
    ...profile,
    state: 'available',
    clocks: detail,
  }))
}

function isGpuProfileActive(
  profile: GpuProfileDefinition,
  gpus: GpuSnapshot[] | undefined,
): boolean {
  const gpu = gpus?.find((candidate) => candidate.index === profile.gpu_index)
  if (!gpu) {
    return false
  }

  const checks: boolean[] = []
  if (profile.power_limit_watts !== null) {
    checks.push(isClose(gpu.power_limit_w, profile.power_limit_watts, 1))
  }
  if (profile.graphics_clocks_mhz !== null) {
    checks.push(isWithinRange(gpu.clocks_graphics_mhz, profile.graphics_clocks_mhz))
  }
  if (profile.memory_clocks_mhz !== null) {
    checks.push(isWithinRange(gpu.clocks_memory_mhz, profile.memory_clocks_mhz))
  }

  return checks.length > 0 && checks.every(Boolean)
}

function isClose(current: number | null, target: number, tolerance: number): boolean {
  return current !== null && Math.abs(current - target) <= tolerance
}

function isWithinRange(current: number | null, range: { min: number; max: number }): boolean {
  return current !== null && current >= range.min && current <= range.max
}

function formatGpuProfileClocks(profile: GpuProfileDefinition): string {
  const details: string[] = []

  if (profile.reset_graphics_clocks) {
    details.push('default graphics clocks')
  } else if (profile.graphics_clocks_mhz) {
    details.push(
      `${profile.graphics_clocks_mhz.min}-${profile.graphics_clocks_mhz.max} MHz graphics`,
    )
  }

  if (profile.reset_memory_clocks) {
    details.push('default memory clocks')
  } else if (profile.memory_clocks_mhz) {
    details.push(`${profile.memory_clocks_mhz.min}-${profile.memory_clocks_mhz.max} MHz memory`)
  }

  const gpuOffsets = formatClockOffsets(profile.gpu_clock_offsets)
  if (gpuOffsets) {
    details.push(`GPU offset ${gpuOffsets}`)
  }

  const memoryOffsets = formatClockOffsets(profile.mem_clock_offsets)
  if (memoryOffsets) {
    details.push(`memory offset ${memoryOffsets}`)
  }

  return details.length ? details.join(' · ') : 'clocks unchanged'
}

function formatClockOffsets(offsets: Record<string, number> | null): string {
  if (!offsets) {
    return ''
  }

  const entries = Object.entries(offsets).sort(([left], [right]) => Number(left) - Number(right))
  if (!entries.length) {
    return ''
  }

  return entries
    .map(([pstate, offset]) => `P${pstate} ${formatSignedNumber(offset)} MHz`)
    .join(', ')
}

function formatSignedNumber(value: number): string {
  return value > 0 ? `+${value}` : `${value}`
}

function buildStorageMetric(host: HardwareSnapshot['host']): Metric {
  const disks = host.disks.length
    ? host.disks
    : [
        {
          device: '',
          mountpoint: '/',
          filesystem: '',
          percent: host.disk_percent,
          free_gib: host.disk_free_gib,
          total_gib: host.disk_total_gib,
        },
      ]
  const fullestDisk = disks.reduce((fullest, disk) =>
    disk.percent > fullest.percent ? disk : fullest,
  )
  const totalFreeGib = disks.reduce((total, disk) => total + disk.free_gib, 0)

  return {
    ...metrics[3],
    value: formatPercent(fullestDisk.percent),
    detail: `${disks.length} volume${disks.length === 1 ? '' : 's'} · ${formatNumber(
      totalFreeGib,
    )} GiB free`,
    tone: toneForPercent(fullestDisk.percent),
    percent: fullestDisk.percent,
  }
}

function buildGpuMetric(gpu: GpuSnapshot | undefined): Metric {
  if (!gpu) {
    return {
      ...metrics[2],
      value: 'No data',
      detail: 'nvidia-smi unavailable',
      tone: 'neutral',
      percent: 0,
    }
  }

  const utilization = gpu.utilization_gpu_percent
  const memoryUsedGib = gpu.memory_used_mib === null ? null : gpu.memory_used_mib / 1024
  const memoryTotalGib = gpu.memory_total_mib === null ? null : gpu.memory_total_mib / 1024
  const memoryPercent =
    gpu.memory_used_mib !== null && gpu.memory_total_mib !== null && gpu.memory_total_mib > 0
      ? (gpu.memory_used_mib / gpu.memory_total_mib) * 100
      : null
  const vramDetail =
    memoryUsedGib === null || memoryTotalGib === null
      ? 'VRAM unavailable'
      : `${formatNumber(memoryUsedGib)} / ${formatNumber(memoryTotalGib)} GiB VRAM`
  const loadDetail = utilization === null ? 'load n/a' : `${formatPercent(utilization)} load`
  const detail = [
    vramDetail,
    loadDetail,
    formatTemperature(gpu.temperature_c),
    formatPower(gpu.power_draw_w),
  ]
    .filter(Boolean)
    .join(' · ')

  return {
    ...metrics[2],
    value: memoryPercent === null ? 'n/a' : formatPercent(memoryPercent),
    detail,
    tone: memoryPercent === null ? 'neutral' : toneForPercent(memoryPercent),
    percent: memoryPercent ?? 0,
  }
}

function buildNetworkMetric(network: NetworkSnapshot): Metric {
  const trafficDetail = `down ${formatBytesPerSecond(
    network.bytes_recv_per_second,
  )} · up ${formatBytesPerSecond(network.bytes_sent_per_second)}`
  const latencyDetail = network.internet_latency_ms === null ? '' : `${Math.round(
    network.internet_latency_ms,
  )} ms`
  const detailParts = [network.interface_name, trafficDetail, latencyDetail].filter(Boolean)

  return {
    ...metrics[4],
    value: network.internet_reachable ? 'Online' : 'Offline',
    detail: detailParts.join(' · '),
    tone: network.internet_reachable ? 'good' : 'danger',
    percent: network.internet_reachable ? 100 : 0,
  }
}

function selectPrimaryGpuBuckets(buckets: HardwareBucket[]): HardwareBucket[] {
  const gpuBuckets = buckets.filter((bucket) => bucket.scope === 'gpu')
  const primaryDevice = gpuBuckets[0]?.device_key
  if (!primaryDevice) {
    return []
  }
  return gpuBuckets.filter((bucket) => bucket.device_key === primaryDevice)
}

function buildSeries(
  label: string,
  buckets: HardwareBucket[],
  selectValue: (bucket: HardwareBucket) => number | null,
  tone: ChartSeries['tone'],
): ChartSeries {
  return {
    label,
    tone,
    values: buckets
      .map((bucket) => ({ timestamp: bucket.bucket_start, value: selectValue(bucket) }))
      .filter((point): point is ChartPoint => point.value !== null),
  }
}

function buildGpuHeatmapCells(buckets: HardwareBucket[], rangeDays: 7 | 30): HeatmapCell[] {
  const now = new Date()
  const start = new Date(now)
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - (rangeDays - 1))

  const totals = new Map<string, { total: number; weight: number; sampleCount: number }>()
  buckets.forEach((bucket) => {
    if (bucket.gpu_utilization_percent_avg === null) {
      return
    }

    const date = new Date(bucket.bucket_start)
    if (date < start || date > now) {
      return
    }

    const dateKey = formatDateKey(date)
    const key = `${dateKey}-${date.getHours()}`
    const sampleCount = Math.max(bucket.sample_count, 1)
    const current = totals.get(key) ?? { total: 0, weight: 0, sampleCount: 0 }
    totals.set(key, {
      total: current.total + bucket.gpu_utilization_percent_avg * sampleCount,
      weight: current.weight + sampleCount,
      sampleCount: current.sampleCount + bucket.sample_count,
    })
  })

  const cells: HeatmapCell[] = []
  for (let dayOffset = 0; dayOffset < rangeDays; dayOffset += 1) {
    const date = new Date(start)
    date.setDate(start.getDate() + dayOffset)
    const dateKey = formatDateKey(date)
    for (let hour = 0; hour < 24; hour += 1) {
      const aggregate = totals.get(`${dateKey}-${hour}`)
      cells.push({
        dateKey,
        dayLabel: formatHeatmapDay(date, rangeDays),
        hour,
        value: aggregate ? aggregate.total / aggregate.weight : null,
        sampleCount: aggregate?.sampleCount ?? 0,
      })
    }
  }
  return cells
}

function chunkHeatmapRows(cells: HeatmapCell[]): HeatmapCell[][] {
  const rows: HeatmapCell[][] = []
  for (let index = 0; index < cells.length; index += 24) {
    rows.push(cells.slice(index, index + 24))
  }
  return rows
}

function polylinePoints(points: ChartPoint[], maxValue: number): string {
  if (points.length === 1) {
    const y = chartY(points[0].value, maxValue)
    return `0,${y} 640,${y}`
  }

  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 640
      return `${x},${chartY(point.value, maxValue)}`
    })
    .join(' ')
}

function chartY(value: number, maxValue: number): number {
  return 210 - (Math.min(value, maxValue) / maxValue) * 200
}

function findProfileName(profiles: GpuProfile[], profileName: string | undefined): string {
  return profiles.find((profile) => profile.profileName === profileName)?.name ?? 'profile'
}

function toneForPercent(value: number): Metric['tone'] {
  if (value >= 90) {
    return 'danger'
  }
  if (value >= 70) {
    return 'watch'
  }
  return 'good'
}

function formatPercent(value: number): string {
  return `${Math.round(value)}%`
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function formatBytesPerSecond(value: number): string {
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  let scaledValue = value
  let unitIndex = 0

  while (scaledValue >= 1024 && unitIndex < units.length - 1) {
    scaledValue /= 1024
    unitIndex += 1
  }

  const formattedValue =
    scaledValue >= 10 ? Math.round(scaledValue).toString() : formatNumber(scaledValue)
  return `${formattedValue} ${units[unitIndex]}`
}

function formatDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function formatHeatmapDay(date: Date, rangeDays: 7 | 30): string {
  return date.toLocaleDateString(undefined, {
    month: rangeDays === 7 ? 'short' : 'numeric',
    day: 'numeric',
  })
}

function formatHour(hour: number): string {
  if (hour === 0) {
    return '12a'
  }
  if (hour === 12) {
    return '12p'
  }
  return hour < 12 ? `${hour}a` : `${hour - 12}p`
}

function heatmapColor(value: number | null): string {
  if (value === null) {
    return '#ece7dc'
  }

  const clamped = Math.max(0, Math.min(value, 100))
  if (clamped < 20) {
    return '#d8eee5'
  }
  if (clamped < 40) {
    return '#9ddbc8'
  }
  if (clamped < 60) {
    return '#4fb7a4'
  }
  if (clamped < 80) {
    return '#f2b66d'
  }
  return '#d97706'
}

function formatTemperature(value: number | null): string {
  return value === null ? '' : `${Math.round(value)} C`
}

function formatPower(value: number | null): string {
  return value === null ? '' : `${Math.round(value)} W`
}

function formatEnergy(value: number): string {
  if (value < 0.001) {
    return `${formatNumber(value * 1000)} Wh`
  }
  return `${formatNumber(value)} kWh`
}

function formatCurrency(value: number): string {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  })
}

function formatChartValue(value: number, unit: string): string {
  if (unit === '%') {
    return formatPercent(value)
  }
  if (unit === 'W') {
    return formatPower(value)
  }
  return `${formatNumber(value)} ${unit}`
}
