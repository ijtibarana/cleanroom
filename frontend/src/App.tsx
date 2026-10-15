import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  API_BASE_URL,
  Audit,
  AuditLog,
  CheckResult,
  CheckStatus,
  CHECK_NAMES,
  getAudit,
  getLogs,
  isRunning,
  reportUrl,
  startAudit,
} from './api'

const initialChecks: CheckResult[] = CHECK_NAMES.map((name, index) => ({
  id: `check-${index + 1}`,
  name,
  status: 'SKIPPED',
  summary: 'Start an audit to inspect this requirement.',
  evidence: [],
  recommendation: 'Choose a repository above to begin.',
  files: [],
}))

function App() {
  const [repositoryPath, setRepositoryPath] = useState('')
  const [verifyDocker, setVerifyDocker] = useState(true)
  const [audit, setAudit] = useState<Audit | null>(null)
  const [logs, setLogs] = useState<AuditLog[]>([])
  const [selectedCheck, setSelectedCheck] = useState<CheckResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [error, setError] = useState('')

  const activeChecks = audit?.checks.length ? audit.checks : initialChecks
  const running = Boolean(audit && isRunning(audit.status))

  const refreshAudit = useCallback(async (id: string, showSpinner = false) => {
    if (showSpinner) setLoading(true)
    try {
      const next = await getAudit(id)
      setAudit(next)
      if (next.checks.length && !selectedCheck) setSelectedCheck(next.checks[0])
      if (next.error) setError(next.error)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to retrieve this audit.')
    } finally {
      if (showSpinner) setLoading(false)
    }
  }, [selectedCheck])

  const refreshLogs = useCallback(async (id: string) => {
    setLoadingLogs(true)
    try {
      setLogs(await getLogs(id))
    } catch {
      // Logs are supplementary; the audit result remains useful if this endpoint is unavailable.
    } finally {
      setLoadingLogs(false)
    }
  }, [])

  useEffect(() => {
    if (!audit || !running) return
    const timer = window.setInterval(() => {
      void refreshAudit(audit.id)
      void refreshLogs(audit.id)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [audit, refreshAudit, refreshLogs, running])

  useEffect(() => {
    if (audit?.checks.length && selectedCheck) {
      const current = audit.checks.find((check) => check.id === selectedCheck.id)
      if (current) setSelectedCheck(current)
    }
  }, [audit, selectedCheck])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const path = repositoryPath.trim()
    if (!path) {
      setError('Enter a repository path to start an audit.')
      return
    }
    setError('')
    setLoading(true)
    setLogs([])
    setSelectedCheck(null)
    try {
      const result = await startAudit(path, verifyDocker)
      await refreshAudit(result.id)
      await refreshLogs(result.id)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to start the audit.')
      setAudit(null)
    } finally {
      setLoading(false)
    }
  }

  const counts = useMemo(() => activeChecks.reduce<Record<CheckStatus, number>>((all, check) => {
    all[check.status] += 1
    return all
  }, { PASS: 0, FAIL: 0, UNVERIFIED: 0, SKIPPED: 0 }), [activeChecks])

  const auditTitle = audit ? `${audit.repositoryPath || repositoryPath || 'Selected repository'}` : 'No repository selected'

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="CleanRoom dashboard">
          <span className="brand-mark" aria-hidden="true"><span /></span>
          <span>Clean<span className="brand-accent">Room</span></span>
        </a>
        <div className="topbar-meta">
          <span className="eyebrow">REPRODUCIBILITY AUDITOR</span>
          <span className="connection-dot" aria-hidden="true" />
          <span className="connection-label">Local API</span>
        </div>
      </header>

      <main id="top" className="page-wrap">
        <section className="intro" aria-labelledby="page-title">
          <div>
            <p className="kicker"><span className="kicker-line" /> Works on my machine? Prove it.</p>
            <h1 id="page-title">A clearer path to<br /><em>reproducible</em> software.</h1>
            <p className="lede">CleanRoom checks the files, commands, and runtime assumptions that make a repository portable.</p>
          </div>
          <div className="intro-aside" aria-label="Audit summary">
            <span className="aside-number">08</span>
            <span className="aside-copy">mandatory<br />checks</span>
          </div>
        </section>

        <section className="audit-launch panel" aria-labelledby="launch-title">
          <div className="panel-heading">
            <div>
              <span className="section-index">01 / START</span>
              <h2 id="launch-title">Choose a repository</h2>
            </div>
            <span className="quiet-label">LOCAL INSPECTION</span>
          </div>
          <form onSubmit={handleSubmit} className="launch-form">
            <div className="path-field">
              <label htmlFor="repository-path">Repository path</label>
              <div className="input-wrap">
                <span className="input-prefix" aria-hidden="true">~/</span>
                <input
                  id="repository-path"
                  value={repositoryPath}
                  onChange={(event) => setRepositoryPath(event.target.value)}
                  placeholder="projects/your-repository"
                  autoComplete="off"
                  spellCheck="false"
                />
              </div>
              <p className="field-hint">Use an absolute path or a path visible to the CleanRoom API.</p>
            </div>
            <div className="launch-options">
              <label className="toggle-label">
                <input type="checkbox" checked={verifyDocker} onChange={(event) => setVerifyDocker(event.target.checked)} />
                <span className="toggle" aria-hidden="true"><span /></span>
                <span>Verify Docker when available</span>
              </label>
              <button className="primary-button" type="submit" disabled={loading}>
                {loading ? <><span className="spinner" aria-hidden="true" /> Starting audit</> : <>Start audit <span aria-hidden="true">↗</span></>}
              </button>
            </div>
          </form>
          {error && <div className="alert error-alert" role="alert"><span aria-hidden="true">!</span>{error}</div>}
        </section>

        <section className="summary-strip" aria-label="Audit overview">
          <div className="summary-intro">
            <span className="section-index">02 / OVERVIEW</span>
            <h2>{audit ? 'Audit in focus' : 'Ready when you are'}</h2>
            <p>{auditTitle}</p>
          </div>
          <div className="summary-stats">
            <SummaryStat value={String(counts.PASS).padStart(2, '0')} label="Passed" tone="pass" />
            <SummaryStat value={String(counts.FAIL).padStart(2, '0')} label="Failed" tone="fail" />
            <SummaryStat value={String(counts.UNVERIFIED).padStart(2, '0')} label="Unverified" tone="unverified" />
            <div className="summary-status"><span className={`status-dot ${statusClass(audit?.overallStatus ?? 'SKIPPED')}`} />{audit ? formatStatus(audit.overallStatus) : 'Awaiting audit'}</div>
          </div>
        </section>

        <section className="checks-section" aria-labelledby="checks-title">
          <div className="section-heading-row">
            <div><span className="section-index">03 / FINDINGS</span><h2 id="checks-title">Eight-point audit</h2></div>
            {audit && <span className={`run-state ${running ? 'is-running' : ''}`}><span className="status-dot" />{running ? 'Audit in progress' : `Updated ${formatDate(audit.updatedAt ?? audit.createdAt)}`}</span>}
          </div>
          {!audit && <div className="empty-note"><span className="empty-icon" aria-hidden="true">⌁</span><div><strong>Your findings will appear here.</strong><span>Point CleanRoom at a repository to see evidence-backed results.</span></div></div>}
          <div className="checks-grid">
            {activeChecks.map((check, index) => (
              <CheckCard key={check.id} check={check} index={index} selected={selectedCheck?.id === check.id} onSelect={setSelectedCheck} />
            ))}
          </div>
        </section>

        <section className="details-layout" aria-label="Selected finding and exports">
          <div className="detail-panel panel">
            <div className="panel-heading compact-heading"><div><span className="section-index">04 / EVIDENCE</span><h2>Finding detail</h2></div><span className="detail-number">{selectedCheck ? selectedCheck.id.replace('check-', '').padStart(2, '0') : '—'}</span></div>
            {selectedCheck ? <FindingDetail check={selectedCheck} /> : <div className="detail-empty">Select a check above to inspect its evidence and recommendation.</div>}
          </div>
          <div className="reports-panel panel">
            <div className="panel-heading compact-heading"><div><span className="section-index">05 / EXPORT</span><h2>Reports</h2></div><span className="export-icon" aria-hidden="true">↓</span></div>
            {audit ? <div className="report-links"><a href={reportUrl(audit.id, 'json')} download>Download JSON <span>↗</span></a><a href={reportUrl(audit.id, 'html')} target="_blank" rel="noreferrer">Open HTML report <span>↗</span></a><p>Generated from the current audit snapshot.</p></div> : <div className="detail-empty">Reports become available after an audit starts.</div>}
          </div>
        </section>

        <section className="logs-panel panel" aria-labelledby="logs-title">
          <div className="panel-heading compact-heading"><div><span className="section-index">06 / VERIFICATION</span><h2 id="logs-title">Activity log</h2></div><span className="log-count">{loadingLogs ? 'Refreshing…' : `${logs.length} ${logs.length === 1 ? 'entry' : 'entries'}`}</span></div>
          <LogList logs={logs} running={running} hasAudit={Boolean(audit)} />
        </section>

        <footer className="footer"><span>CleanRoom / local-first repository auditing</span><span>API base: {API_BASE_URL || 'same origin'}</span></footer>
      </main>
    </div>
  )
}

function SummaryStat({ value, label, tone }: { value: string; label: string; tone: 'pass' | 'fail' | 'unverified' }) {
  return <div className={`summary-stat ${tone.toLowerCase()}`}><strong>{value}</strong><span>{label}</span></div>
}

function CheckCard({ check, index, selected, onSelect }: { check: CheckResult; index: number; selected: boolean; onSelect: (check: CheckResult) => void }) {
  return <button className={`check-card ${selected ? 'selected' : ''}`} onClick={() => onSelect(check)} aria-pressed={selected}>
    <div className="card-top"><span className="card-index">{String(index + 1).padStart(2, '0')}</span><StatusBadge status={check.status} /></div>
    <h3>{check.name}</h3><p>{check.summary}</p><span className="inspect-link">Inspect finding <span aria-hidden="true">→</span></span>
  </button>
}

function StatusBadge({ status }: { status: CheckStatus | 'PENDING' }) {
  return <span className={`status-badge ${statusClass(status)}`}><span className="status-dot" />{formatStatus(status)}</span>
}

function FindingDetail({ check }: { check: CheckResult }) {
  return <div className="finding-content"><div className="finding-status"><StatusBadge status={check.status} /><span>{check.name}</span></div><p className="finding-summary">{check.summary}</p><div className="detail-columns"><div><h3>Evidence</h3>{check.evidence.length ? <ul className="evidence-list">{check.evidence.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="muted">No evidence was returned.</p>}</div><div><h3>Recommendation</h3><p className="recommendation">{check.recommendation}</p></div></div>{check.files.length > 0 && <div className="file-references"><h3>Referenced files</h3>{check.files.map((file) => <code key={file}>{file}</code>)}</div>}</div>
}

function LogList({ logs, running, hasAudit }: { logs: AuditLog[]; running: boolean; hasAudit: boolean }) {
  if (!hasAudit) return <div className="logs-empty"><span className="terminal-mark" aria-hidden="true">›_</span><span>Verification output will stream here when an audit is running.</span></div>
  if (!logs.length && running) return <div className="logs-empty"><span className="spinner" aria-hidden="true" /><span>Waiting for verification output…</span></div>
  if (!logs.length) return <div className="logs-empty"><span className="terminal-mark" aria-hidden="true">›_</span><span>No command output was recorded for this audit.</span></div>
  return <div className="log-list">{logs.map((log) => <details className="log-entry" key={log.id}><summary><span className={`log-level ${log.level ?? 'info'}`} /> <code>{log.command}</code><span className="log-meta">{log.exitCode == null ? '—' : `exit ${log.exitCode}`} {log.elapsedMs != null ? `· ${log.elapsedMs}ms` : ''}</span></summary><pre>{log.output || 'No output.'}</pre></details>)}</div>
}

function statusClass(status: string) { return status.toLowerCase().replace('pending', 'unverified') }
function formatStatus(status: string) { return status.charAt(0) + status.slice(1).toLowerCase() }
function formatDate(value?: string) { if (!value) return 'recently'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) }

export default App
