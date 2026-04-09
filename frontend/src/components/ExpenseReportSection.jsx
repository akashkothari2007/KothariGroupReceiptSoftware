import { useMemo, useState } from 'react'
import { API, authFetch } from '../utils/api'
import { formatDate, formatMoney } from '../utils/formatters'

export function ExpenseReportSection({ transactions, companies, glCodes, statementId }) {
  const [expandedCompanyId, setExpandedCompanyId] = useState(null)
  const [downloading, setDownloading] = useState(null)

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

  const expanded = grouped.find(g => g.company_id === expandedCompanyId)

  return (
    <div className="expense-reports-section">
      <div className="expense-reports-header">
        <h3 className="expense-reports-title">Expense Reports</h3>
        <span className="expense-reports-count">{grouped.length} {grouped.length === 1 ? 'company' : 'companies'}</span>
      </div>

      <div className="expense-report-chips">
        {grouped.map(g => (
          <button
            key={g.company_id}
            className={`expense-chip${expandedCompanyId === g.company_id ? ' active' : ''}`}
            onClick={() => setExpandedCompanyId(
              expandedCompanyId === g.company_id ? null : g.company_id
            )}
          >
            <span className="expense-chip-name">{g.company_name}</span>
            <span className="expense-chip-meta">
              {g.transactions.length} tx &middot; {formatMoney(g.total_amount)}
            </span>
          </button>
        ))}
      </div>

      {expanded && (
        <div className="expense-report-detail">
          <div className="expense-report-detail-header">
            <h4 className="expense-report-detail-title">{expanded.company_name}</h4>
            <button
              className="expense-download-btn"
              onClick={() => handleDownload(expanded.company_id)}
              disabled={downloading === expanded.company_id}
            >
              {downloading === expanded.company_id ? 'Generating...' : 'Download PDF'}
            </button>
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
                  <th className="amount-col">Tax</th>
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
        </div>
      )}
    </div>
  )
}
