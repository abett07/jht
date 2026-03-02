import { useEffect, useState, useCallback } from 'react'

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function Badge({ children, color = '#666' }) {
  return <span style={{ background: color, color: '#fff', padding: '2px 8px', borderRadius: 12, fontSize: 12, marginLeft: 6 }}>{children}</span>
}

function StatCard({ label, value }) {
  return (
    <div style={{ background: '#f8f9fa', borderRadius: 8, padding: '16px 24px', textAlign: 'center', minWidth: 140 }}>
      <div style={{ fontSize: 28, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 13, color: '#666', marginTop: 4 }}>{label}</div>
    </div>
  )
}

export default function Home() {
  const [jobs, setJobs] = useState([])
  const [stats, setStats] = useState({})
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const load = useCallback(() => {
    fetch(`${API}/jobs`).then(r => r.json()).then(setJobs).catch(() => setJobs([]))
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const triggerScrape = async () => {
    setLoading(true); setMsg('')
    try {
      const r = await fetch(`${API}/scrape`, { method: 'POST' })
      const d = await r.json()
      setMsg(`Scrape complete: ${d.added} new jobs added`)
      load()
    } catch { setMsg('Scrape failed') }
    setLoading(false)
  }

  const sendEmail = async (id) => {
    try {
      const r = await fetch(`${API}/jobs/${id}/send`, { method: 'POST' })
      const d = await r.json()
      setMsg(d.sent ? `Email sent for job #${id}` : `Send failed for job #${id}`)
      load()
    } catch { setMsg(`Error sending for job #${id}`) }
  }

  const sendFollowup = async (id) => {
    try {
      const r = await fetch(`${API}/jobs/${id}/followup`, { method: 'POST' })
      const d = await r.json()
      setMsg(d.sent ? `Follow-up sent for job #${id}` : `Follow-up failed for job #${id}`)
      load()
    } catch { setMsg(`Error following up job #${id}`) }
  }

  const filtered = jobs.filter(j => {
    if (filter === 'emailed') return j.email_sent
    if (filter === 'pending') return !j.email_sent && j.recruiter_email
    if (filter === 'high') return j.match_score >= 70
    return true
  })

  return (
    <main style={{ padding: 24, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', maxWidth: 1100, margin: '0 auto' }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>Job Hunting Toolkit</h1>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <StatCard label="Total Jobs" value={stats.total_jobs ?? 0} />
        <StatCard label="Emails Sent" value={stats.emails_sent ?? 0} />
        <StatCard label="Follow-ups" value={stats.followups_sent ?? 0} />
        <StatCard label="Avg Score" value={stats.avg_match_score ?? '-'} />
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <button onClick={triggerScrape} disabled={loading} style={{ padding: '8px 16px', background: '#0070f3', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
          {loading ? 'Scraping...' : 'Run Scrape'}
        </button>
        <select value={filter} onChange={e => setFilter(e.target.value)} style={{ padding: '8px 12px', borderRadius: 6, border: '1px solid #ccc' }}>
          <option value="all">All Jobs</option>
          <option value="high">High Match (≥70)</option>
          <option value="emailed">Emailed</option>
          <option value="pending">Pending Send</option>
        </select>
        <button onClick={load} style={{ padding: '8px 12px', background: '#eee', border: '1px solid #ccc', borderRadius: 6, cursor: 'pointer' }}>Refresh</button>
        {msg && <span style={{ color: '#0070f3', fontSize: 13 }}>{msg}</span>}
      </div>

      {/* Job table */}
      {filtered.length === 0 ? <p style={{ color: '#999' }}>No jobs match this filter.</p> : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #eee', textAlign: 'left' }}>
              <th style={{ padding: 8 }}>ID</th>
              <th style={{ padding: 8 }}>Title</th>
              <th style={{ padding: 8 }}>Company</th>
              <th style={{ padding: 8 }}>Location</th>
              <th style={{ padding: 8 }}>Score</th>
              <th style={{ padding: 8 }}>Recruiter</th>
              <th style={{ padding: 8 }}>Status</th>
              <th style={{ padding: 8 }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(j => (
              <tr key={j.id} style={{ borderBottom: '1px solid #f0f0f0' }}>
                <td style={{ padding: 8 }}>{j.id}</td>
                <td style={{ padding: 8, fontWeight: 500 }}>{j.title}</td>
                <td style={{ padding: 8 }}>{j.company}</td>
                <td style={{ padding: 8 }}>{j.location}</td>
                <td style={{ padding: 8 }}>
                  {j.match_score != null ? (
                    <Badge color={j.match_score >= 70 ? '#22c55e' : j.match_score >= 40 ? '#f59e0b' : '#ef4444'}>
                      {j.match_score.toFixed(1)}
                    </Badge>
                  ) : '-'}
                </td>
                <td style={{ padding: 8, fontSize: 12, color: '#666' }}>{j.recruiter_email || '-'}</td>
                <td style={{ padding: 8 }}>
                  {j.followup_sent ? <Badge color="#8b5cf6">Followed Up</Badge>
                    : j.email_sent ? <Badge color="#0070f3">Emailed</Badge>
                    : j.recruiter_email ? <Badge color="#f59e0b">Ready</Badge>
                    : <Badge color="#ccc">No Email</Badge>}
                </td>
                <td style={{ padding: 8 }}>
                  {!j.email_sent && j.recruiter_email && (
                    <button onClick={() => sendEmail(j.id)} style={{ padding: '4px 10px', fontSize: 12, background: '#0070f3', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', marginRight: 4 }}>Send</button>
                  )}
                  {j.email_sent && !j.followup_sent && (
                    <button onClick={() => sendFollowup(j.id)} style={{ padding: '4px 10px', fontSize: 12, background: '#8b5cf6', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}>Follow Up</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  )
}
