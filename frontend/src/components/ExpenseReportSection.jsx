import { useMemo, useState, useEffect, useCallback } from 'react'
import { API, authFetch } from '../utils/api'
import { formatDate, formatMoney, formatUploadDate } from '../utils/formatters'
import { hasRole } from '../utils/roles'

export function ExpenseReportSection({ transactions, companies, glCodes, statementId, userRole }) {
  const [expandedCompanyId, setExpandedCompanyId] = useState(null)
  const [downloading, setDownloading] = useState(null)
  const [finalizing, setFinalizing] = useState(null)
  const [approving, setApproving] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [reports, setReports] = useState([])

  const companyMap = useMemo(() => {
    const m = {}
    for (const c of companies) m[c.id] = c.name
    return m
  }, [companies])

  const glMap = useMemo(() => {
    const m = {}
    for (const g of glCodes) m[g.id] = `${g.code} — ${g.name}`
    return m
  }, [glCodes])

  const grouped = useMemo(() => {
    const groups = {}
    for (const tx of transactions) {
      if (!tx.company_id) continue
      if (!groups[tx.company_id]) {
        groups[tx.company_id] = {
          company_id: tx.company_id,
          company_name: companyMap[tx.company_id] || 'Unknown',
          transactions: [],
          total_amount: 0,
          total_tax: 0,
        }
      }
      const g = groups[tx.company_id]
      g.transactions.push(tx)
      g.total_amount += (tx.amount_cad || 0)
      g.total_tax += (tx.tax_amount || 0)
    }
    return Object.values(groups).sort((a, b) => a.company_name.localeCompare(b.company_name))
  }, [transactions, companyMap])

  const fetchReports = useCallback(async () => {
    if (!statementId) return
    try {
      const res = await authFetch(`${API}/expense-reports/?statement_id=${statementId}`)
      if (res.ok) setReports(await res.json())
    } catch { /* ignore */ }
  }, [statementId])

  useEffect(() => { fetchReports() }, [fetchReports])

  const reportsByCompany = useMemo(() => {
    const m = {}
    for (const r of reports) {
      if (!m[r.company_id]) m[r.company_id] = []
      m[r.company_id].push(r)
    }
    return m
  }, [reports])

  if (grouped.length === 0) return null

  const handleDownload = async (companyId) => {
    setDownloading(companyId)
    try {
      const res = await authFetch(
        `${API}/expense-reports/${statementId}/pdf?company_id=${companyId}`
      )
      if (!res.ok) throw new Error('PDF generation failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Expense_Report_${(companyMap[companyId] || 'report').replace(/\s+/g, '_')}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Failed to download PDF: ' + err.message)
    }
    setDownloading(null)
  }

  const handleFinalize = async (companyId) => {
    const group = grouped.find(g => g.company_id === companyId)
    if (group) {
      const missing = group.transactions.filter(tx => !tx.gl_code_id)
      if (missing.length > 0) {
        alert(`${missing.length} transaction${missing.length === 1 ? ' is' : 's are'} missing GL code assignments. Please assign GL codes before finalizing.`)
        return
      }
    }
    setFinalizing(companyId)
    try {
      const res = await authFetch(
        `${API}/expense-reports/${statementId}/finalize?company_id=${companyId}`,
        { method: 'POST' }
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Finalize failed')
      }
      await fetchReports()
    } catch (err) {
      alert('Failed to finalize: ' + err.message)
    }
    setFinalizing(null)
  }

  const handleApprove = async (reportId) => {
    setApproving(reportId)
    try {
      const res = await authFetch(
        `${API}/expense-reports/${reportId}/approve`,
        { method: 'POST' }
      )
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Approve failed')
      }
      await fetchReports()
    } catch (err) {
      alert('Failed to approve: ' + err.message)
    }
    setApproving(null)
  }

  const handleDownloadReport = async (reportId, companyName, status) => {
    setDownloading(reportId)
    try {
      const res = await authFetch(`${API}/expense-reports/${reportId}/download`)
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const safe = (companyName || 'report').replace(/\s+/g, '_')
      const suffix = status === 'approved' ? '_APPROVED' : '_PENDING'
      a.download = `Expense_Report_${safe}${suffix}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Download failed: ' + err.message)
    }
    setDownloading(null)
  }

  const handleDeleteReport = async (reportId) => {
    if (!confirm('Delete this finalized report?')) return
    setReports(prev => prev.filter(r => r.id !== reportId))
    try {
      const res = await authFetch(`${API}/expense-reports/${reportId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
    } catch (err) {
      alert('Delete failed: ' + err.message)
      await fetchReports()
    }
  }

  const expanded = grouped.find(g => g.company_id === expandedCompanyId)

  return (
    <div className="expense-reports-section">
      <div className="expense-reports-header">
        <h3 className="expense-reports-title">Expense Reports</h3>
        <span className="expense-reports-count">{grouped.length} {grouped.length === 1 ? 'company' : 'companies'}</span>
      </div>

      <div className="expense-report-chips">
        {grouped.map(g => {
          const companyReports = reportsByCompany[g.company_id] || []
          const hasApproved = companyReports.some(r => r.status === 'approved')
          const hasPending = companyReports.some(r => r.status === 'pending')

          let badge = null
          if (hasApproved) badge = <span className="chip-badge approved">Approved</span>
          else if (hasPending) badge = <span className="chip-badge pending">Pending</span>

          return (
            <button
              key={g.company_id}
              className={`expense-chip${expandedCompanyId === g.company_id ? ' active' : ''}`}
              onClick={() => setExpandedCompanyId(
                expandedCompanyId === g.company_id ? null : g.company_id
              )}
            >
              <span className="expense-chip-name">{g.company_name} {badge}</span>
              <span className="expense-chip-meta">
                {g.transactions.length} tx &middot; {formatMoney(g.total_amount)}
              </span>
            </button>
          )
        })}
      </div>

      {expanded && (
        <div className="expense-report-detail">
          <div className="expense-report-detail-header">
            <h4 className="expense-report-detail-title">{expanded.company_name}</h4>
            <div className="expense-report-actions">
              <button
                className="expense-download-btn"
                onClick={() => handleDownload(expanded.company_id)}
                disabled={downloading === expanded.company_id}
              >
                {downloading === expanded.company_id ? 'Generating...' : 'Download PDF'}
              </button>
              {hasRole(userRole, 'delegate') && (
                <button
                  className="expense-finalize-btn"
                  onClick={() => handleFinalize(expanded.company_id)}
                  disabled={finalizing === expanded.company_id}
                >
                  {finalizing === expanded.company_id ? 'Finalizing...' : 'Finalize Report'}
                </button>
              )}
            </div>
          </div>

          <div className="expense-report-table-wrapper">
            <table className="expense-report-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Merchant</th>
                  <th>Description</th>
                  <th>GL Code</th>
                  <th className="amount-col">Amount</th>
                  <th className="amount-col">Tax (HST/GST)</th>
                </tr>
              </thead>
              <tbody>
                {expanded.transactions
                  .sort((a, b) => (a.transaction_date || '').localeCompare(b.transaction_date || ''))
                  .map(tx => (
                    <tr key={tx.id}>
                      <td className="date-cell">{formatDate(tx.transaction_date)}</td>
                      <td>{tx.merchant || '—'}</td>
                      <td>{tx.description || '—'}</td>
                      <td>{tx.gl_code_id ? (glMap[tx.gl_code_id] || '—') : '—'}</td>
                      <td className="amount-cell">{formatMoney(tx.amount_cad)}</td>
                      <td className="amount-cell">{tx.tax_amount != null ? formatMoney(tx.tax_amount) : '—'}</td>
                    </tr>
                  ))
                }
              </tbody>
              <tfoot>
                <tr className="expense-totals-row">
                  <td colSpan={4} className="expense-totals-label">Totals</td>
                  <td className="amount-cell expense-totals-val">{formatMoney(expanded.total_amount)}</td>
                  <td className="amount-cell expense-totals-val">{formatMoney(expanded.total_tax)}</td>
                </tr>
                <tr className="expense-net-row">
                  <td colSpan={4} className="expense-totals-label">Net (Amount - Tax)</td>
                  <td colSpan={2} className="amount-cell expense-net-val">
                    {formatMoney(expanded.total_amount - expanded.total_tax)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Finalized reports for this company */}
          {(reportsByCompany[expanded.company_id] || []).length > 0 && (
            <div className="finalized-reports">
              <h5 className="finalized-reports-title">Finalized Reports</h5>
              {(reportsByCompany[expanded.company_id] || []).map(r => (
                <div key={r.id} className={`finalized-report-card ${r.status}`}>
                  <div className="finalized-report-info">
                    <span className={`report-status-badge ${r.status}`}>
                      {r.status === 'approved' ? 'Approved' : 'Pending Approval'}
                    </span>
                    <span className="report-meta">
                      {r.transaction_count} tx &middot; {formatMoney(r.total_amount)}
                    </span>
                    <span className="report-meta-detail">
                      Created by {r.created_by}{r.created_at ? ` on ${formatUploadDate(r.created_at)}` : ''}
                    </span>
                    {r.approved_by && (
                      <span className="report-meta-detail">
                        Approved by {r.approved_by}{r.approved_at ? ` on ${formatUploadDate(r.approved_at)}` : ''}
                      </span>
                    )}
                  </div>
                  <div className="finalized-report-actions">
                    <button
                      className="report-action-btn download"
                      onClick={() => handleDownloadReport(r.id, r.company_name, r.status)}
                      disabled={downloading === r.id}
                    >
                      {downloading === r.id ? '...' : 'Download'}
                    </button>
                    {r.status === 'pending' && hasRole(userRole, 'manager') && (
                      <button
                        className="report-action-btn approve"
                        onClick={() => handleApprove(r.id)}
                        disabled={approving === r.id}
                      >
                        {approving === r.id ? '...' : 'Approve'}
                      </button>
                    )}
                    <button
                      className="report-action-btn delete"
                      onClick={() => handleDeleteReport(r.id)}
                      disabled={deleting === r.id}
                    >
                      {deleting === r.id ? '...' : 'Delete'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
