import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  BatteryCharging,
  Bot,
  BrainCircuit,
  Cpu,
  Database,
  Gauge,
  HardDrive,
  ListChecks,
  MemoryStick,
  PanelsTopLeft,
  PauseCircle,
  Power,
  RadioTower,
  RotateCw,
  Server,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Timer,
  Zap,
} from 'lucide-react'

export type NavItem = {
  label: string
  icon: LucideIcon
}

export type Metric = {
  label: string
  value: string
  detail: string
  tone: 'good' | 'watch' | 'danger' | 'neutral'
  icon: LucideIcon
  percent?: number
}

export type Service = {
  name: string
  status: 'healthy' | 'degraded' | 'offline'
  detail: string
  latency: string
  parentName?: string
  isActive?: boolean
  href?: string
}

export type JobRun = {
  name: string
  status: string
  priority: string
  progress: number
  resource: string
  eta: string
  subjobCount?: number
  subjobSummary?: JobSubjobSummary
  subjobs?: JobSubjob[]
}

export type JobSubjobSummary = {
  finished: number
  failed: number
  total: number
}

export type JobSubjob = {
  id: string
  label: string
  status: string
  type: string
  progress: number
  detail: string
  index?: number
  total?: number
}

export type GpuProfile = {
  name: string
  power: string
  clocks: string
  state: 'active' | 'available'
  profileName?: string
  description?: string
}

export type SchedulerLane = {
  name: string
  value: string
  detail: string
}

export const navItems: NavItem[] = [
  { label: 'Overview', icon: PanelsTopLeft },
  { label: 'Hardware', icon: Cpu },
  { label: 'Services', icon: RadioTower },
  { label: 'Jobs', icon: ListChecks },
  { label: 'Schedules', icon: Timer },
  { label: 'Presets', icon: SlidersHorizontal },
  { label: 'Settings', icon: Settings },
]

export const metrics: Metric[] = [
  {
    label: 'CPU',
    value: '31%',
    detail: '16 cores · 61 C',
    tone: 'good',
    icon: Cpu,
    percent: 31,
  },
  {
    label: 'Memory',
    value: '42%',
    detail: '54.2 GiB free',
    tone: 'good',
    icon: MemoryStick,
    percent: 42,
  },
  {
    label: 'GPU',
    value: '49%',
    detail: '12 / 24 GiB VRAM · 68% load',
    tone: 'watch',
    icon: Gauge,
    percent: 68,
  },
  {
    label: 'Storage',
    value: '73%',
    detail: '2.8 TiB free',
    tone: 'watch',
    icon: HardDrive,
    percent: 73,
  },
  {
    label: 'Uplink',
    value: 'Online',
    detail: 'waiting for network sample',
    tone: 'good',
    icon: RadioTower,
    percent: 100,
  },
]

export const services: Service[] = [
  { name: 'llama-swap', status: 'healthy', detail: 'mixtral-q5 loaded', latency: '18 ms' },
  {
    name: 'vLLM',
    status: 'degraded',
    detail: 'not loaded',
    latency: 'idle',
    parentName: 'llama-swap',
    isActive: false,
  },
  {
    name: 'llama.cpp',
    status: 'healthy',
    detail: 'local backend available',
    latency: 'idle',
    parentName: 'llama-swap',
    isActive: false,
  },
  { name: 'Postgres', status: 'healthy', detail: 'scheduler state online', latency: '4 ms' },
  {
    name: 'Docker',
    status: 'degraded',
    detail: '1 container restarting',
    latency: 'retrying',
    href: 'https://brainsrv-dockge.lan.homeautomations.info',
  },
]

export const jobRuns: JobRun[] = [
  {
    name: 'dataset-embed-nightly',
    status: 'running',
    priority: 'normal',
    progress: 62,
    resource: 'GPU 0',
    eta: '41 min',
    subjobs: [
      {
        id: 'shard-001',
        label: 'Shard 001',
        status: 'complete',
        type: 'worker',
        progress: 100,
        detail: '12,000 / 12,000 embeddings',
        index: 1,
        total: 4,
      },
      {
        id: 'shard-002',
        label: 'Shard 002',
        status: 'running',
        type: 'worker',
        progress: 68,
        detail: '8,160 / 12,000 embeddings',
        index: 2,
        total: 4,
      },
      {
        id: 'shard-003',
        label: 'Shard 003',
        status: 'running',
        type: 'worker',
        progress: 54,
        detail: '6,480 / 12,000 embeddings',
        index: 3,
        total: 4,
      },
      {
        id: 'shard-004',
        label: 'Shard 004',
        status: 'pending',
        type: 'worker',
        progress: 0,
        detail: 'waiting for GPU slot',
        index: 4,
        total: 4,
      },
    ],
  },
  {
    name: 'caption-backfill',
    status: 'blocked_by_policy',
    priority: 'low',
    progress: 0,
    resource: 'solar policy',
    eta: 'waiting',
  },
  {
    name: 'model-eval-smoke',
    status: 'queued',
    priority: 'high',
    progress: 0,
    resource: 'exclusive GPU',
    eta: 'next',
  },
]

export const gpuProfiles: GpuProfile[] = [
  { name: 'Balanced', power: '260 W', clocks: 'default', state: 'active' },
  { name: 'Inference Quiet', power: '190 W', clocks: 'locked', state: 'available' },
  { name: 'Training Burst', power: '320 W', clocks: 'max app', state: 'available' },
]

export const schedulerLanes: SchedulerLane[] = [
  { name: 'Running', value: '1', detail: '1 GPU lock' },
  { name: 'Queued', value: '4', detail: '2 native, 2 Docker' },
  { name: 'Blocked', value: '1', detail: 'solar policy' },
  { name: 'Succeeded', value: '12', detail: 'last 24h' },
]

export const inventory = [
  { label: 'Backend', value: 'FastAPI', icon: Server },
  { label: 'State', value: 'Postgres', icon: Database },
  { label: 'GPU control', value: 'nvidia-smi', icon: Zap },
  { label: 'Power input', value: 'planned', icon: BatteryCharging },
  { label: 'Native runs', value: 'enabled', icon: Activity },
  { label: 'Docker runs', value: 'planned', icon: Bot },
]

export const topActions = [
  { label: 'Refresh', icon: RotateCw },
  { label: 'Apply profile', icon: Power },
  { label: 'New job', icon: Sparkles },
  { label: 'Hold queue', icon: PauseCircle },
]

export const brandIcon = BrainCircuit
