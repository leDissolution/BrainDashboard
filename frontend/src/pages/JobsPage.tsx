import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ChevronRight, Copy, Play, Plus, Save, Square, Trash2, X } from 'lucide-react'
import type { JobSubjob } from '../data/dashboard'
import {
  cancelJobRun,
  createJobDefinition,
  deleteJobDefinition,
  fetchJobDefinitions,
  fetchJobRun,
  fetchJobRuns,
  queueJobDefinition,
  updateJobDefinition as updateJobDefinitionRequest,
  type JobDefinition,
  type JobParameter,
  type JobParameterValue,
  type JobQueueRequest,
  type JobResourceHints,
} from '../lib/api'
import {
  buildDisplayJobRun,
  buildDisplayJobRuns,
  isActiveDisplayRun,
  recentFinishedJobRuns,
  type DisplayJobRun,
} from './jobRunDisplay'

export function JobsPage() {
  const queryClient = useQueryClient()
  const [editedJobDefinitions, setEditedJobDefinitions] = useState<JobDefinition[] | null>(null)
  const [jobDefinitionCommandInputs, setJobDefinitionCommandInputs] = useState<Record<string, string>>({})
  const jobDefinitionSnapshot = useQuery({
    queryKey: ['jobs', 'definitions'],
    queryFn: fetchJobDefinitions,
    refetchInterval: 30_000,
    retry: 1,
  })
  const jobRunSnapshot = useQuery({
    queryKey: ['jobs', 'runs'],
    queryFn: () => fetchJobRuns(25, { includeSubjobs: true }),
    refetchInterval: 3_000,
    retry: 1,
  })
  const jobDefinitions = editedJobDefinitions ?? jobDefinitionSnapshot.data?.definitions ?? []
  const allJobRuns = buildDisplayJobRuns(jobRunSnapshot.data?.runs ?? [])
  const displayedJobRuns = allJobRuns.filter((run) => isActiveDisplayRun(run.status))
  const recentJobRuns = recentFinishedJobRuns(allJobRuns)
  const persistedJobDefinitionIds = new Set(
    jobDefinitionSnapshot.data?.definitions.map((definition) => definition.id) ?? [],
  )
  const saveJobDefinitions = useMutation({
    mutationFn: async (definitions: JobDefinition[]) => {
      const persistedIds = new Set(
        jobDefinitionSnapshot.data?.definitions.map((definition) => definition.id) ?? [],
      )
      return Promise.all(
        definitions.map((definition) =>
          persistedIds.has(definition.id)
            ? updateJobDefinitionRequest(definition)
            : createJobDefinition(definition),
        ),
      )
    },
    onSuccess: (definitions) => {
      queryClient.setQueryData(['jobs', 'definitions'], { definitions })
      setEditedJobDefinitions(null)
      setJobDefinitionCommandInputs({})
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'definitions'] })
    },
  })
  const deleteJobDefinitionMutation = useMutation({
    mutationFn: async ({
      definitionId,
      isPersisted,
    }: {
      definitionId: string
      isPersisted: boolean
    }) => {
      if (isPersisted) {
        await deleteJobDefinition(definitionId)
      }
      return definitionId
    },
    onSuccess: (definitionId) => {
      setEditedJobDefinitions((currentDefinitions) =>
        currentDefinitions?.filter((definition) => definition.id !== definitionId) ?? null,
      )
      queryClient.setQueryData(
        ['jobs', 'definitions'],
        (currentData: { definitions: JobDefinition[] } | undefined) => ({
          definitions: currentData?.definitions.filter((definition) => definition.id !== definitionId) ?? [],
        }),
      )
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'definitions'] })
    },
  })
  const queueJobMutation = useMutation({
    mutationFn: queueJobDefinition,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'runs'] })
    },
  })
  const cancelJobRunMutation = useMutation({
    mutationFn: cancelJobRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['jobs', 'runs'] })
    },
  })

  const updateJobDefinition = (definitionId: string, changes: Partial<JobDefinition>) => {
    setEditedJobDefinitions((currentDefinitions) =>
      (currentDefinitions ?? jobDefinitions).map((definition) =>
        definition.id === definitionId ? { ...definition, ...changes } : definition,
      ),
    )
  }

  const updateJobDefinitionCommand = (definitionId: string, commandText: string) => {
    setJobDefinitionCommandInputs((currentInputs) => ({
      ...currentInputs,
      [definitionId]: commandText,
    }))
    updateJobDefinition(definitionId, { command: parseCommandInput(commandText) })
  }

  const updateJobParameter = (
    definitionId: string,
    parameterIndex: number,
    changes: Partial<JobParameter>,
  ) => {
    setEditedJobDefinitions((currentDefinitions) =>
      (currentDefinitions ?? jobDefinitions).map((definition) =>
        definition.id === definitionId
          ? {
              ...definition,
              parameters: definition.parameters.map((parameter, index) =>
                index === parameterIndex ? { ...parameter, ...changes } : parameter,
              ),
            }
          : definition,
      ),
    )
  }

  const addJobParameter = (definitionId: string) => {
    setEditedJobDefinitions((currentDefinitions) =>
      (currentDefinitions ?? jobDefinitions).map((definition) =>
        definition.id === definitionId
          ? {
              ...definition,
              parameters: [
                ...definition.parameters,
                buildDraftJobParameter(definition.parameters.length + 1),
              ],
            }
          : definition,
      ),
    )
  }

  const deleteJobParameter = (definitionId: string, parameterIndex: number) => {
    setEditedJobDefinitions((currentDefinitions) =>
      (currentDefinitions ?? jobDefinitions).map((definition) =>
        definition.id === definitionId
          ? {
              ...definition,
              parameters: definition.parameters.filter((_, index) => index !== parameterIndex),
            }
          : definition,
      ),
    )
  }

  const resetEditableJobDefinitions = () => {
    setEditedJobDefinitions(null)
    setJobDefinitionCommandInputs({})
  }

  const createEditableJobDefinition = (defaults?: Partial<JobDefinition>): JobDefinition => {
    const draftDefinition = buildDraftJobDefinition(jobDefinitions.length + 1, defaults)
    setEditedJobDefinitions((currentDefinitions) => [
      ...(currentDefinitions ?? jobDefinitions),
      draftDefinition,
    ])
    setJobDefinitionCommandInputs((currentInputs) => ({
      ...currentInputs,
      [draftDefinition.id]: formatCommandInput(draftDefinition.command),
    }))
    return draftDefinition
  }

  const cloneEditableJobDefinition = (definition: JobDefinition): JobDefinition => {
    const clonedDefinition = buildClonedJobDefinition(definition, jobDefinitions)
    setEditedJobDefinitions((currentDefinitions) => [
      ...(currentDefinitions ?? jobDefinitions),
      clonedDefinition,
    ])
    setJobDefinitionCommandInputs((currentInputs) => ({
      ...currentInputs,
      [clonedDefinition.id]: formatCommandInput(clonedDefinition.command),
    }))
    return clonedDefinition
  }

  const deleteEditableJobDefinition = (definitionId: string) => {
    setJobDefinitionCommandInputs((currentInputs) => {
      const nextInputs = { ...currentInputs }
      delete nextInputs[definitionId]
      return nextInputs
    })
    deleteJobDefinitionMutation.mutate({
      definitionId,
      isPersisted: persistedJobDefinitionIds.has(definitionId),
    })
  }

  return (
    <JobsWorkspace
      definitions={jobDefinitions}
      isDirty={editedJobDefinitions !== null}
      isLoading={jobDefinitionSnapshot.isLoading}
      isError={jobDefinitionSnapshot.isError}
      isSaving={saveJobDefinitions.isPending}
      isDeleting={deleteJobDefinitionMutation.isPending}
      actionError={saveJobDefinitions.isError || deleteJobDefinitionMutation.isError}
      persistedDefinitionIds={persistedJobDefinitionIds}
      commandInputs={jobDefinitionCommandInputs}
      onCreate={createEditableJobDefinition}
      onClone={cloneEditableJobDefinition}
      onDelete={deleteEditableJobDefinition}
      onDefinitionChange={updateJobDefinition}
      onDefinitionCommandChange={updateJobDefinitionCommand}
      onParameterChange={updateJobParameter}
      onParameterCreate={addJobParameter}
      onParameterDelete={deleteJobParameter}
      onReset={resetEditableJobDefinitions}
      onSave={() => saveJobDefinitions.mutate(jobDefinitions)}
      runs={displayedJobRuns}
      recentRuns={recentJobRuns}
      runsLoading={jobRunSnapshot.isLoading}
      runsError={jobRunSnapshot.isError}
      isQueueing={queueJobMutation.isPending}
      queueError={queueJobMutation.isError}
      onQueue={(definitionId, request) => queueJobMutation.mutateAsync({ definitionId, request })}
      isCanceling={cancelJobRunMutation.isPending}
      onCancelRun={(runId) => cancelJobRunMutation.mutate(runId)}
    />
  )
}

