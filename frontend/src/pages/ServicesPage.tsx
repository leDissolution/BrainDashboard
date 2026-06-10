import {
  Activity,
  Circle,
  ExternalLink,
  Gauge,
  Power,
  RadioTower,
  Timer,
} from 'lucide-react'
import {
  services as seededServices,
  type Service,
} from '../data/dashboard'
import type {
  ServiceSnapshot,
  ServiceSnapshotItem,
  VllmMetricsHistoryResponse,
  VllmMetricsSample,
} from '../lib/api'

export type ServiceSections = {
  primary: Service[]
  childGroups: Map<string, Service[]>
  secondary: Service[]
}

type ServicesPageProps = {
  serviceSnapshot: ServiceSnapshot | undefined
  serviceSnapshotIsError: boolean
  serviceSnapshotIsLoading: boolean
  vllmMetrics: VllmMetricsHistoryResponse | undefined
  vllmMetricsIsError: boolean
  vllmMetricsIsLoading: boolean
  isUnloadingLlamaSwap: boolean
  unloadLlamaSwapIsError: boolean
  onUnloadLlamaSwap: () => void
}

type ServiceWatchlistProps = {
  sections: ServiceSections
  isUnloadingLlamaSwap: boolean
  unloadLlamaSwapIsError: boolean
  onUnloadLlamaSwap: () => void
}

type TelemetrySeries = {
  label: string
  tone: 'primary' | 'secondary' | 'power'
  scaleKey?: string
  values: TelemetryPoint[]
}

type TelemetryPoint = {
  timestamp: string
  value: number
}

export function ServicesPage({
  serviceSnapshot,
  serviceSnapshotIsError,
  serviceSnapshotIsLoading,
  vllmMetrics,
  vllmMetricsIsError,
  vllmMetricsIsLoading,
  isUnloadingLlamaSwap,
  unloadLlamaSwapIsError,
  onUnloadLlamaSwap,
}: ServicesPageProps) {
  const sections = buildServiceSections(
    serviceSnapshot,
    serviceSnapshotIsError,
    serviceSnapshotIsLoading,
  )

  return (
    <div className="services-workspace">
      <section className="services-main-grid">
        <div className="services-primary-column">
          <VllmTelemetryPanel
            metrics={vllmMetrics}
            isError={vllmMetricsIsError}
            isLoading={vllmMetricsIsLoading}
          />
        </div>
        <aside className="services-side-column">
          <ServiceWatchlist
            sections={sections}
            isUnloadingLlamaSwap={isUnloadingLlamaSwap}
            unloadLlamaSwapIsError={unloadLlamaSwapIsError}
            onUnloadLlamaSwap={onUnloadLlamaSwap}
          />
        </aside>
      </section>
    </div>
  )
}

