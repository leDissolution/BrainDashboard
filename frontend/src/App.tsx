import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import './App.css'
import {
  brandIcon as BrandIcon,
  inventory,
  navItems,
  topActions,
} from './data/dashboard'
import {
  applyGpuProfile,
  cancelJobRun,
  fetchJobDefinitions,
  fetchGpuProfiles,
  fetchHardwareHistory,
  fetchHardwareSnapshot,
  fetchHealth,
  fetchJobRuns,
  fetchServiceSnapshot,
  fetchVllmMetricsHistory,
  queueJobDefinition,
  unloadLlamaSwapModels,
  type JobDefinition,
  type JobParameterValue,
} from './lib/api'
import { HardwarePage, HardwareSummaryGrid } from './pages/HardwarePage'
import {
  buildInitialQueueParameterValues,
  CompactJobRunList,
  JobRunRow,
  JobsPage,
  QueueJobDialog,
} from './pages/JobsPage'
import {
  buildDisplayJobRuns,
  buildSchedulerLanes,
  isActiveDisplayRun,
  recentFinishedJobRuns,
} from './pages/jobRunDisplay'
import { buildServiceSections, ServicesPage, ServiceWatchlist } from './pages/ServicesPage'

function App() {
  const queryClient = useQueryClient()
  const [activeView, setActiveView] = useState('Overview')
  const [queueDefinitionId, setQueueDefinitionId] = useState<string | null>(null)
  const [queueParameterValues, setQueueParameterValues] = useState<Record<string, JobParameterValue>>({})
  const [queuePriority, setQueuePriority] = useState<JobDefinition['default_priority']>('normal')
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 15_000,
    retry: 1,
  })
  const hardware = useQuery({
    queryKey: ['hardware', 'snapshot'],
    queryFn: fetchHardwareSnapshot,
    refetchInterval: 3_000,
    retry: 1,
  })
  const hardwareHistory = useQuery({
    queryKey: ['hardware', 'history', 6],
    queryFn: () => fetchHardwareHistory(6),
    refetchInterval: 60_000,
    retry: 1,
  })
  const hardwareHeatmapHistory = useQuery({
    queryKey: ['hardware', 'history', 'gpu', 30, hardware.data?.gpus[0]?.index],
    queryFn: () =>
      fetchHardwareHistory(24 * 30, {
        scope: 'gpu',
        deviceKey: `gpu:${hardware.data?.gpus[0]?.index ?? 0}`,
        limit: 50_000,
      }),
    enabled: activeView === 'Hardware' && Boolean(hardware.data?.gpus.length),
    refetchInterval: 5 * 60_000,
    retry: 1,
  })
  const serviceSnapshot = useQuery({
    queryKey: ['services', 'snapshot'],
    queryFn: fetchServiceSnapshot,
    refetchInterval: 10_000,
    retry: 1,
  })
  const vllmMetricsSnapshot = useQuery({
    queryKey: ['services', 'vllm', 'metrics'],
    queryFn: fetchVllmMetricsHistory,
    refetchInterval: activeView === 'Services' ? 5_000 : 15_000,
    retry: 1,
  })
  const gpuProfileSnapshot = useQuery({
    queryKey: ['gpu', 'profiles'],
    queryFn: fetchGpuProfiles,
    refetchInterval: 30_000,
    retry: 1,
  })
  const jobDefinitionSnapshot = useQuery({
    queryKey: ['jobs', 'definitions'],
    queryFn: fetchJobDefinitions,
    refetchInterval: 30_000,
    retry: 1,
    enabled: activeView !== 'Jobs',
  })
  const jobRunSnapshot = useQuery({
    queryKey: ['jobs', 'runs'],
    queryFn: () => fetchJobRuns(25),
    refetchInterval: 3_000,
    retry: 1,
  })
  const gpuProfileApply = useMutation({
    mutationFn: applyGpuProfile,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['hardware', 'snapshot'] })
      void queryClient.invalidateQueries({ queryKey: ['gpu', 'profiles'] })
    },
  })
  const cancelJobRunMutation = useMutation({
    mutationFn: cancelJobRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'runs'] })
    },
  })
  const queueJobMutation = useMutation({
    mutationFn: queueJobDefinition,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'runs'] })
    },
  })
  const unloadLlamaSwapMutation = useMutation({
    mutationFn: unloadLlamaSwapModels,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['services', 'snapshot'] })
    },
  })
  const apiStatus = health.data?.status === 'ok' ? 'online' : health.isError ? 'offline' : 'checking'
  const serviceSections = buildServiceSections(
    serviceSnapshot.data,
    serviceSnapshot.isError,
    serviceSnapshot.isLoading,
  )
  const allJobRuns = buildDisplayJobRuns(jobRunSnapshot.data?.runs ?? [])
  const schedulerLanes = buildSchedulerLanes(
    jobRunSnapshot.data?.runs ?? [],
    jobRunSnapshot.isLoading,
    jobRunSnapshot.isError,
  )
  const displayedJobRuns = allJobRuns.filter((run) =>
    isActiveDisplayRun(run.status),
  )
  const recentJobRuns = recentFinishedJobRuns(allJobRuns)
  const jobDefinitions = jobDefinitionSnapshot.data?.definitions ?? []
  const queueDefinition = jobDefinitions.find((definition) => definition.id === queueDefinitionId) ?? null
  const openQueueDialogFromRun = (run: (typeof allJobRuns)[number]) => {
    const definition = jobDefinitions.find((candidate) => candidate.id === run.definitionId)
    if (!definition) {
      window.alert(`Job definition "${run.definitionId}" is not loaded, so this run cannot be copied.`)
      return
    }

    setQueueDefinitionId(definition.id)
    setQueuePriority(run.restartPriority)
    setQueueParameterValues(buildInitialQueueParameterValues(definition, run.restartParameters))
  }
  const closeQueueDialog = () => {
    if (!queueJobMutation.isPending) {
      setQueueDefinitionId(null)
      setQueueParameterValues({})
    }
  }
  const submitQueue = async () => {
    if (queueDefinition === null) {
      return
    }

    await queueJobMutation.mutateAsync({
      definitionId: queueDefinition.id,
      request: {
        parameters: queueParameterValues,
        priority: queuePriority,
      },
    })
    setQueueDefinitionId(null)
    setQueueParameterValues({})
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary">
        <a className="brand" href="/" aria-label="BrainDashboard overview">
          <span className="brand-mark">
            <BrandIcon size={22} strokeWidth={2.2} />
          </span>
          <span className="brand-text">BrainDashboard</span>
        </a>

        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.label}
              className={`nav-item ${item.label === activeView ? 'active' : ''}`}
              type="button"
              title={item.label}
              onClick={() => setActiveView(item.label)}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className={`status-dot ${apiStatus}`} aria-hidden="true" />
          <span>API {apiStatus}</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Homelab ML Server</p>
            <h1>{activeView === 'Overview' ? 'Operations' : activeView}</h1>
          </div>
          <div className="top-actions" aria-label="Dashboard actions">
            {topActions.map((action) => (
              <button key={action.label} type="button" className="icon-button" title={action.label}>
                <action.icon size={18} />
              </button>
            ))}
          </div>
        </header>

        {activeView === 'Jobs' ? (
          <JobsPage />
        ) : activeView === 'Hardware' ? (
          <HardwarePage
            snapshot={hardware.data}
            snapshotIsError={hardware.isError}
            snapshotIsLoading={hardware.isLoading}
            history={hardwareHistory.data}
            historyIsError={hardwareHistory.isError}
            historyIsLoading={hardwareHistory.isLoading}
            heatmapHistory={hardwareHeatmapHistory.data}
            heatmapHistoryIsError={hardwareHeatmapHistory.isError}
            heatmapHistoryIsLoading={hardwareHeatmapHistory.isLoading}
            profiles={gpuProfileSnapshot.data?.profiles}
            profilesIsError={gpuProfileSnapshot.isError}
            profilesIsLoading={gpuProfileSnapshot.isLoading}
            isApplyingProfile={gpuProfileApply.isPending}
            applyProfileError={gpuProfileApply.isError}
            applyProfileWarning={gpuProfileApply.data?.warnings[0]}
            applyingProfileName={gpuProfileApply.variables}
            onApplyProfile={(profileName) => gpuProfileApply.mutate(profileName)}
          />
        ) : activeView === 'Services' ? (
          <ServicesPage
            serviceSnapshot={serviceSnapshot.data}
            serviceSnapshotIsError={serviceSnapshot.isError}
            serviceSnapshotIsLoading={serviceSnapshot.isLoading}
            vllmMetrics={vllmMetricsSnapshot.data}
            vllmMetricsIsError={vllmMetricsSnapshot.isError}
            vllmMetricsIsLoading={vllmMetricsSnapshot.isLoading}
            isUnloadingLlamaSwap={unloadLlamaSwapMutation.isPending}
            unloadLlamaSwapIsError={unloadLlamaSwapMutation.isError}
            onUnloadLlamaSwap={() => unloadLlamaSwapMutation.mutate()}
          />
        ) : (
          <>
            <HardwareSummaryGrid
              snapshot={hardware.data}
              snapshotIsError={hardware.isError}
              snapshotIsLoading={hardware.isLoading}
              profiles={gpuProfileSnapshot.data?.profiles}
              profilesIsError={gpuProfileSnapshot.isError}
              profilesIsLoading={gpuProfileSnapshot.isLoading}
              isApplyingProfile={gpuProfileApply.isPending}
              applyProfileError={gpuProfileApply.isError}
              applyProfileWarning={gpuProfileApply.data?.warnings[0]}
              applyingProfileName={gpuProfileApply.variables}
              onApplyProfile={(profileName) => gpuProfileApply.mutate(profileName)}
            />

            <section className="dashboard-grid">
              <div className="dashboard-column">
                <div className="surface">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Queue</p>
                      <h2>Active Runs</h2>
                    </div>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setActiveView('Jobs')}
                    >
                      Open jobs
                      <ChevronRight size={16} />
                    </button>
                  </div>

                  <div className="job-table" role="table" aria-label="Job runs">
                    <div className="job-row heading" role="row">
                      <span>Job</span>
                      <span>State</span>
                      <span>Priority</span>
                      <span>Resource</span>
                      <span>ETA</span>
                      <span>Control</span>
                    </div>
                    {displayedJobRuns.length ? (
                      displayedJobRuns.map((job) => (
                        <JobRunRow
                          job={job}
                          isCanceling={cancelJobRunMutation.isPending}
                          isRestarting={queueJobMutation.isPending}
                          onCancel={(runId) => cancelJobRunMutation.mutate(runId)}
                          onRestart={openQueueDialogFromRun}
                          showRestart
                          key={job.id}
                        />
                      ))
                    ) : (
                      <div className="job-row empty" role="row">
                        <span className="job-name">
                          {jobRunSnapshot.isError
                            ? 'Job runs unavailable'
                            : jobRunSnapshot.isLoading
                              ? 'Loading runs'
                              : 'No queued or recent runs'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <details className="surface recent-jobs-panel">
                  <summary>
                    <span>
                      <span className="eyebrow">History</span>
                      <strong>Recent Jobs</strong>
                    </span>
                    <span>{recentJobRuns.length} in 12h</span>
                  </summary>
                  <CompactJobRunList
                    runs={recentJobRuns}
                    isLoading={jobRunSnapshot.isLoading}
                    isError={jobRunSnapshot.isError}
                    isCanceling={false}
                    isRestarting={queueJobMutation.isPending}
                    onCancel={(runId) => cancelJobRunMutation.mutate(runId)}
                    onRestart={openQueueDialogFromRun}
                    showCancel={false}
                    showRestart
                    emptyLabel="No recent jobs"
                    emptyDetail="Finished, failed, and canceled runs from the last 12 hours will appear here."
                  />
                </details>

                <div className="surface">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Scheduler</p>
                      <h2>Admission State</h2>
                    </div>
                  </div>
                  <div className="lane-grid">
                    {schedulerLanes.map((lane) => (
                      <article className="lane-card" key={lane.name}>
                        <span>{lane.name}</span>
                        <strong>{lane.value}</strong>
                        <small>{lane.detail}</small>
                      </article>
                    ))}
                  </div>
                </div>
              </div>

              <div className="dashboard-column service-column">
                <ServiceWatchlist
                  sections={serviceSections}
                  isUnloadingLlamaSwap={unloadLlamaSwapMutation.isPending}
                  unloadLlamaSwapIsError={unloadLlamaSwapMutation.isError}
                  onUnloadLlamaSwap={() => unloadLlamaSwapMutation.mutate()}
                />

                <div className="surface inventory-surface">
                  <div className="section-heading">
                    <div>
                      <p className="eyebrow">Stack</p>
                      <h2>Server Shape</h2>
                    </div>
                  </div>
                  <div className="inventory-grid">
                    {inventory.map((item) => (
                      <article className="inventory-card" key={item.label}>
                        <item.icon size={17} />
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </article>
                    ))}
                  </div>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
      {activeView !== 'Jobs' && queueDefinition ? (
        <QueueJobDialog
          definition={queueDefinition}
          values={queueParameterValues}
          priority={queuePriority}
          isQueueing={queueJobMutation.isPending}
          queueError={queueJobMutation.isError}
          onValueChange={(parameterName, value) =>
            setQueueParameterValues((currentValues) => ({
              ...currentValues,
              [parameterName]: value,
            }))
          }
          onPriorityChange={setQueuePriority}
          onClose={closeQueueDialog}
          onSubmit={submitQueue}
        />
      ) : null}
    </div>
  )
}

export default App