function JobsWorkspace({
  definitions,
  isDirty,
  isLoading,
  isError,
  isSaving,
  isDeleting,
  actionError,
  persistedDefinitionIds,
  commandInputs,
  onCreate,
  onClone,
  onDelete,
  onDefinitionChange,
  onDefinitionCommandChange,
  onParameterChange,
  onParameterCreate,
  onParameterDelete,
  onReset,
  onSave,
  runs,
  recentRuns,
  runsLoading,
  runsError,
  isQueueing,
  queueError,
  onQueue,
  isCanceling,
  onCancelRun,
}: {
  definitions: JobDefinition[]
  isDirty: boolean
  isLoading: boolean
  isError: boolean
  isSaving: boolean
  isDeleting: boolean
  actionError: boolean
  persistedDefinitionIds: Set<string>
  commandInputs: Record<string, string>
  onCreate: (defaults?: Partial<JobDefinition>) => JobDefinition
  onClone: (definition: JobDefinition) => JobDefinition
  onDelete: (definitionId: string) => void
  onDefinitionChange: (definitionId: string, changes: Partial<JobDefinition>) => void
  onDefinitionCommandChange: (definitionId: string, commandText: string) => void
  onParameterChange: (
    definitionId: string,
    parameterIndex: number,
    changes: Partial<JobParameter>,
  ) => void
  onParameterCreate: (definitionId: string) => void
  onParameterDelete: (definitionId: string, parameterIndex: number) => void
  onReset: () => void
  onSave: () => void
  runs: DisplayJobRun[]
  recentRuns: DisplayJobRun[]
  runsLoading: boolean
  runsError: boolean
  isQueueing: boolean
  queueError: boolean
  onQueue: (definitionId: string, request: JobQueueRequest) => Promise<unknown>
  isCanceling: boolean
  onCancelRun: (runId: string) => void
}) {
  const [expandedDefinitionIds, setExpandedDefinitionIds] = useState<Set<string>>(new Set())
  const [expandedGroupIds, setExpandedGroupIds] = useState<Set<string>>(new Set())
  const [queueDefinitionId, setQueueDefinitionId] = useState<string | null>(null)
  const [queueParameterValues, setQueueParameterValues] = useState<Record<string, JobParameterValue>>({})
  const [queuePriority, setQueuePriority] = useState<JobDefinition['default_priority']>('normal')
  const enabledCount = definitions.filter((definition) => definition.enabled).length
  const definitionGroups = buildJobDefinitionGroups(definitions)
  const queueDefinition = definitions.find((definition) => definition.id === queueDefinitionId) ?? null
  const toggleGroup = (groupId: string) => {
    setExpandedGroupIds((currentIds) => {
      const nextIds = new Set(currentIds)
      if (nextIds.has(groupId)) {
        nextIds.delete(groupId)
      } else {
        nextIds.add(groupId)
      }
      return nextIds
    })
  }
  const toggleDefinition = (definitionId: string) => {
    setExpandedDefinitionIds((currentIds) => {
      const nextIds = new Set(currentIds)
      if (nextIds.has(definitionId)) {
        nextIds.delete(definitionId)
      } else {
        nextIds.add(definitionId)
      }
      return nextIds
    })
  }
  const createDefinition = () => {
    const definition = onCreate()
    setExpandedDefinitionIds((currentIds) => new Set(currentIds).add(definition.id))
    setExpandedGroupIds((currentIds) =>
      new Set(currentIds).add(buildDefinitionGroupId(buildJobGroupSettings(definition))),
    )
  }
  const createDefinitionInGroup = (group: JobDefinitionGroup) => {
    const definition = onCreate(buildDefinitionDefaultsFromGroup(group.settings))
    setExpandedDefinitionIds((currentIds) => new Set(currentIds).add(definition.id))
    setExpandedGroupIds((currentIds) => new Set(currentIds).add(group.id))
  }
  const cloneDefinition = (definition: JobDefinition) => {
    const clonedDefinition = onClone(definition)
    setExpandedDefinitionIds((currentIds) => new Set(currentIds).add(clonedDefinition.id))
    setExpandedGroupIds((currentIds) =>
      new Set(currentIds).add(buildDefinitionGroupId(buildJobGroupSettings(clonedDefinition))),
    )
  }
  const deleteDefinition = (definitionId: string) => {
    const definition = definitions.find((candidate) => candidate.id === definitionId)
    const confirmed = window.confirm(
      `Delete job definition "${definition?.name ?? definitionId}"? This cannot be undone.`,
    )
    if (!confirmed) {
      return
    }

    onDelete(definitionId)
    setExpandedDefinitionIds((currentIds) => {
      const nextIds = new Set(currentIds)
      nextIds.delete(definitionId)
      return nextIds
    })
  }
  const openQueueDialog = (definition: JobDefinition) => {
    setQueueDefinitionId(definition.id)
    setQueuePriority(definition.default_priority)
    setQueueParameterValues(buildInitialQueueParameterValues(definition))
  }
  const openQueueDialogFromRun = (run: DisplayJobRun) => {
    const definition = definitions.find((candidate) => candidate.id === run.definitionId)
    if (!definition) {
      window.alert(`Job definition "${run.definitionId}" is not loaded, so this run cannot be copied.`)
      return
    }

    setQueueDefinitionId(definition.id)
    setQueuePriority(run.restartPriority)
    setQueueParameterValues(buildInitialQueueParameterValues(definition, run.restartParameters))
  }
  const closeQueueDialog = () => {
    if (!isQueueing) {
      setQueueDefinitionId(null)
      setQueueParameterValues({})
    }
  }
  const submitQueue = async () => {
    if (queueDefinition === null) {
      return
    }
    await onQueue(queueDefinition.id, {
      parameters: buildQueueParameters(queueDefinition, queueParameterValues),
      priority: queuePriority,
    })
    setQueueDefinitionId(null)
    setQueueParameterValues({})
  }

  return (
    <section className="jobs-workspace" aria-label="Jobs workspace">
      <div className="jobs-grid">
        <div className="surface jobs-main-surface">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Definitions</p>
              <h2>Job Catalog</h2>
            </div>
            <span className="definition-count">
              {isError
                ? 'API unavailable'
                : isLoading
                  ? 'Loading'
                  : `${enabledCount} enabled / ${definitions.length} total${isDirty ? ' / edited' : ''}`}
            </span>
          </div>
          <div className="definition-actions">
            <button type="button" className="text-button" onClick={createDefinition}>
              <Plus size={16} />
              New definition
            </button>
            {isDirty ? (
              <button type="button" className="text-button" onClick={onReset} disabled={isSaving}>
                Reset edits
              </button>
            ) : null}
            <button
              type="button"
              className="text-button primary"
              onClick={onSave}
              disabled={!isDirty || isSaving || isDeleting}
            >
              <Save size={16} />
              {isSaving ? 'Saving' : 'Save changes'}
            </button>
          </div>
          {actionError ? (
            <p className="definition-action-error">Job definition write failed. Check the API logs.</p>
          ) : null}

          <div className="definition-list">
            {definitionGroups.length ? (
              definitionGroups.map((group) => {
                if (group.definitions.length === 1) {
                  const definition = group.definitions[0]
                  return (
                    <JobDefinitionCard
                      definition={definition}
                      isExpanded={expandedDefinitionIds.has(definition.id)}
                      onToggle={() => toggleDefinition(definition.id)}
                      onDefinitionChange={(changes) => onDefinitionChange(definition.id, changes)}
                      commandInput={commandInputs[definition.id] ?? formatCommandInput(definition.command)}
                      onCommandChange={(commandText) =>
                        onDefinitionCommandChange(definition.id, commandText)
                      }
                      onParameterChange={(parameterIndex, changes) =>
                        onParameterChange(definition.id, parameterIndex, changes)
                      }
                      onParameterCreate={() => onParameterCreate(definition.id)}
                      onParameterDelete={(parameterIndex) =>
                        onParameterDelete(definition.id, parameterIndex)
                      }
                      onQueue={() => openQueueDialog(definition)}
                      onClone={() => cloneDefinition(definition)}
                      onDelete={() => deleteDefinition(definition.id)}
                      isDeleting={isDeleting}
                      isDirty={isDirty}
                      isPersisted={persistedDefinitionIds.has(definition.id)}
                      key={definition.id}
                    />
                  )
                }

                return (
                  <JobDefinitionGroupPanel
                    group={group}
                    expandedDefinitionIds={expandedDefinitionIds}
                    isExpanded={expandedGroupIds.has(group.id)}
                    persistedDefinitionIds={persistedDefinitionIds}
                    commandInputs={commandInputs}
                    isDeleting={isDeleting}
                    isDirty={isDirty}
                    onToggle={() => toggleGroup(group.id)}
                    onCreate={() => createDefinitionInGroup(group)}
                    onDefinitionToggle={toggleDefinition}
                    onDefinitionChange={onDefinitionChange}
                    onDefinitionCommandChange={onDefinitionCommandChange}
                    onParameterChange={onParameterChange}
                    onParameterCreate={onParameterCreate}
                    onParameterDelete={onParameterDelete}
                    onQueue={openQueueDialog}
                    onClone={cloneDefinition}
                    onDelete={deleteDefinition}
                    key={group.id}
                  />
                )
              })
            ) : (
              <article className="definition-card empty">
                <strong>{isError ? 'Job definitions unavailable' : 'No job definitions yet'}</strong>
                <span className="detail">
                  {isError ? 'Check the backend API logs.' : 'Definitions will appear here once loaded.'}
                </span>
              </article>
            )}
          </div>
        </div>

        <div className="jobs-side-column">
          <div className="surface">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Queue</p>
                <h2>Active Runs</h2>
              </div>
            </div>
            <CompactJobRunList
              runs={runs}
              isLoading={runsLoading}
              isError={runsError}
              isCanceling={isCanceling}
              isRestarting={isQueueing}
              onCancel={onCancelRun}
              onRestart={openQueueDialogFromRun}
              showRestart
            />
          </div>

          <details className="surface recent-jobs-panel">
            <summary>
              <span>
                <span className="eyebrow">History</span>
                <strong>Recent Jobs</strong>
              </span>
              <span>{recentRuns.length} in 12h</span>
            </summary>
            <CompactJobRunList
              runs={recentRuns}
              isLoading={runsLoading}
              isError={runsError}
              isCanceling={false}
              isRestarting={isQueueing}
              onCancel={onCancelRun}
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
                <p className="eyebrow">Contract</p>
                <h2>Structured Events</h2>
              </div>
            </div>
            <div className="contract-panel">
              <span className="pill">BD_EVENT</span>
              <p>Controlled jobs emit JSON lines through stdout or stderr.</p>
              <small>BRAINDASHBOARD_RUN_ID / BRAINDASHBOARD_EVENT_PREFIX</small>
            </div>
          </div>
        </div>
      </div>
      {queueDefinition ? (
        <QueueJobDialog
          definition={queueDefinition}
          values={queueParameterValues}
          priority={queuePriority}
          isQueueing={isQueueing}
          queueError={queueError}
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
    </section>
  )
}

function buildDraftJobDefinition(
  position: number,
  defaults: Partial<JobDefinition> = {},
): JobDefinition {
  const suffix = Date.now().toString(36)
  return {
    id: `job-definition-${suffix}`,
    name: `New job definition ${position}`,
    description: 'Draft job definition.',
    enabled: false,
    execution_mode: defaults.execution_mode ?? 'native',
    command: defaults.command ? [...defaults.command] : ['/opt/BrainDashboard/jobs/new-job.sh'],
    working_directory: defaults.working_directory ?? null,
    image: defaults.image ?? null,
    default_priority: defaults.default_priority ?? 'normal',
    timeout_seconds: defaults.timeout_seconds ?? null,
    event_contract: defaults.event_contract ?? 'structured_stdout',
    resource_hints: defaults.resource_hints
      ? { ...defaults.resource_hints }
      : {
          gpu_count: 1,
          min_vram_gib: null,
          exclusive_gpu: false,
          docker_required: false,
        },
    retry_policy: defaults.retry_policy
      ? { ...defaults.retry_policy }
      : {
          max_attempts: 1,
          backoff_seconds: 0,
        },
    parameters: [],
  }
}

function buildClonedJobDefinition(
  definition: JobDefinition,
  existingDefinitions: JobDefinition[],
): JobDefinition {
  return {
    ...definition,
    id: buildClonedJobDefinitionId(definition.id, existingDefinitions),
    name: buildClonedJobDefinitionName(definition.name, existingDefinitions),
    enabled: false,
    command: [...definition.command],
    resource_hints: { ...definition.resource_hints },
    retry_policy: { ...definition.retry_policy },
    parameters: definition.parameters.map((parameter) => ({
      ...parameter,
      choices: [...parameter.choices],
    })),
  }
}

function buildClonedJobDefinitionId(sourceId: string, existingDefinitions: JobDefinition[]): string {
  const suffix = Date.now().toString(36)
  const baseId = `${sourceId.slice(0, 92)}-copy-${suffix}`
  const existingIds = new Set(existingDefinitions.map((definition) => definition.id))
  if (!existingIds.has(baseId)) {
    return baseId
  }
  return `job-definition-${suffix}`
}

function buildClonedJobDefinitionName(
  sourceName: string,
  existingDefinitions: JobDefinition[],
): string {
  const baseName = `${sourceName} copy`
  const existingNames = new Set(existingDefinitions.map((definition) => definition.name))
  if (!existingNames.has(baseName)) {
    return baseName
  }

  let copyNumber = 2
  let candidateName = `${baseName} ${copyNumber}`
  while (existingNames.has(candidateName)) {
    copyNumber += 1
    candidateName = `${baseName} ${copyNumber}`
  }
  return candidateName
}

function buildDraftJobParameter(position: number): JobParameter {
  return {
    name: `parameter_${position}`,
    label: `Parameter ${position}`,
    description: '',
    value_type: 'string',
    cli_flag: `--parameter-${position}`,
    default_value: null,
    required_at_queue: false,
    allow_queue_override: true,
    choices: [],
  }
}

type JobGroupSettings = Pick<
  JobDefinition,
  | 'execution_mode'
  | 'command'
  | 'working_directory'
  | 'image'
  | 'default_priority'
  | 'timeout_seconds'
  | 'event_contract'
  | 'resource_hints'
  | 'retry_policy'
>

type JobDefinitionGroup = {
  id: string
  title: string
  description: string
  settings: JobGroupSettings
  definitions: JobDefinition[]
  enabledCount: number
}

function JobDefinitionGroupPanel({
  group,
  expandedDefinitionIds,
  isExpanded,
  persistedDefinitionIds,
  commandInputs,
  isDeleting,
  isDirty,
  onToggle,
  onCreate,
  onDefinitionToggle,
  onDefinitionChange,
  onDefinitionCommandChange,
  onParameterChange,
  onParameterCreate,
  onParameterDelete,
  onQueue,
  onClone,
  onDelete,
}: {
  group: JobDefinitionGroup
  expandedDefinitionIds: Set<string>
  isExpanded: boolean
  persistedDefinitionIds: Set<string>
  commandInputs: Record<string, string>
  isDeleting: boolean
  isDirty: boolean
  onToggle: () => void
  onCreate: () => void
  onDefinitionToggle: (definitionId: string) => void
  onDefinitionChange: (definitionId: string, changes: Partial<JobDefinition>) => void
  onDefinitionCommandChange: (definitionId: string, commandText: string) => void
  onParameterChange: (
    definitionId: string,
    parameterIndex: number,
    changes: Partial<JobParameter>,
  ) => void
  onParameterCreate: (definitionId: string) => void
  onParameterDelete: (definitionId: string, parameterIndex: number) => void
  onQueue: (definition: JobDefinition) => void
  onClone: (definition: JobDefinition) => void
  onDelete: (definitionId: string) => void
}) {
  const previewDefinitions = group.definitions.slice(0, 4)
  const overflowCount = group.definitions.length - previewDefinitions.length

  return (
    <section className="definition-group" aria-label={`${group.title} job group`}>
      <div className="definition-group-heading">
        <button
          type="button"
          className="definition-group-toggle"
          onClick={onToggle}
          aria-expanded={isExpanded}
        >
          <ChevronRight className={isExpanded ? 'expanded-chevron' : ''} size={18} />
          <span>
            <strong>{group.title}</strong>
            <span className="detail">{group.description}</span>
          </span>
        </button>
        <div className="definition-group-actions">
          <span className="pill enabled">
            {group.enabledCount} / {group.definitions.length} enabled
          </span>
          <button type="button" className="text-button" onClick={onCreate}>
            <Plus size={16} />
            New in group
          </button>
        </div>
      </div>
      <div className="definition-group-meta-grid">
        <DefinitionMeta label="Mode" value={formatExecutionMode(group.settings.execution_mode)} />
        <DefinitionMeta label="Priority" value={group.settings.default_priority} />
        <DefinitionMeta
          label="Working Dir"
          value={group.settings.working_directory ?? 'service default'}
        />
        <DefinitionMeta label="Resources" value={formatResourceHints(group.settings.resource_hints)} />
        <DefinitionMeta label="Timeout" value={formatTimeout(group.settings.timeout_seconds)} />
      </div>
      <div className="definition-command compact">
        <span>{group.settings.image ?? group.settings.working_directory ?? 'host'}</span>
        <code>{formatCommandInput(group.settings.command)}</code>
      </div>
      {isExpanded ? (
        <div className="definition-group-list">
          {group.definitions.map((definition) => (
            <JobDefinitionCard
              definition={definition}
              isGrouped
              isExpanded={expandedDefinitionIds.has(definition.id)}
              onToggle={() => onDefinitionToggle(definition.id)}
              onDefinitionChange={(changes) => onDefinitionChange(definition.id, changes)}
              commandInput={commandInputs[definition.id] ?? formatCommandInput(definition.command)}
              onCommandChange={(commandText) =>
                onDefinitionCommandChange(definition.id, commandText)
              }
              onParameterChange={(parameterIndex, changes) =>
                onParameterChange(definition.id, parameterIndex, changes)
              }
              onParameterCreate={() => onParameterCreate(definition.id)}
              onParameterDelete={(parameterIndex) => onParameterDelete(definition.id, parameterIndex)}
              onQueue={() => onQueue(definition)}
              onClone={() => onClone(definition)}
              onDelete={() => onDelete(definition.id)}
              isDeleting={isDeleting}
              isDirty={isDirty}
              isPersisted={persistedDefinitionIds.has(definition.id)}
              key={definition.id}
            />
          ))}
        </div>
      ) : (
        <div className="definition-group-preview" aria-label="Collapsed job definitions">
          {previewDefinitions.map((definition) => (
            <span className="definition-preview-item" key={definition.id}>
              {definition.name}
            </span>
          ))}
          {overflowCount > 0 ? (
            <span className="definition-preview-item muted">+{overflowCount} more</span>
          ) : null}
        </div>
      )}
    </section>
  )
}

function JobDefinitionCard({
  definition,
  isGrouped = false,
  isExpanded,
  onToggle,
  onDefinitionChange,
  commandInput,
  onCommandChange,
  onParameterChange,
  onParameterCreate,
  onParameterDelete,
  onQueue,
  onClone,
  onDelete,
  isDeleting,
  isDirty,
  isPersisted,
}: {
  definition: JobDefinition
  isGrouped?: boolean
  isExpanded: boolean
  onToggle: () => void
  onDefinitionChange: (changes: Partial<JobDefinition>) => void
  commandInput: string
  onCommandChange: (commandText: string) => void
  onParameterChange: (parameterIndex: number, changes: Partial<JobParameter>) => void
  onParameterCreate: () => void
  onParameterDelete: (parameterIndex: number) => void
  onQueue: () => void
  onClone: () => void
  onDelete: () => void
  isDeleting: boolean
  isDirty: boolean
  isPersisted: boolean
}) {
  const requiredParameters = definition.parameters.filter((parameter) => parameter.required_at_queue)
  const defaultedParameters = definition.parameters.filter(
    (parameter) => !parameter.required_at_queue && parameter.default_value !== null,
  )
  const canQueue = definition.enabled && definition.execution_mode === 'native' && isPersisted && !isDirty

  return (
    <article className={`definition-card ${definition.enabled ? 'enabled' : 'disabled'}`}>
      <div className="definition-title-row">
        <div>
          <strong>{definition.name}</strong>
          <span className="detail">{definition.description}</span>
        </div>
        <div className="definition-card-actions">
          <span className={`pill ${definition.enabled ? 'enabled' : 'disabled'}`}>
            {definition.enabled ? 'enabled' : 'disabled'}
          </span>
          <button
            type="button"
            className="mini-button"
            title={canQueue ? 'Queue job' : 'Queue unavailable'}
            onClick={onQueue}
            disabled={!canQueue}
          >
            <Play size={14} />
          </button>
          <button type="button" className="mini-button" title="Clone definition" onClick={onClone}>
            <Copy size={14} />
          </button>
          <button type="button" className="text-button" onClick={onToggle}>
            {isExpanded ? 'Collapse' : 'Edit'}
            <ChevronRight className={isExpanded ? 'expanded-chevron' : ''} size={16} />
          </button>
          <button
            type="button"
            className="mini-button danger"
            title={isPersisted ? 'Delete definition' : 'Discard draft'}
            onClick={onDelete}
            disabled={isDeleting}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {isGrouped ? null : (
        <div className="definition-meta-grid">
          <DefinitionMeta label="Mode" value={formatExecutionMode(definition.execution_mode)} />
          <DefinitionMeta label="Priority" value={definition.default_priority} />
          <DefinitionMeta label="Working Dir" value={definition.working_directory ?? 'service default'} />
          <DefinitionMeta label="Resources" value={formatResourceHints(definition.resource_hints)} />
          <DefinitionMeta label="Timeout" value={formatTimeout(definition.timeout_seconds)} />
        </div>
      )}
      {isExpanded ? (
        <>
          <JobDefinitionEditor
            definition={definition}
            commandInput={commandInput}
            onChange={onDefinitionChange}
            onCommandChange={onCommandChange}
          />
          {isGrouped ? null : (
            <div className="definition-command">
              <span>{definition.image ?? definition.working_directory ?? 'host'}</span>
              <code>{formatCommandInput(definition.command)}</code>
            </div>
          )}
          <JobParameterList
            parameters={definition.parameters}
            onParameterChange={onParameterChange}
            onParameterCreate={onParameterCreate}
            onParameterDelete={onParameterDelete}
          />
        </>
      ) : null}
      <div className="definition-footer">
        <span>{definition.event_contract === 'structured_stdout' ? 'BD_EVENT enabled' : 'logs only'}</span>
        <span>
          {requiredParameters.length} required / {defaultedParameters.length} default
          {defaultedParameters.length === 1 ? '' : 's'}
        </span>
        <span>
          {definition.retry_policy.max_attempts} attempt
          {definition.retry_policy.max_attempts === 1 ? '' : 's'}
        </span>
      </div>
    </article>
  )
}

function JobDefinitionEditor({
  definition,
  commandInput,
  onChange,
  onCommandChange,
}: {
  definition: JobDefinition
  commandInput: string
  onChange: (changes: Partial<JobDefinition>) => void
  onCommandChange: (commandText: string) => void
}) {
  return (
    <div className="definition-editor-grid">
      <label className="field-control">
        <span>Name</span>
        <input
          type="text"
          value={definition.name}
          onChange={(event) => onChange({ name: event.target.value })}
        />
      </label>
      <label className="field-control wide">
        <span>Description</span>
        <input
          type="text"
          value={definition.description}
          onChange={(event) => onChange({ description: event.target.value })}
        />
      </label>
      <label className="field-control">
        <span>Priority</span>
        <select
          value={definition.default_priority}
          onChange={(event) =>
            onChange({ default_priority: event.target.value as JobDefinition['default_priority'] })
          }
        >
          <option value="low">low</option>
          <option value="normal">normal</option>
          <option value="high">high</option>
        </select>
      </label>
      <label className="field-control">
        <span>Timeout seconds</span>
        <input
          type="number"
          min="0"
          value={definition.timeout_seconds ?? ''}
          onChange={(event) => onChange({ timeout_seconds: parseOptionalInteger(event.target.value) })}
        />
      </label>
      <label className="field-control wide">
        <span>Command</span>
        <textarea value={commandInput} onChange={(event) => onCommandChange(event.target.value)} />
      </label>
      <label className="field-control wide">
        <span>Working directory</span>
        <input
          type="text"
          value={definition.working_directory ?? ''}
          placeholder="service default"
          onChange={(event) =>
            onChange({ working_directory: parseOptionalString(event.target.value) })
          }
        />
      </label>
      <label className="field-toggle">
        <input
          type="checkbox"
          checked={definition.enabled}
          onChange={(event) => onChange({ enabled: event.target.checked })}
        />
        <span>Enabled</span>
      </label>
    </div>
  )
}

function JobParameterList({
  parameters,
  onParameterChange,
  onParameterCreate,
  onParameterDelete,
}: {
  parameters: JobParameter[]
  onParameterChange: (parameterIndex: number, changes: Partial<JobParameter>) => void
  onParameterCreate: () => void
  onParameterDelete: (parameterIndex: number) => void
}) {
  return (
    <div className="parameter-list" aria-label="Queue parameters">
      <div className="parameter-list-heading">
        <strong>Queue parameters</strong>
        <button type="button" className="text-button" onClick={onParameterCreate}>
          <Plus size={16} />
          Add parameter
        </button>
      </div>
      {parameters.length ? (
        parameters.map((parameter, parameterIndex) => (
          <article
            className={`parameter-card ${parameter.required_at_queue ? 'required' : 'defaulted'}`}
            key={parameterIndex}
          >
            <div className="parameter-fields">
              <label className="field-control">
                <span>Name</span>
                <input
                  type="text"
                  value={parameter.name}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { name: event.target.value })
                  }
                />
              </label>
              <label className="field-control">
                <span>Label</span>
                <input
                  type="text"
                  value={parameter.label}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { label: event.target.value })
                  }
                />
              </label>
              <label className="field-control wide">
                <span>Description</span>
                <input
                  type="text"
                  value={parameter.description}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { description: event.target.value })
                  }
                />
              </label>
            </div>
            <div className="parameter-fields compact">
              <label className="field-control">
                <span>CLI flag</span>
                <input
                  type="text"
                  value={parameter.cli_flag}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { cli_flag: event.target.value })
                  }
                />
              </label>
              <label className="field-control">
                <span>Type</span>
                <select
                  value={parameter.value_type}
                  onChange={(event) => {
                    const valueType = event.target.value as JobParameter['value_type']
                    onParameterChange(parameterIndex, {
                      value_type: valueType,
                      default_value: parseParameterValue(
                        formatParameterInputValue(parameter.default_value),
                        valueType,
                      ),
                    })
                  }}
                >
                  <option value="string">string</option>
                  <option value="integer">integer</option>
                  <option value="float">float</option>
                  <option value="boolean">boolean</option>
                  <option value="path">path</option>
                  <option value="choice">choice</option>
                  <option value="flag">flag</option>
                </select>
              </label>
              <label className="field-control">
                <span>Default</span>
                <ParameterDefaultInput
                  parameter={parameter}
                  onChange={(defaultValue) =>
                    onParameterChange(parameterIndex, { default_value: defaultValue })
                  }
                />
              </label>
              <label className="field-control">
                <span>Choices</span>
                <input
                  type="text"
                  disabled={parameter.value_type !== 'choice'}
                  value={parameter.choices.join(', ')}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { choices: splitChoices(event.target.value) })
                  }
                />
              </label>
            </div>
            <div className="parameter-controls">
              <span className={`pill ${parameter.required_at_queue ? 'required' : 'defaulted'}`}>
                {parameter.required_at_queue ? 'required at queue' : 'default override'}
              </span>
              <label className="parameter-required-toggle">
                <input
                  type="checkbox"
                  checked={parameter.required_at_queue}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { required_at_queue: event.target.checked })
                  }
                />
                <span>Required</span>
              </label>
              <label className="parameter-required-toggle">
                <input
                  type="checkbox"
                  checked={parameter.allow_queue_override}
                  onChange={(event) =>
                    onParameterChange(parameterIndex, { allow_queue_override: event.target.checked })
                  }
                />
                <span>Queue override</span>
              </label>
              <button
                type="button"
                className="mini-button danger"
                title="Delete parameter"
                onClick={() => onParameterDelete(parameterIndex)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          </article>
        ))
      ) : (
        <article className="parameter-card empty">
          <strong>No queue parameters</strong>
          <span className="detail">Add parameters for values collected before launch.</span>
        </article>
      )}
    </div>
  )
}