export function ServiceWatchlist({
  sections,
  isUnloadingLlamaSwap,
  unloadLlamaSwapIsError,
  onUnloadLlamaSwap,
}: ServiceWatchlistProps) {
  return (
    <div className="surface">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Services</p>
          <h2>Watchlist</h2>
        </div>
      </div>
      <div className="service-list">
        {sections.primary.map((service) => (
          <div className="service-group" key={service.name}>
            <ServiceCard
              service={service}
              isUnloading={isUnloadingLlamaSwap}
              onUnload={
                service.name === 'llama-swap'
                  ? () => {
                      if (window.confirm('Unload all currently running llama-swap models?')) {
                        onUnloadLlamaSwap()
                      }
                    }
                  : undefined
              }
            />
            {sections.childGroups.get(service.name)?.length ? (
              <div className="service-children">
                {sections.childGroups.get(service.name)?.map((childService) => (
                  <ServiceCard service={childService} child key={childService.name} />
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      {unloadLlamaSwapIsError ? <p className="inline-error">llama-swap unload failed.</p> : null}
      {sections.secondary.length > 0 ? (
        <details className="secondary-services">
          <summary>
            <span>Secondary Services</span>
            <span>{sections.secondary.length}</span>
          </summary>
          <div className="service-list secondary">
            {sections.secondary.map((service) => (
              <ServiceCard service={service} key={service.name} />
            ))}
          </div>
        </details>
      ) : null}
    </div>
  )
}

function VllmTelemetryPanel({
  metrics,
  isError,
  isLoading,
}: {
  metrics: VllmMetricsHistoryResponse | undefined
  isError: boolean
  isLoading: boolean
}) {
  const latest = metrics?.latest
  const online = latest?.status === 'online'
  const endpoint = metrics?.endpoint ?? 'waiting for endpoint'
  const samples = metrics?.samples ?? []
  const minuteAverageTg = averageRecentRate(samples, (sample) => sample.generation_tokens_per_second)
  const minuteAverageComputePp = averageRecentRate(
    samples,
    (sample) => sample.prompt_compute_tokens_per_second,
  )
  const minuteAverageTotalPp = averageRecentRate(samples, (sample) => sample.prompt_tokens_per_second)
  const throughputSeries = [
    buildTelemetrySeries(
      'TG tok/s',
      samples,
      (sample) => sample.generation_tokens_per_second,
      'power',
      'tg',
    ),
    buildTelemetrySeries(
      'PP tok/s',
      samples,
      (sample) => sample.prompt_compute_tokens_per_second,
      'primary',
      'pp',
    ),
    buildTelemetrySeries(
      'Requests/min',
      samples,
      (sample) => sample.requests_per_second === null ? null : sample.requests_per_second * 60,
      'secondary',
      'requests',
    ),
  ]
  const latencySeries = [
    buildTelemetrySeries('TTFT p95', samples, (sample) => sample.ttft_seconds_p95, 'primary'),
    buildTelemetrySeries(
      'E2E p95',
      samples,
      (sample) => sample.e2e_latency_seconds_p95,
      'power',
    ),
    buildTelemetrySeries('Queue p95', samples, (sample) => sample.queue_seconds_p95, 'secondary'),
  ]
  const schedulerSeries = [
    buildTelemetrySeries('Running', samples, (sample) => sample.running_requests, 'primary'),
    buildTelemetrySeries('Waiting', samples, (sample) => sample.waiting_requests, 'power'),
    buildTelemetrySeries(
      'KV cache',
      samples,
      (sample) => sample.kv_cache_usage_percent,
      'secondary',
    ),
    buildTelemetrySeries(
      'Prefix hit',
      samples,
      (sample) => sample.prefix_cache_hit_percent,
      'primary',
    ),
  ]

  return (
    <div className="surface inference-surface">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Inference</p>
          <h2>vLLM Metrics</h2>
        </div>
        <span className={`telemetry-status ${online ? 'online' : 'offline'}`}>
          {isError ? 'api unavailable' : latest?.status ?? (isLoading ? 'loading' : 'waiting')}
        </span>
      </div>

      <div className="telemetry-endpoint" title={endpoint}>
        <RadioTower size={15} />
        <span>{endpoint}</span>
      </div>

      <div className="inference-summary-grid">
        <TelemetryStat
          label="Running"
          value={formatCount(latest?.running_requests)}
          detail="active batches"
          icon={Activity}
        />
        <TelemetryStat
          label="Waiting"
          value={formatCount(latest?.waiting_requests)}
          detail="queued requests"
          icon={Timer}
        />
        <TelemetryStat
          label="KV Cache"
          value={formatPercent(latest?.kv_cache_usage_percent)}
          detail="highest reported usage"
          icon={Gauge}
        />
        <TelemetryStat
          label="Cache Hit"
          value={formatPercent(latest?.prefix_cache_hit_percent)}
          detail="recent prefix hits"
          icon={Gauge}
        />
        <TelemetryStat
          label="TG avg"
          value={formatRate(minuteAverageTg, 'tok/s')}
          detail="last minute"
          icon={Activity}
        />
        <TelemetryStat
          label="Compute PP"
          value={formatRate(minuteAverageComputePp, 'tok/s')}
          detail="last minute"
          icon={Activity}
        />
        <TelemetryStat
          label="Total PP"
          value={formatRate(minuteAverageTotalPp, 'tok/s')}
          detail="last minute incl cache"
          icon={Activity}
        />
      </div>

      <div className="telemetry-model-strip">
        <span>
          <strong>{latest?.model_names.length ? latest.model_names.join(', ') : 'No model labels'}</strong>
          <small>{formatPromptCacheDetail(latest, isLoading)}</small>
        </span>
        <span>
          <strong>{samples.length}</strong>
          <small>in-memory samples</small>
        </span>
      </div>

      <section className="telemetry-chart-grid">
        <TelemetryChart title="Throughput" unit="" series={throughputSeries} />
        <TelemetryChart title="Latency" unit="s" series={latencySeries} />
        <TelemetryChart title="Scheduler And Cache" unit="" series={schedulerSeries} maxValue={100} />
      </section>
    </div>
  )
}

function TelemetryStat({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string
  value: string
  detail: string
  icon: typeof Activity
}) {
  return (
    <article className="telemetry-stat-card">
      <div>
        <Icon size={17} />
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}

function TelemetryChart({
  title,
  unit,
  series,
  maxValue,
}: {
  title: string
  unit: string
  series: TelemetrySeries[]
  maxValue?: number
}) {
  const populatedSeries = series.filter((item) => item.values.length > 0)
  const allValues = populatedSeries.flatMap((item) => item.values.map((point) => point.value))
  const highestValue = maxValue ?? Math.max(...allValues, 1)
  const scaleMaxByKey = buildScaleMaxByKey(populatedSeries, highestValue, maxValue !== undefined)

  return (
    <article className="telemetry-chart-card">
      <div className="telemetry-chart-heading">
        <strong>{title}</strong>
        <span>{allValues.length ? `${allValues.length} points` : 'waiting'}</span>
      </div>
      {allValues.length ? (
        <div className="telemetry-line-chart">
          <svg viewBox="0 0 640 180" role="img" aria-label={`${title} chart`}>
            <g className="chart-grid" aria-hidden="true">
              {[0, 1, 2, 3].map((line) => (
                <line key={line} x1="0" x2="640" y1={line * 45} y2={line * 45} />
              ))}
            </g>
            {populatedSeries.map((item) => (
              <polyline
                key={item.label}
                className={`chart-line ${item.tone}`}
                points={telemetryPolylinePoints(
                  item.values,
                  scaleMaxByKey.get(item.scaleKey ?? item.label) ?? highestValue,
                )}
              />
            ))}
          </svg>
        </div>
      ) : (
        <div className="telemetry-chart-empty">Waiting for samples</div>
      )}
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
    </article>
  )
}

function ServiceCard({
  service,
  child = false,
  isUnloading = false,
  onUnload,
}: {
  service: Service
  child?: boolean
  isUnloading?: boolean
  onUnload?: () => void
}) {
  const className = `service-card ${child ? 'child' : ''} ${service.isActive === false ? 'inactive' : ''}`
  const content = (
    <>
      <div>
        <span className="service-name">
          {service.name}
          {service.href ? <ExternalLink size={13} aria-hidden="true" /> : null}
        </span>
        <span className="detail">{service.detail}</span>
      </div>
      <div className="service-meta">
        <span className={`service-status ${service.status}`}>
          <Circle size={10} fill="currentColor" />
          {service.isActive === false ? 'idle' : service.status}
        </span>
        <span>{service.latency}</span>
        {onUnload ? (
          <button
            type="button"
            className="mini-button danger service-action-button"
            title="Unload llama-swap models"
            aria-label="Unload llama-swap models"
            disabled={isUnloading}
            onClick={onUnload}
          >
            <Power size={15} />
          </button>
        ) : null}
      </div>
    </>
  )

  if (service.href) {
    return (
      <a className={className} href={service.href} target="_blank" rel="noreferrer">
        {content}
      </a>
    )
  }

  return <article className={className}>{content}</article>
}

export function buildServiceSections(
  snapshot: ServiceSnapshot | undefined,
  isError: boolean,
  isLoading: boolean,
): ServiceSections {
  if (!snapshot) {
    const detail = isError ? 'Service API unavailable' : isLoading ? 'Polling' : 'Waiting'
    return splitServiceSections(seededServices.map((service) => ({
      ...service,
      status: isPrimaryService(service.name) ? 'degraded' : service.status,
      detail: isPrimaryService(service.name) ? detail : service.detail,
      latency: isPrimaryService(service.name) ? 'n/a' : service.latency,
    })))
  }

  const liveServices = snapshot.services.map(buildServiceCard)
  const liveServiceNames = new Set(liveServices.map((service) => service.name))
  const remainingSeededServices = seededServices.filter(
    (service) => !liveServiceNames.has(service.name),
  )

  return splitServiceSections([...liveServices, ...remainingSeededServices])
}

function buildTelemetrySeries(
  label: string,
  samples: VllmMetricsSample[],
  selectValue: (sample: VllmMetricsSample) => number | null,
  tone: TelemetrySeries['tone'],
  scaleKey = label,
): TelemetrySeries {
  return {
    label,
    tone,
    scaleKey,
    values: samples
      .filter((sample) => sample.status === 'online')
      .map((sample) => ({ timestamp: sample.timestamp, value: selectValue(sample) }))
      .filter((point): point is TelemetryPoint => point.value !== null),
  }
}

function buildScaleMaxByKey(
  series: TelemetrySeries[],
  fallbackMax: number,
  useSharedMax: boolean,
): Map<string, number> {
  const scaleMaxByKey = new Map<string, number>()
  for (const item of series) {
    const key = item.scaleKey ?? item.label
    const seriesMax = Math.max(...item.values.map((point) => point.value), 1)
    scaleMaxByKey.set(
      key,
      useSharedMax ? fallbackMax : Math.max(scaleMaxByKey.get(key) ?? 1, seriesMax),
    )
  }
  if (scaleMaxByKey.size === 0) {
    scaleMaxByKey.set('default', fallbackMax)
  }
  return scaleMaxByKey
}

function splitServiceSections(services: Service[]): ServiceSections {
  const childServices = services.filter((service) => service.parentName)
  const childGroups = new Map<string, Service[]>()
  for (const service of childServices) {
    const parentName = service.parentName
    if (!parentName) {
      continue
    }
    childGroups.set(parentName, [...(childGroups.get(parentName) ?? []), service])
  }

  return {
    primary: services.filter((service) => isPrimaryService(service.name) && !service.parentName),
    childGroups,
    secondary: services.filter((service) => !isPrimaryService(service.name) && !service.parentName),
  }
}

function isPrimaryService(name: string): boolean {
  return ['llama-swap', 'vLLM', 'llama.cpp', 'Docker'].includes(name)
}

function buildServiceCard(service: ServiceSnapshotItem): Service {
  return {
    name: service.name,
    status: service.status,
    detail: service.detail,
    latency: formatServiceLatency(service),
    parentName: service.parent_name ?? undefined,
    isActive: service.is_active ?? undefined,
    href: service.name === 'Docker' ? 'https://brainsrv-dockge.lan.homeautomations.info' : undefined,
  }
}

function telemetryPolylinePoints(points: TelemetryPoint[], maxValue: number): string {
  if (points.length === 1) {
    const y = telemetryChartY(points[0].value, maxValue)
    return `0,${y} 640,${y}`
  }

  return points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 640
      return `${x},${telemetryChartY(point.value, maxValue)}`
    })
    .join(' ')
}

function telemetryChartY(value: number, maxValue: number): number {
  return 170 - (Math.min(value, maxValue) / maxValue) * 160
}

function formatServiceLatency(service: ServiceSnapshotItem): string {
  if (service.recent_average_duration_ms !== null) {
    return `${formatDuration(service.recent_average_duration_ms / 1000)} avg`
  }

  if (service.latency_ms !== null) {
    return `${Math.round(service.latency_ms)} ms`
  }

  if (service.recent_request_count !== null) {
    return `${service.recent_request_count} req`
  }

  return 'idle'
}

function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'n/a'
  }
  return Math.round(value).toLocaleString()
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'n/a'
  }
  return `${Math.round(value)}%`
}

function formatRate(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) {
    return 'n/a'
  }
  return `${formatNumber(value)} ${unit}`
}

function averageRecentRate(
  samples: VllmMetricsSample[],
  selectValue: (sample: VllmMetricsSample) => number | null,
  windowMs = 60_000,
): number | null {
  const latestOnlineSample = [...samples].reverse().find((sample) => sample.status === 'online')
  if (!latestOnlineSample) {
    return null
  }

  const endTime = new Date(latestOnlineSample.timestamp).getTime()
  const startTime = endTime - windowMs
  const values = samples
    .filter((sample) => sample.status === 'online')
    .filter((sample) => {
      const timestamp = new Date(sample.timestamp).getTime()
      return timestamp >= startTime && timestamp <= endTime
    })
    .map(selectValue)
    .filter((value): value is number => value !== null)

  if (!values.length) {
    return null
  }

  return values.reduce((total, value) => total + value, 0) / values.length
}

function formatChartValue(value: number, unit: string): string {
  if (unit === 's') {
    return formatDuration(value)
  }
  return formatNumber(value)
}

function formatPromptCacheDetail(
  latest: VllmMetricsSample | null | undefined,
  isLoading: boolean,
): string {
  if (!latest) {
    return isLoading ? 'Collecting metrics' : 'No vLLM samples yet'
  }

  const details = [latest.detail]
  if (latest.prompt_tokens_per_second !== null) {
    details.push(`total PP ${formatNumber(latest.prompt_tokens_per_second)} tok/s`)
  }
  if (latest.prompt_cached_tokens_per_second !== null) {
    details.push(`cached ${formatNumber(latest.prompt_cached_tokens_per_second)} tok/s`)
  }
  return details.join(' · ')
}

function formatDuration(value: number): string {
  if (value >= 1) {
    return `${formatNumber(value)} s`
  }
  return `${Math.round(value * 1000)} ms`
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}
