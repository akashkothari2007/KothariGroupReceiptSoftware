import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'

const API = 'http://localhost:8000'

function useDebounce() {
  const timers = useRef({})
  return (key, fn, delay = 500) => {
    clearTimeout(timers.current[key])
    timers.current[key] = setTimeout(fn, delay)
  }
}

function ShimmerRows({ count = 8 }) {
  return Array.from({ length: count }).map((_, i) => (
    <tr key={i} className="shimmer-row">
      {Array.from({ length: 8 }).map((_, j) => (
        <td key={j}><div className="shimmer-block" /></td>
      ))}
    </tr>
  ))
}

function App() {
  const [statements, setStatements] = useState([])
  const [currentId, setCurrentId] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [glCodes, setGlCodes] = useState([])
  const [companies, setCompanies] = useState([])
  const [uploading, setUploading] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [loadingStatements, setLoadingStatements] = useState(true)
  const [loadingTx, setLoadingTx] = useState(false)
  const fileRef = useRef()
  const prevValues = useRef({})
  const debounce = useDebounce()

  const currentIndex = statements.findIndex(s => s.id === currentId)
  const currentStatement = currentIndex >= 0 ? statements[currentIndex] : null

  const fetchStatements = useCallback(async () => {
    const res = await fetch(`${API}/statements`)
    const data = await res.json()
    setStatements(data)
    setLoadingStatements(false)
    return data
  }, [])

  const fetchTransactions = useCallback(async (statementId) => {
    setLoadingTx(true)
    setTransactions([])
    const res = await fetch(`${API}/statements/${statementId}/transactions`)
    const data = await res.json()
    setTransactions(data)
    setLoadingTx(false)
  }, [])

  useEffect(() => {
    fetchStatements().then(data => {
      if (data.length > 0) setCurrentId(data[0].id)
    })
    fetch(`${API}/lookups/gl-codes`).then(r => r.json()).then(setGlCodes)
    fetch(`${API}/lookups/companies`).then(r => r.json()).then(setCompanies)
  }, [fetchStatements])

  useEffect(() => {
    if (currentId) {
      fetchTransactions(currentId)
    } else {
      setTransactions([])
    }
  }, [currentId, fetchTransactions])

  const goOlder = () => {
    if (currentIndex < statements.length - 1) {
      setCurrentId(statements[currentIndex + 1].id)
    }
  }

  const goNewer = () => {
    if (currentIndex > 0) {
      setCurrentId(statements[currentIndex - 1].id)
    }
  }

  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(`${API}/upload/statement`, { method: 'POST', body: form })
      const data = await res.json()
      const updated = await fetchStatements()
      setCurrentId(data.statement_id)
    } catch (err) {
      alert('Upload failed: ' + err.message)
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  const handleDelete = async () => {
    if (!currentStatement) return
    const deletedId = currentStatement.id
    const nextId = currentIndex < statements.length - 1
      ? statements[currentIndex + 1].id
      : currentIndex > 0
        ? statements[currentIndex - 1].id
        : null

    // Optimistic: remove from UI immediately
    setStatements(prev => prev.filter(s => s.id !== deletedId))
    setCurrentId(nextId)
    setTransactions([])
    setDeleteConfirm(false)

    try {
      await fetch(`${API}/statements/${deletedId}`, { method: 'DELETE' })
    } catch {
      // Revert on failure
      await fetchStatements()
    }
  }

  const updateTransaction = (txId, field, value, immediate = false) => {
    setTransactions(prev => {
      const old = prev.find(t => t.id === txId)
      if (old) prevValues.current[`${txId}-${field}`] = old[field]
      return prev.map(t => t.id === txId ? { ...t, [field]: value } : t)
    })
    const save = async () => {
      try {
        const res = await fetch(`${API}/transactions/${txId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [field]: value || '' }),
        })
        if (!res.ok) throw new Error()
      } catch {
        // Revert on failure
        const prev = prevValues.current[`${txId}-${field}`]
        setTransactions(txs =>
          txs.map(t => t.id === txId ? { ...t, [field]: prev } : t)
        )
      }
    }
    if (immediate) {
      save()
    } else {
      debounce(`${txId}-${field}`, save)
    }
  }

  const formatDate = (d) => {
    if (!d) return ''
    const date = new Date(d + 'T00:00:00')
    return date.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const formatMoney = (amt) => {
    if (amt == null) return ''
    return new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(amt)
  }

  const formatUploadDate = (d) => {
    if (!d) return ''
    return new Date(d).toLocaleDateString('en-CA', {
      month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
    })
  }

  const statusLabel = (s) => {
    const map = { unmatched: 'No receipt', matched_sure: 'Matched', matched_unsure: 'Unsure', ignored: 'Ignored' }
    return map[s] || 'No receipt'
  }

  if (loadingStatements) {
    return <div className="app"><div className="loading">Loading...</div></div>
  }

  return (
    <div className="app">
      <header>
        <h1>Kothari Group Expenses</h1>
      </header>

      <div className="toolbar">
        <div className="nav-group">
          <button className="btn" disabled={currentIndex >= statements.length - 1} onClick={goOlder}>
            &larr; Older
          </button>

          <div className="statement-info">
            {currentStatement ? (
              <>
                <span className="statement-name">{currentStatement.filename}</span>
                <span className="statement-meta">
                  {currentStatement.transaction_count} transactions &middot; {formatMoney(currentStatement.total_amount)} &middot; {formatUploadDate(currentStatement.uploaded_at)}
                </span>
                <span className="statement-counter">
                  {currentIndex + 1} of {statements.length}
                </span>
              </>
            ) : (
              <span className="no-statements">No statements yet</span>
            )}
          </div>

          <button className="btn" disabled={currentIndex <= 0} onClick={goNewer}>
            Newer &rarr;
          </button>
        </div>

        <div className="action-group">
          <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} hidden />
          <button className="btn btn-primary" onClick={() => fileRef.current.click()} disabled={uploading}>
            {uploading ? 'Uploading...' : '+ Upload Statement'}
          </button>
          {currentStatement && !deleteConfirm && (
            <button className="btn btn-danger" onClick={() => setDeleteConfirm(true)}>Delete</button>
          )}
          {deleteConfirm && (
            <div className="confirm-delete">
              <span>Delete this statement?</span>
              <button className="btn btn-danger" onClick={handleDelete}>Yes, delete</button>
              <button className="btn" onClick={() => setDeleteConfirm(false)}>Cancel</button>
            </div>
          )}
        </div>
      </div>

      {currentStatement && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Merchant</th>
                <th>Description</th>
                <th className="amount-col">Amount</th>
                <th className="amount-col">Tax</th>
                <th>Company</th>
                <th>GL Code</th>
                <th>Receipt</th>
              </tr>
            </thead>
            <tbody>
              {loadingTx ? (
                <ShimmerRows />
              ) : transactions.length === 0 ? (
                <tr><td colSpan={8} className="empty-cell">No transactions in this statement.</td></tr>
              ) : (
                transactions.map(tx => (
                  <tr key={tx.id} className={tx.amount_cad < 0 ? 'credit-row' : ''}>
                    <td className="date-cell">{formatDate(tx.transaction_date)}</td>
                    <td>
                      <input
                        type="text"
                        value={tx.merchant || ''}
                        onChange={e => updateTransaction(tx.id, 'merchant', e.target.value)}
                        className="cell-input"
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        value={tx.description || ''}
                        onChange={e => updateTransaction(tx.id, 'description', e.target.value)}
                        className="cell-input"
                      />
                    </td>
                    <td className="amount-cell">
                      {formatMoney(tx.amount_cad)}
                      {tx.foreign_amount != null && (
                        <span className="foreign-tag">
                          {tx.foreign_amount.toFixed(2)} {tx.foreign_currency}
                        </span>
                      )}
                    </td>
                    <td className="amount-cell tax-cell">
                      {tx.tax_amount != null ? formatMoney(tx.tax_amount) : <span className="empty-dash">&mdash;</span>}
                    </td>
                    <td>
                      <select
                        value={tx.company_id || ''}
                        onChange={e => updateTransaction(tx.id, 'company_id', e.target.value, true)}
                        className="cell-select"
                      >
                        <option value="">—</option>
                        {companies.map(c => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <select
                        value={tx.gl_code_id || ''}
                        onChange={e => updateTransaction(tx.id, 'gl_code_id', e.target.value, true)}
                        className="cell-select"
                      >
                        <option value="">—</option>
                        {glCodes.map(g => (
                          <option key={g.id} value={g.id}>{g.code} — {g.name}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <span className={`receipt-badge ${tx.match_status || 'unmatched'}`}>
                        {statusLabel(tx.match_status)}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {!currentStatement && (
        <div className="empty">Upload an Amex CSV to get started.</div>
      )}
    </div>
  )
}

export default App