function ParameterDefaultInput({
  parameter,
  onChange,
}: {
  parameter: JobParameter
  onChange: (value: JobParameterValue) => void
}) {
  if (parameter.value_type === 'boolean' || parameter.value_type === 'flag') {
    return (
      <select
        value={formatParameterInputValue(parameter.default_value)}
        disabled={parameter.required_at_queue || !parameter.allow_queue_override}
        onChange={(event) => onChange(parseParameterValue(event.target.value, parameter.value_type))}
      >
        <option value="">none</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    )
  }

  return (
    <input
      type={parameter.value_type === 'integer' || parameter.value_type === 'float' ? 'number' : 'text'}
      disabled={parameter.required_at_queue || !parameter.allow_queue_override}
      value={parameter.required_at_queue ? '' : formatParameterInputValue(parameter.default_value)}
      placeholder={parameter.required_at_queue ? 'must specify' : 'none'}
      onChange={(event) => onChange(parseParameterValue(event.target.value, parameter.value_type))}
    />
  )
}

export function QueueJobDialog({
  definition,
  values,
  priority,
  isQueueing,
  queueError,
  onValueChange,
  onPriorityChange,
  onClose,
  onSubmit,
}: {
  definition: JobDefinition
  values: Record<string, JobParameterValue>
  priority: JobDefinition['default_priority']
  isQueueing: boolean
  queueError: boolean
  onValueChange: (parameterName: string, value: JobParameterValue) => void
  onPriorityChange: (priority: JobDefinition['default_priority']) => void
  onClose: () => void
  onSubmit: () => Promise<void>
}) {
  const queueParameters = definition.parameters.filter(
    (parameter) => parameter.required_at_queue || parameter.allow_queue_override,
  )

  return (
    <div className="modal-backdrop" role="presentation">
      <form
        className="queue-modal"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit()
        }}
      >
        <div className="queue-modal-heading">
          <div>
            <p className="eyebrow">Queue</p>
            <h2>{definition.name}</h2>
          </div>
          <button type="button" className="mini-button" title="Close" onClick={onClose}>
            <X size={14} />
          </button>
        </div>

        <label className="field-control">
          <span>Priority</span>
          <select
            value={priority}
            onChange={(event) =>
              onPriorityChange(event.target.value as JobDefinition['default_priority'])
            }
          >
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
          </select>
        </label>

        <div className="queue-parameter-list">
          {queueParameters.length ? (
            queueParameters.map((parameter) => (
              <label className="field-control" key={parameter.name}>
                <span>{parameter.label}</span>
                <QueueParameterInput
                  parameter={parameter}
                  value={values[parameter.name] ?? null}
                  onChange={(value) => onValueChange(parameter.name, value)}
                />
                {parameter.description ? <small>{parameter.description}</small> : null}
              </label>
            ))
          ) : (
            <article className="parameter-card empty">
              <strong>No queue parameters</strong>
              <span className="detail">This run will use the saved command.</span>
            </article>
          )}
        </div>

        {queueError ? <p className="definition-action-error">Queue request failed.</p> : null}

        <div className="queue-modal-actions">
          <button type="button" className="text-button" onClick={onClose} disabled={isQueueing}>
            Cancel
          </button>
          <button type="submit" className="text-button primary" disabled={isQueueing}>
            <Play size={16} />
            {isQueueing ? 'Queueing' : 'Queue run'}
          </button>
        </div>
      </form>
    </div>
  )
}

