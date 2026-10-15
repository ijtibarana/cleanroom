export type CheckStatus = 'PASS' | 'FAIL' | 'UNVERIFIED' | 'SKIPPED'

export type CheckResult = {
  id: string
  name: string
  status: CheckStatus
  summary: string
  evidence: string[]
  recommendation: string
  files: string[]
}

export type AuditLog = {
  id: string
  command: string
  output: string
  exitCode?: number | null
  elapsedMs?: number | null
  containerStatus?: string
  level?: 'info' | 'error' | 'success'
}

export type Audit = {
  id: string
  repositoryPath: string
  status: string
  overallStatus: CheckStatus | 'PENDING'
  checks: CheckResult[]
  logs: AuditLog[]
  createdAt?: string
  updatedAt?: string
  error?: string
  progress?: number
}

type JsonRecord = Record<string, unknown>

const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim()
export const API_BASE_URL = (configuredBase || '').replace(/\/$/, '')

const endpoint = (path: string) => `${API_BASE_URL}/api${path}`

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const raw = await response.text()
  let payload: unknown = null
  try {
    payload = raw ? JSON.parse(raw) : null
  } catch {
    payload = raw
  }
  if (!response.ok) {
    const detail = typeof payload === 'object' && payload !== null && 'detail' in payload
      ? String((payload as JsonRecord).detail)
      : `Request failed with ${response.status}`
    throw new Error(detail)
  }
  return payload as T
}

export async function startAudit(repositoryPath: string, verifyDocker: boolean): Promise<{ id: string }> {
  const payload = await request<JsonRecord>('/audits', {
    method: 'POST',
    body: JSON.stringify({ repo_path: repositoryPath, verify_docker: verifyDocker, verify_tests: true }),
  })
  const id = String(payload.id ?? payload.audit_id ?? payload.auditId ?? '')
  if (!id) throw new Error('The API did not return an audit id.')
  return { id }
}

export async function getAudit(id: string): Promise<Audit> {
  return normalizeAudit(await request<JsonRecord>(`/audits/${encodeURIComponent(id)}`), id)
}

export async function getLogs(id: string): Promise<AuditLog[]> {
  const payload = await request<unknown>(`/audits/${encodeURIComponent(id)}/logs`)
  const rows = Array.isArray(payload) ? payload : isRecord(payload) && Array.isArray(payload.logs) ? payload.logs : []
  return rows.map((row, index) => normalizeLog(row, index))
}

export function reportUrl(id: string, format: 'json' | 'html') {
  return endpoint(`/audits/${encodeURIComponent(id)}/report.${format}`)
}

function normalizeAudit(payload: JsonRecord, fallbackId: string): Audit {
  const rawChecks = Array.isArray(payload.checks) ? payload.checks : Array.isArray(payload.results) ? payload.results : []
  const rawLogs = Array.isArray(payload.logs) ? payload.logs : []
  const status = String(payload.status ?? payload.state ?? 'pending').toLowerCase()
  const rawOverall = String(payload.overall_status ?? payload.overallStatus ?? payload.result ?? '').toUpperCase()
  return {
    id: String(payload.id ?? payload.audit_id ?? fallbackId),
    repositoryPath: String(payload.repository_path ?? payload.repositoryPath ?? payload.path ?? ''),
    status,
    overallStatus: asStatus(rawOverall) ?? (isRunning(status) ? 'PENDING' : 'UNVERIFIED'),
    checks: rawChecks.map((check, index) => normalizeCheck(check, index)),
    logs: rawLogs.map((log, index) => normalizeLog(log, index)),
    createdAt: optionalString(payload.created_at ?? payload.createdAt),
    updatedAt: optionalString(payload.updated_at ?? payload.updatedAt),
    error: optionalString(payload.error ?? payload.message),
    progress: typeof payload.progress === 'number' ? payload.progress : undefined,
  }
}

function normalizeCheck(value: unknown, index: number): CheckResult {
  const row = isRecord(value) ? value : {}
  const status = asStatus(String(row.status ?? row.result ?? row.state ?? 'UNVERIFIED').toUpperCase()) ?? 'UNVERIFIED'
  return {
    id: String(row.id ?? row.key ?? `check-${index + 1}`),
    name: String(row.name ?? row.title ?? CHECK_NAMES[index] ?? `Check ${index + 1}`),
    status,
    summary: String(row.summary ?? row.description ?? row.message ?? 'No explanation was returned for this check.'),
    evidence: asStringArray(row.evidence),
    recommendation: String(row.recommendation ?? row.fix ?? 'No recommendation was returned.'),
    files: asStringArray(row.files ?? row.file_references ?? row.fileReferences),
  }
}

function normalizeLog(value: unknown, index: number): AuditLog {
  const row = isRecord(value) ? value : {}
  return {
    id: String(row.id ?? `log-${index + 1}`),
    command: String(row.command ?? row.cmd ?? 'Audit event'),
    output: String(row.output ?? row.message ?? ''),
    exitCode: typeof row.exit_code === 'number' ? row.exit_code : typeof row.exitCode === 'number' ? row.exitCode : null,
    elapsedMs: typeof row.elapsed_ms === 'number' ? row.elapsed_ms : typeof row.elapsedMs === 'number' ? row.elapsedMs : null,
    containerStatus: optionalString(row.container_status ?? row.containerStatus),
    level: row.level === 'error' || row.level === 'success' ? row.level : 'info',
  }
}

export function isRunning(status: string) {
  return ['queued', 'pending', 'running', 'in_progress', 'processing', 'started'].includes(status.toLowerCase())
}

function asStatus(value: string): CheckStatus | undefined {
  return ['PASS', 'FAIL', 'UNVERIFIED', 'SKIPPED'].includes(value) ? value as CheckStatus : undefined
}

function asStringArray(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String)
  return value == null || value === '' ? [] : [String(value)]
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

function optionalString(value: unknown): string | undefined {
  return value == null || value === '' ? undefined : String(value)
}

export const CHECK_NAMES = [
  'Git repository',
  'Dependency lockfile',
  'Runtime pinned',
  'Dockerfile',
  'Test command',
  'README setup',
  '.env.example',
  'Absolute paths',
]