function QueueParameterInput({
  parameter,
  value,
  onChange,
}: {
  parameter: JobParameter
  value: JobParameterValue
  onChange: (value: JobParameterValue) => void
}) {
  if (parameter.value_type === 'boolean' || parameter.value_type === 'flag') {
    return (
      <select
        value={formatParameterInputValue(value)}
        required={parameter.required_at_queue}
        onChange={(event) => onChange(parseParameterValue(event.target.value, parameter.value_type))}
      >
        <option value="">none</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    )
  }

  if (parameter.value_type === 'choice') {
    return (
      <select
        value={formatParameterInputValue(value)}
        required={parameter.required_at_queue}
        onChange={(event) => onChange(parseParameterValue(event.target.value, parameter.value_type))}
      >
        <option value="">none</option>
        {parameter.choices.map((choice) => (
          <option value={choice} key={choice}>
            {choice}
          </option>
        ))}
      </select>
    )
  }

  return (
    <input
      type={parameter.value_type === 'integer' || parameter.value_type === 'float' ? 'number' : 'text'}
      value={formatParameterInputValue(value)}
      required={parameter.required_at_queue}
      onChange={(event) => onChange(parseParameterValue(event.target.value, parameter.value_type))}
    />
  )
}

function DefinitionMeta({ label, value }: { label: string; value: string }) {
  return (
    <span className="definition-meta">
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  )
}

export function CompactJobRunList({
  runs,
  isLoading,
  isError,
  isCanceling,
  isRestarting = false,
  onCancel,
  onRestart,
  showCancel = true,
  showRestart = false,
  emptyLabel,
  emptyDetail,
}: {
  runs: DisplayJobRun[]
  isLoading: boolean
  isError: boolean
  isCanceling: boolean
  isRestarting?: boolean
  onCancel: (runId: string) => void
  onRestart?: (run: DisplayJobRun) => void
  showCancel?: boolean
  showRestart?: boolean
  emptyLabel?: string
  emptyDetail?: string
}) {
  return (
    <div className="compact-run-list">
      {runs.length ? (
        runs.map((job) => {
          const hasCopyAction = showRestart && job.canRestart
          const actionClassNames = [
            showCancel || hasCopyAction ? 'with-action' : '',
            showCancel && hasCopyAction ? 'with-two-actions' : '',
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <article className={`compact-run-card ${actionClassNames}`} key={job.id}>
              <div>
                <strong>{job.name}</strong>
                <span className="detail job-resource" title={job.resource}>
                  {job.resource}
                </span>
              </div>
              <span className={`pill ${job.status}`}>{job.status}</span>
              {showCancel ? (
                <button
                  type="button"
                  className="mini-button danger compact-cancel-button"
                  title="Cancel run"
                  onClick={() => onCancel(job.id)}
                  disabled={!job.canCancel || isCanceling}
                >
                  <Square size={14} />
                </button>
              ) : null}
              {showRestart && job.canRestart ? (
                <button
                  type="button"
                  className="mini-button compact-run-action-button"
                  title="Copy run"
                  onClick={() => onRestart?.(job)}
                  disabled={isRestarting}
                >
                  <Copy size={14} />
                </button>
              ) : null}
              <div className="progress-track run-progress-track" aria-hidden="true">
                <span style={{ width: `${job.progress}%` }} />
              </div>
              <RunDetailsDisclosure run={job} compact />
              {job.subjobCount ? <SubjobDisclosure job={job} compact /> : null}
            </article>
          )
        })
      ) : (
        <article className="compact-run-card empty">
          <div>
            <strong>
              {isError ? 'Runs unavailable' : isLoading ? 'Loading runs' : emptyLabel ?? 'No queued runs'}
            </strong>
            <span className="detail">{emptyDetail ?? 'Scheduler state will appear here.'}</span>
          </div>
        </article>
      )}
    </div>
  )
}

export function JobRunRow({
  job,
  isCanceling,
  isRestarting = false,
  onCancel,
  onRestart,
  showRestart = false,
}: {
  job: DisplayJobRun
  isCanceling: boolean
  isRestarting?: boolean
  onCancel: (runId: string) => void
  onRestart?: (run: DisplayJobRun) => void
  showRestart?: boolean
}) {
  return (
    <div className="job-row" role="row">
      <span className="job-name">{job.name}</span>
      <span className={`pill ${job.status}`}>{job.status}</span>
      <span>{job.priority}</span>
      <span className="job-resource" title={job.resource}>
        {job.resource}
      </span>
      <span>{job.eta}</span>
      <span className="row-actions">
        <button
          type="button"
          className="mini-button danger"
          title="Cancel run"
          onClick={() => onCancel(job.id)}
          disabled={!job.canCancel || isCanceling}
        >
          <Square size={14} />
        </button>
        {showRestart && job.canRestart ? (
          <button
            type="button"
            className="mini-button"
            title="Copy run"
            onClick={() => onRestart?.(job)}
            disabled={isRestarting}
          >
            <Copy size={14} />
          </button>
        ) : null}
      </span>
      <span className="progress-track run-progress-track" aria-hidden="true">
        <span style={{ width: `${job.progress}%` }} />
      </span>
      <RunDetailsDisclosure run={job} />
      {job.subjobCount ? <SubjobDisclosure job={job} /> : null}
    </div>
  )
}

function RunDetailsDisclosure({
  run,
  compact = false,
}: {
  run: DisplayJobRun
  compact?: boolean
}) {
  const parameters = Object.entries(run.parameters)

  return (
    <details className={`run-detail-block ${compact ? 'compact' : ''}`}>
      <summary>
        <span>Run details</span>
        <span>{parameters.length} parameter{parameters.length === 1 ? '' : 's'}</span>
      </summary>
      <div className="run-detail-panel">
        <div className="run-detail-meta">
          <span>
            <small>Queued</small>
            <strong>{formatRunTimestamp(run.queuedAt)}</strong>
          </span>
          <span>
            <small>Started</small>
            <strong>{run.startedAt ? formatRunTimestamp(run.startedAt) : 'not started'}</strong>
          </span>
          <span>
            <small>Finished</small>
            <strong>{run.finishedAt ? formatRunTimestamp(run.finishedAt) : 'not finished'}</strong>
          </span>
        </div>
        {parameters.length ? (
          <div className="run-parameter-grid" aria-label="Run parameters">
            {parameters.map(([name, value]) => (
              <span className="run-parameter" key={name}>
                <small>{name}</small>
                <code>{formatRunParameterValue(value)}</code>
              </span>
            ))}
          </div>
        ) : (
          <p className="run-detail-empty">No parameters were supplied for this run.</p>
        )}
      </div>
    </details>
  )
}

function SubjobDisclosure({
  job,
  compact = false,
}: {
  job: DisplayJobRun
  compact?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const shouldLoadDetails = isOpen
  const detailedRunSnapshot = useQuery({
    queryKey: ['jobs', 'runs', job.id],
    queryFn: () => fetchJobRun(job.id),
    enabled: shouldLoadDetails,
    refetchInterval: shouldLoadDetails && isActiveDisplayRun(job.status) ? 3_000 : false,
    retry: 1,
  })
  const detailedJob = detailedRunSnapshot.data ? buildDisplayJobRun(detailedRunSnapshot.data) : null
  const subjobs = detailedJob?.subjobs ?? []
  const isLoading = detailedRunSnapshot.isLoading || detailedRunSnapshot.isFetching
  const isError = detailedRunSnapshot.isError

  const completeCount = subjobs.filter((subjob) => isCompleteSubjobStatus(subjob.status)).length
  const failedCount = subjobs.filter((subjob) => isFailedSubjobStatus(subjob.status)).length
  const summaryCompleteCount = subjobs.length ? completeCount : job.subjobSummary?.finished ?? 0
  const summaryFailedCount = subjobs.length ? failedCount : job.subjobSummary?.failed ?? 0
  const expectedCount = subjobs.length
    ? expectedSubjobCount(subjobs)
    : job.subjobSummary?.total ?? job.subjobCount ?? 0
  const eta = estimateSubjobEta(detailedJob ?? job, completeCount, expectedCount)
  const summaryLabel = `${summaryCompleteCount}/${summaryFailedCount}/${expectedCount}${eta ? ` / ${eta}` : ''}`

  return (
    <details
      className={`subjob-block ${compact ? 'compact' : ''}`}
      open={isOpen}
      onToggle={(event) => setIsOpen(event.currentTarget.open)}
    >
      <summary>
        <span>Child jobs</span>
        <span>
          {isError ? 'unavailable' : summaryLabel}
        </span>
      </summary>
      <div className="subjob-list">
        {isError ? (
          <p className="run-detail-empty">Child jobs could not be loaded.</p>
        ) : isLoading && !subjobs.length ? (
          <p className="run-detail-empty">Loading child jobs.</p>
        ) : subjobs.length ? (
          subjobs.map((subjob) => <SubjobRow subjob={subjob} key={subjob.id} />)
        ) : (
          <p className="run-detail-empty">No child jobs were reported for this run.</p>
        )}
      </div>
    </details>
  )
}

function SubjobRow({ subjob }: { subjob: JobSubjob }) {
  const position =
    subjob.index !== undefined && subjob.total !== undefined
      ? `${subjob.index}/${subjob.total}`
      : subjob.type

  return (
    <article className="subjob-row">
      <div>
        <strong>{subjob.label}</strong>
        <small>{subjob.detail}</small>
      </div>
      <span className={`pill ${subjob.status}`}>{subjob.status}</span>
      <span className="subjob-position">{position}</span>
      <div className="progress-track" aria-hidden="true">
        <span style={{ width: `${subjob.progress}%` }} />
      </div>
    </article>
  )
}

function expectedSubjobCount(subjobs: JobSubjob[]): number {
  const reportedTotal = Math.max(
    0,
    ...subjobs.map((subjob) => (typeof subjob.total === 'number' ? subjob.total : 0)),
  )
  return Math.max(subjobs.length, Math.floor(reportedTotal))
}

function estimateSubjobEta(
  job: DisplayJobRun,
  completeCount: number,
  expectedCount: number,
): string | null {
  if (!isActiveDisplayRun(job.status) || job.startedAt === null || completeCount <= 0) {
    return null
  }

  const remainingCount = expectedCount - completeCount
  if (remainingCount <= 0) {
    return null
  }

  const startedAt = Date.parse(job.startedAt)
  if (!Number.isFinite(startedAt)) {
    return null
  }

  const elapsedMs = Date.now() - startedAt
  if (elapsedMs <= 0) {
    return null
  }

  const estimatedRemainingMs = (elapsedMs / completeCount) * remainingCount
  return `eta ~${formatDurationEstimate(estimatedRemainingMs)}`
}

function isCompleteSubjobStatus(status: string): boolean {
  return ['complete', 'completed', 'succeeded'].includes(status)
}

function isFailedSubjobStatus(status: string): boolean {
  return ['failed', 'timed_out', 'lost', 'needs_review'].includes(status)
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

function formatRunTimestamp(value: string): string {
  const timestamp = Date.parse(value)
  if (!Number.isFinite(timestamp)) {
    return 'unknown'
  }

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(timestamp)
}

function formatRunParameterValue(value: JobParameterValue): string {
  if (value === null) {
    return 'null'
  }

  if (typeof value === 'string') {
    return value.length ? value : 'empty string'
  }

  return value.toString()
}

function formatExecutionMode(mode: JobDefinition['execution_mode']): string {
  if (mode === 'api') {
    return 'API'
  }

  return mode.charAt(0).toUpperCase() + mode.slice(1)
}

function formatResourceHints(resourceHints: JobResourceHints): string {
  const details: string[] = []

  if (resourceHints.gpu_count > 0) {
    details.push(`${resourceHints.gpu_count} GPU${resourceHints.gpu_count === 1 ? '' : 's'}`)
  }
  if (resourceHints.min_vram_gib !== null) {
    details.push(`${formatNumber(resourceHints.min_vram_gib)} GiB VRAM`)
  }
  if (resourceHints.exclusive_gpu) {
    details.push('exclusive')
  }
  if (resourceHints.docker_required) {
    details.push('Docker')
  }

  return details.length ? details.join(' / ') : 'none'
}

function formatTimeout(value: number | null): string {
  if (value === null) {
    return 'none'
  }

  if (value >= 3600) {
    return `${formatNumber(value / 3600)} h`
  }

  if (value >= 60) {
    return `${Math.round(value / 60)} min`
  }

  return `${value} sec`
}

function parseOptionalInteger(value: string): number | null {
  if (value.trim() === '') {
    return null
  }

  const parsedValue = Number.parseInt(value, 10)
  return Number.isNaN(parsedValue) ? null : parsedValue
}

function parseOptionalString(value: string): string | null {
  const trimmedValue = value.trim()
  return trimmedValue === '' ? null : trimmedValue
}

function formatCommandInput(command: string[]): string {
  return command.map(formatCommandArgument).join(' ')
}

function parseCommandInput(value: string): string[] {
  if (value.includes('\n')) {
    return value
      .split(/\r?\n/)
      .map((part) => part.trim())
      .filter(Boolean)
  }

  return parseQuotedCommandInput(value)
}

function formatCommandArgument(argument: string): string {
  if (argument === '') {
    return '""'
  }
  if (!/[\s"'\\]/.test(argument)) {
    return argument
  }
  return `"${argument.replace(/(["\\])/g, '\\$1')}"`
}

function parseQuotedCommandInput(value: string): string[] {
  const args: string[] = []
  let current = ''
  let quote: 'single' | 'double' | null = null
  let escaping = false

  for (const character of value.trim()) {
    if (escaping) {
      current += character
      escaping = false
      continue
    }
    if (character === '\\') {
      escaping = true
      continue
    }
    if (quote === 'single') {
      if (character === "'") {
        quote = null
      } else {
        current += character
      }
      continue
    }
    if (quote === 'double') {
      if (character === '"') {
        quote = null
      } else {
        current += character
      }
      continue
    }
    if (character === "'") {
      quote = 'single'
      continue
    }
    if (character === '"') {
      quote = 'double'
      continue
    }
    if (/\s/.test(character)) {
      if (current !== '') {
        args.push(current)
        current = ''
      }
      continue
    }
    current += character
  }

  if (escaping) {
    current += '\\'
  }
  if (current !== '') {
    args.push(current)
  }

  return args
}

function formatParameterInputValue(value: JobParameterValue): string {
  return value === null ? '' : value.toString()
}

function parseParameterValue(value: string, valueType: JobParameter['value_type']): JobParameterValue {
  if (value.trim() === '') {
    return null
  }

  if (valueType === 'integer') {
    const parsedValue = Number.parseInt(value, 10)
    return Number.isNaN(parsedValue) ? null : parsedValue
  }

  if (valueType === 'float') {
    const parsedValue = Number.parseFloat(value)
    return Number.isNaN(parsedValue) ? null : parsedValue
  }

  if (valueType === 'boolean') {
    return value.toLowerCase() === 'true'
  }

  if (valueType === 'flag') {
    return value.toLowerCase() === 'true'
  }

  return value
}

export function buildInitialQueueParameterValues(
  definition: JobDefinition,
  sourceValues: Record<string, JobParameterValue> = {},
): Record<string, JobParameterValue> {
  return Object.fromEntries(
    definition.parameters
      .filter((parameter) => parameter.required_at_queue || parameter.allow_queue_override)
      .map((parameter) => [
        parameter.name,
        Object.prototype.hasOwnProperty.call(sourceValues, parameter.name)
          ? sourceValues[parameter.name]
          : parameter.default_value,
      ]),
  )
}

function buildQueueParameters(
  definition: JobDefinition,
  values: Record<string, JobParameterValue>,
): Record<string, JobParameterValue> {
  return Object.fromEntries(
    definition.parameters
      .filter((parameter) => parameter.required_at_queue || parameter.allow_queue_override)
      .map((parameter) => [parameter.name, values[parameter.name] ?? null]),
  )
}

function buildJobDefinitionGroups(definitions: JobDefinition[]): JobDefinitionGroup[] {
  const groups = new Map<string, JobDefinitionGroup>()

  for (const definition of definitions) {
    const settings = buildJobGroupSettings(definition)
    const groupId = buildDefinitionGroupId(settings)
    const existingGroup = groups.get(groupId)

    if (existingGroup) {
      existingGroup.definitions.push(definition)
      existingGroup.enabledCount += definition.enabled ? 1 : 0
      existingGroup.title = buildJobGroupTitle(existingGroup.definitions, settings)
      existingGroup.description = buildJobGroupDescription(existingGroup.definitions, settings)
      continue
    }

    const definitionsInGroup = [definition]
    groups.set(groupId, {
      id: groupId,
      title: buildJobGroupTitle(definitionsInGroup, settings),
      description: buildJobGroupDescription(definitionsInGroup, settings),
      settings,
      definitions: definitionsInGroup,
      enabledCount: definition.enabled ? 1 : 0,
    })
  }

  return [...groups.values()]
}

function buildJobGroupSettings(definition: JobDefinition): JobGroupSettings {
  return {
    execution_mode: definition.execution_mode,
    command: buildCommandGroupBase(definition.command),
    working_directory: definition.working_directory,
    image: definition.image,
    default_priority: definition.default_priority,
    timeout_seconds: definition.timeout_seconds,
    event_contract: definition.event_contract,
    resource_hints: { ...definition.resource_hints },
    retry_policy: { ...definition.retry_policy },
  }
}

function buildCommandGroupBase(command: string[]): string[] {
  if (command.length <= 1) {
    return [...command]
  }

  const moduleFlagIndex = command.indexOf('-m')
  if (moduleFlagIndex >= 0 && command[moduleFlagIndex + 1]) {
    return command.slice(0, moduleFlagIndex + 2)
  }

  if (isPythonCommand(command[0]) && command[1]?.endsWith('.py')) {
    return command.slice(0, 2)
  }

  return [...command]
}

function isPythonCommand(command: string): boolean {
  const executableName = command.split(/[\\/]/).pop()?.toLowerCase() ?? command.toLowerCase()
  return executableName === 'python' || executableName === 'python3' || executableName === 'python.exe'
}

function buildDefinitionDefaultsFromGroup(settings: JobGroupSettings): Partial<JobDefinition> {
  return {
    ...settings,
    command: [...settings.command],
    resource_hints: { ...settings.resource_hints },
    retry_policy: { ...settings.retry_policy },
  }
}

function buildDefinitionGroupId(settings: JobGroupSettings): string {
  return `job-group-${hashString(stableStringifyJobGroupSettings(settings))}`
}

function stableStringifyJobGroupSettings(settings: JobGroupSettings): string {
  return JSON.stringify({
    command: settings.command,
    default_priority: settings.default_priority,
    event_contract: settings.event_contract,
    execution_mode: settings.execution_mode,
    image: settings.image,
    resource_hints: {
      docker_required: settings.resource_hints.docker_required,
      exclusive_gpu: settings.resource_hints.exclusive_gpu,
      gpu_count: settings.resource_hints.gpu_count,
      min_vram_gib: settings.resource_hints.min_vram_gib,
    },
    retry_policy: {
      backoff_seconds: settings.retry_policy.backoff_seconds,
      max_attempts: settings.retry_policy.max_attempts,
    },
    timeout_seconds: settings.timeout_seconds,
    working_directory: settings.working_directory,
  })
}

function hashString(value: string): string {
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = Math.imul(hash ^ value.charCodeAt(index), 16_777_619)
  }
  return (hash >>> 0).toString(36)
}

function buildJobGroupTitle(
  definitions: JobDefinition[],
  settings: JobGroupSettings,
): string {
  if (definitions.length === 1) {
    return definitions[0].name
  }

  const prefix = commonLeadingWords(definitions.map((definition) => definition.name))
  if (prefix !== null) {
    return prefix
  }

  const directoryName = settings.working_directory?.split(/[\\/]/).filter(Boolean).at(-1)
  if (directoryName) {
    return directoryName
  }

  return `${formatExecutionMode(settings.execution_mode)} jobs`
}

function buildJobGroupDescription(
  definitions: JobDefinition[],
  settings: JobGroupSettings,
): string {
  const count = `${definitions.length} definition${definitions.length === 1 ? '' : 's'}`
  const location = settings.working_directory ?? settings.image ?? 'service default'
  return `${count} using ${location}`
}

function commonLeadingWords(values: string[]): string | null {
  const wordSets = values.map((value) => value.trim().split(/\s+/).filter(Boolean))
  const firstWords = wordSets[0] ?? []
  const prefix: string[] = []

  for (const [wordIndex, word] of firstWords.entries()) {
    const normalizedWord = word.toLowerCase()
    if (wordSets.every((words) => words[wordIndex]?.toLowerCase() === normalizedWord)) {
      prefix.push(word)
      continue
    }
    break
  }

  return prefix.length ? prefix.join(' ') : null
}

function splitChoices(value: string): string[] {
  return value
    .split(',')
    .map((choice) => choice.trim())
    .filter(Boolean)
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}
