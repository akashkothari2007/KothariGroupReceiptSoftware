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

function ShimmerCards({ count = 6 }) {
  return (
    <div className="receipts-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="receipt-card receipt-card-shimmer">
          <div className="shimmer-block shimmer-icon" />
          <div className="shimmer-block shimmer-line" />
          <div className="shimmer-block shimmer-line-short" />
          <div className="shimmer-block shimmer-line-short" />
        </div>
      ))}
    </div>
  )
}

function ReceiptDetailModal({ receipt, onClose, onUpdate }) {
  const [fileUrl, setFileUrl] = useState(null)
  const [loadingUrl, setLoadingUrl] = useState(false)
  const [fields, setFields] = useState({})
  const debounce = useDebounce()

  useEffect(() => {
    if (!receipt) return
    setFields({
      merchant_name: receipt.merchant_name || '',
      receipt_date: receipt.receipt_date || '',
      subtotal: receipt.subtotal != null ? String(receipt.subtotal) : '',
      tax_amount: receipt.tax_amount != null ? String(receipt.tax_amount) : '',
      tax_type: receipt.tax_type || '',
      total_amount: receipt.total_amount != null ? String(receipt.total_amount) : '',
      country: receipt.country || '',
    })
    setLoadingUrl(true)
    setFileUrl(null)
    fetch(`${API}/receipts/${receipt.id}/url`)
      .then(r => r.json())
      .then(data => setFileUrl(data.url))
      .catch(() => setFileUrl(null))
      .finally(() => setLoadingUrl(false))
  }, [receipt])

  if (!receipt) return null

  const handleChange = (field, value) => {
    setFields(prev => ({ ...prev, [field]: value }))
    const payload = { [field]: value || '' }
    // Convert numeric fields
    if (['subtotal', 'tax_amount', 'total_amount'].includes(field) && value !== '') {
      const num = parseFloat(value)
      if (!isNaN(num)) payload[field] = num
      else return // don't save invalid numbers
    }
    debounce(`receipt-${receipt.id}-${field}`, async () => {
      try {
        await fetch(`${API}/receipts/${receipt.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        onUpdate(receipt.id, field, value)
      } catch {}
    })
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title-row">
            <h2 className="modal-title">{receipt.file_name || 'Receipt'}</h2>
            <ProcessingDot status={receipt.processing_status} />
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          <div className="receipt-preview">
            {loadingUrl ? (
              <div className="receipt-preview-placeholder">
                <div className="shimmer-block" style={{ width: '100%', height: 200, borderRadius: 8 }} />
              </div>
            ) : fileUrl ? (
              receipt.file_type && receipt.file_type.includes('pdf') ? (
                <iframe src={fileUrl} className="receipt-pdf-embed" title={receipt.file_name} />
              ) : (
                <img src={fileUrl} alt={receipt.file_name} className="receipt-image" />
              )
            ) : (
              <div className="receipt-preview-placeholder">
                <span className="receipt-icon-large">?</span>
                <span className="receipt-preview-label">No file available</span>
              </div>
            )}
          </div>

          <div className="receipt-meta-list">
            <div className="meta-row">
              <span className="meta-label">Merchant</span>
              <input className="meta-input" value={fields.merchant_name} onChange={e => handleChange('merchant_name', e.target.value)} placeholder="—" />
            </div>
            <div className="meta-row">
              <span className="meta-label">Receipt date</span>
              <input className="meta-input" type="date" value={fields.receipt_date} onChange={e => handleChange('receipt_date', e.target.value)} />
            </div>
            <div className="meta-row">
              <span className="meta-label">Subtotal</span>
              <input className="meta-input meta-input-num" value={fields.subtotal} onChange={e => handleChange('subtotal', e.target.value)} placeholder="—" />
            </div>
            <div className="meta-row">
              <span className="meta-label">Tax amount</span>
              <input className="meta-input meta-input-num" value={fields.tax_amount} onChange={e => handleChange('tax_amount', e.target.value)} placeholder="—" />
            </div>
            <div className="meta-row">
              <span className="meta-label">Tax type</span>
              <select className="meta-select" value={fields.tax_type} onChange={e => handleChange('tax_type', e.target.value)}>
                <option value="">—</option>
                <option value="HST">HST</option>
                <option value="GST">GST</option>
                <option value="GST+PST">GST+PST</option>
                <option value="none">None</option>
              </select>
            </div>
            <div className="meta-row">
              <span className="meta-label">Total amount</span>
              <input className="meta-input meta-input-num" value={fields.total_amount} onChange={e => handleChange('total_amount', e.target.value)} placeholder="—" />
            </div>
            <div className="meta-row">
              <span className="meta-label">Country</span>
              <input className="meta-input" value={fields.country} onChange={e => handleChange('country', e.target.value)} placeholder="CA" style={{ maxWidth: 80 }} />
            </div>
            <div className="meta-row">
              <span className="meta-label">Source</span>
              <span className="meta-value">{receipt.source || '—'}</span>
            </div>
            <div className="meta-row">
              <span className="meta-label">Uploaded</span>
              <span className="meta-value">{receipt.created_at ? new Date(receipt.created_at).toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}</span>
            </div>
            {receipt.transaction_id && (
              <div className="meta-row meta-row-linked">
                <span className="meta-label">Linked transaction</span>
                <span className="meta-value meta-value-linked">
                  {receipt.tx_merchant || 'Transaction'} — {receipt.tx_amount != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(receipt.tx_amount) : ''}
                  {receipt.tx_date ? ` (${receipt.tx_date})` : ''}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ProcessingDot({ status }) {
  const config = {
    pending: { color: '#9ca3af', label: 'Pending' },
    processing: { color: '#eab308', label: 'Processing' },
    completed: { color: '#22c55e', label: 'Completed' },
    failed: { color: '#ef4444', label: 'Failed' },
  }
  const c = config[status] || config.pending
  return (
    <span className="processing-dot-wrapper" title={c.label}>
      <span className="processing-dot" style={{ background: c.color }} />
      <span className="processing-dot-label" style={{ color: c.color }}>{c.label}</span>
    </span>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState('statements')

  // ── Statements state ──
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

  // ── Receipts state ──
  const [receipts, setReceipts] = useState([])
  const [loadingReceipts, setLoadingReceipts] = useState(false)
  const [receiptsFetched, setReceiptsFetched] = useState(false)
  const [uploadingReceipt, setUploadingReceipt] = useState(false)
  const [selectedReceipt, setSelectedReceipt] = useState(null)
  const [receiptMenuOpen, setReceiptMenuOpen] = useState(null)
  const [receiptSort, setReceiptSort] = useState('date') // 'date' | 'matched' | 'unmatched'
  const [linkingTxId, setLinkingTxId] = useState(null) // tx id with open receipt picker
  const [receiptPreviewTxId, setReceiptPreviewTxId] = useState(null) // tx id showing receipt popup
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null)
  const [receiptPreviewLoading, setReceiptPreviewLoading] = useState(false)
  const receiptFileRef = useRef()

  const currentIndex = statements.findIndex(s => s.id === currentId)
  const currentStatement = currentIndex >= 0 ? statements[currentIndex] : null

  // ── Statements data ──
  const fetchStatements = useCallback(async () => {
    const res = await fetch(`${API}/statements`)
    const data = await res.json()
    setStatements(data)
    setLoadingStatements(false)
    return data
  }, [])

  const fetchTransactions = useCallback(async (statementId, silent = false) => {
    if (!silent) { setLoadingTx(true); setTransactions([]) }
    const res = await fetch(`${API}/statements/${statementId}/transactions`)
    const data = await res.json()
    setTransactions(data)
    if (!silent) setLoadingTx(false)
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

  // ── Receipts data (lazy load) ──
  const fetchReceipts = useCallback(async () => {
    setLoadingReceipts(true)
    try {
      const res = await fetch(`${API}/receipts`)
      const data = await res.json()
      setReceipts(data)
    } catch (err) {
      console.error('Failed to fetch receipts:', err)
    }
    setLoadingReceipts(false)
    setReceiptsFetched(true)
  }, [])

  useEffect(() => {
    if (!receiptsFetched) fetchReceipts()
  }, [receiptsFetched, fetchReceipts])

  // Poll for status updates when any receipts are still processing
  useEffect(() => {
    const hasInFlight = receipts.some(r => r.processing_status === 'pending' || r.processing_status === 'processing')
    if (!hasInFlight || activeTab !== 'receipts') return
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API}/receipts`)
        const data = await res.json()
        setReceipts(data)
        // Sync selectedReceipt if open
        setSelectedReceipt(prev => {
          if (!prev) return prev
          const updated = data.find(r => r.id === prev.id)
          return updated || prev
        })
      } catch {}
    }, 3000)
    return () => clearInterval(interval)
  }, [receipts, activeTab])

  // Close receipt menu / link dropdown on outside click
  useEffect(() => {
    if (receiptMenuOpen === null && linkingTxId === null) return
    const handler = () => { setReceiptMenuOpen(null); setLinkingTxId(null) }
    document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [receiptMenuOpen, linkingTxId])

  // ── Statements handlers ──
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

    setStatements(prev => prev.filter(s => s.id !== deletedId))
    setCurrentId(nextId)
    setTransactions([])
    setDeleteConfirm(false)

    try {
      await fetch(`${API}/statements/${deletedId}`, { method: 'DELETE' })
    } catch {
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

  // ── Match handlers ──
  const handleManualMatch = async (txId, receiptId) => {
    setLinkingTxId(null)
    const receipt = receipts.find(r => r.id === receiptId)
    // Optimistic update
    setTransactions(prev => prev.map(t => t.id === txId ? {
      ...t, matched_receipt_id: receiptId, match_status: 'matched_sure',
      receipt_file_name: receipt?.file_name, receipt_merchant: receipt?.merchant_name,
    } : t))
    setReceipts(prev => prev.map(r => r.id === receiptId ? { ...r, match_status: 'matched_sure' } : r))
    try {
      const res = await fetch(`${API}/transactions/${txId}/match`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_id: receiptId }),
      })
      if (!res.ok) throw new Error()
      // Silently refresh to get updated tax_amount from server
      if (currentId) fetchTransactions(currentId, true)
    } catch {
      // Revert
      setTransactions(prev => prev.map(t => t.id === txId ? {
        ...t, matched_receipt_id: null, match_status: 'unmatched',
        receipt_file_name: null, receipt_merchant: null,
      } : t))
      setReceipts(prev => prev.map(r => r.id === receiptId ? { ...r, match_status: 'unmatched' } : r))
    }
  }

  const handleUnmatch = async (txId) => {
    const tx = transactions.find(t => t.id === txId)
    const oldReceiptId = tx?.matched_receipt_id
    // Optimistic update
    setTransactions(prev => prev.map(t => t.id === txId ? {
      ...t, matched_receipt_id: null, match_status: 'unmatched', tax_amount: null,
      receipt_file_name: null, receipt_merchant: null,
    } : t))
    if (oldReceiptId) {
      setReceipts(prev => prev.map(r => r.id === oldReceiptId ? { ...r, match_status: 'unmatched' } : r))
    }
    setReceiptPreviewTxId(null)
    try {
      const res = await fetch(`${API}/transactions/${txId}/match`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
    } catch {
      // Revert — just refetch
      if (currentId) fetchTransactions(currentId)
      fetchReceipts()
    }
  }

  const showReceiptPreview = async (txId, receiptId) => {
    if (receiptPreviewTxId === txId) { setReceiptPreviewTxId(null); return }
    setReceiptPreviewTxId(txId)
    setReceiptPreviewUrl(null)
    setReceiptPreviewLoading(true)
    try {
      const res = await fetch(`${API}/receipts/${receiptId}/url`)
      const data = await res.json()
      setReceiptPreviewUrl(data.url)
    } catch { setReceiptPreviewUrl(null) }
    setReceiptPreviewLoading(false)
  }

  // ── Receipts handlers ──
  const handleReceiptUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploadingReceipt(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await fetch(`${API}/receipts/upload`, { method: 'POST', body: form })
      if (!res.ok) throw new Error('Upload failed')
      const data = await res.json()
      data.processing_status = 'processing'
      setReceipts(prev => [data, ...prev])
    } catch (err) {
      alert('Receipt upload failed: ' + err.message)
    }
    setUploadingReceipt(false)
    receiptFileRef.current.value = ''
  }

  const handleReceiptDelete = async (receiptId) => {
    const removed = receipts.find(r => r.id === receiptId)
    setReceipts(prev => prev.filter(r => r.id !== receiptId))
    setReceiptMenuOpen(null)
    if (selectedReceipt && selectedReceipt.id === receiptId) {
      setSelectedReceipt(null)
    }

    try {
      const res = await fetch(`${API}/receipts/${receiptId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
    } catch {
      setReceipts(prev => [...prev, removed].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)))
    }
  }

  // ── Formatters ──
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

  const receiptMatchLabel = (s) => {
    const map = { unmatched: 'No match', matched_sure: 'Matched', matched_unsure: 'Unsure', ignored: 'Ignored' }
    return map[s] || 'No match'
  }

  const fileTypeIcon = (type) => {
    if (!type) return 'FILE'
    if (type.includes('pdf')) return 'PDF'
    return 'IMG'
  }

  if (loadingStatements) {
    return <div className="app"><div className="loading">Loading...</div></div>
  }

  return (
    <div className="app">
      <header>
        <h1>Kothari Group Expenses</h1>
      </header>

      <div className="tabs">
        <button
          className={`tab ${activeTab === 'statements' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('statements')}
        >
          Statements
        </button>
        <button
          className={`tab ${activeTab === 'receipts' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('receipts')}
        >
          Receipts
        </button>
      </div>

      {/* ── Statements Tab ── */}
      {activeTab === 'statements' && (
        <>
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
                        <td className="receipt-cell">
                          {tx.matched_receipt_id ? (
                            <div className="receipt-matched">
                              <span
                                className={`receipt-badge ${tx.match_status || 'matched_sure'} receipt-badge-clickable`}
                                onClick={() => showReceiptPreview(tx.id, tx.matched_receipt_id)}
                                title="Click to preview receipt"
                              >
                                {tx.receipt_merchant || tx.receipt_file_name || 'Matched'}
                              </span>
                              <button
                                className="receipt-unmatch-btn"
                                onClick={() => handleUnmatch(tx.id)}
                                title="Remove match"
                              >&times;</button>
                              {receiptPreviewTxId === tx.id && (
                                <div className="receipt-popup" onClick={e => e.stopPropagation()}>
                                  <div className="receipt-popup-header">
                                    <span className="receipt-popup-title">{tx.receipt_merchant || tx.receipt_file_name}</span>
                                    <button className="modal-close" onClick={() => setReceiptPreviewTxId(null)}>&times;</button>
                                  </div>
                                  {receiptPreviewLoading ? (
                                    <div className="shimmer-block" style={{ width: '100%', height: 200, borderRadius: 8 }} />
                                  ) : receiptPreviewUrl ? (
                                    <img src={receiptPreviewUrl} alt="receipt" className="receipt-popup-img" />
                                  ) : (
                                    <div className="receipt-preview-placeholder" style={{ padding: 20 }}>No preview</div>
                                  )}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="receipt-link-wrapper">
                              <button
                                className="receipt-link-btn"
                                onClick={e => { e.stopPropagation(); setLinkingTxId(linkingTxId === tx.id ? null : tx.id) }}
                              >
                                Link
                              </button>
                              {linkingTxId === tx.id && (
                                <div className="receipt-link-dropdown" onClick={e => e.stopPropagation()}>
                                  {receipts.filter(r => !r.match_status || r.match_status === 'unmatched').length === 0 ? (
                                    <div className="receipt-link-empty">No unmatched receipts</div>
                                  ) : (
                                    receipts.filter(r => !r.match_status || r.match_status === 'unmatched').map(r => (
                                      <button
                                        key={r.id}
                                        className="receipt-link-option"
                                        onClick={() => handleManualMatch(tx.id, r.id)}
                                      >
                                        <span className="receipt-link-name">{r.merchant_name || r.file_name || 'Untitled'}</span>
                                        <span className="receipt-link-amount">{r.total_amount != null ? formatMoney(r.total_amount) : ''}</span>
                                      </button>
                                    ))
                                  )}
                                </div>
                              )}
                            </div>
                          )}
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
        </>
      )}

      {/* ── Receipts Tab ── */}
      {activeTab === 'receipts' && (
        <div className="receipts-tab">
          <div className="receipts-toolbar">
            <input
              ref={receiptFileRef}
              type="file"
              accept="image/jpeg,image/png,application/pdf,image/heic,image/heif"
              onChange={handleReceiptUpload}
              hidden
            />
            <button
              className="btn btn-primary"
              onClick={() => receiptFileRef.current.click()}
              disabled={uploadingReceipt}
            >
              {uploadingReceipt ? 'Uploading...' : '+ Upload Receipt'}
            </button>
            <span className="receipts-count">
              {!loadingReceipts && `${receipts.length} receipt${receipts.length !== 1 ? 's' : ''}`}
            </span>
            <select
              className="receipt-sort-select"
              value={receiptSort}
              onChange={e => setReceiptSort(e.target.value)}
            >
              <option value="date">Newest first</option>
              <option value="unmatched">Unmatched first</option>
              <option value="matched">Matched first</option>
            </select>
          </div>

          {loadingReceipts ? (
            <ShimmerCards />
          ) : receipts.length === 0 ? (
            <div className="empty">No receipts yet. Upload one to get started.</div>
          ) : (
            <div className="receipts-grid">
              {[...receipts].sort((a, b) => {
                if (receiptSort === 'matched') {
                  const aM = (a.match_status === 'matched_sure' || a.match_status === 'matched_unsure') ? 0 : 1
                  const bM = (b.match_status === 'matched_sure' || b.match_status === 'matched_unsure') ? 0 : 1
                  if (aM !== bM) return aM - bM
                } else if (receiptSort === 'unmatched') {
                  const aM = (!a.match_status || a.match_status === 'unmatched') ? 0 : 1
                  const bM = (!b.match_status || b.match_status === 'unmatched') ? 0 : 1
                  if (aM !== bM) return aM - bM
                }
                return new Date(b.created_at) - new Date(a.created_at)
              }).map(r => (
                <div
                  key={r.id}
                  className="receipt-card"
                  onClick={() => setSelectedReceipt(r)}
                >
                  <div className="receipt-card-top">
                    <div className="receipt-card-top-left">
                      <div className={`receipt-type-icon ${fileTypeIcon(r.file_type).toLowerCase()}`}>
                        {fileTypeIcon(r.file_type)}
                      </div>
                      <ProcessingDot status={r.processing_status} />
                    </div>
                    <div
                      className="receipt-menu-trigger"
                      onClick={e => {
                        e.stopPropagation()
                        setReceiptMenuOpen(receiptMenuOpen === r.id ? null : r.id)
                      }}
                    >
                      &#x22EF;
                    </div>
                    {receiptMenuOpen === r.id && (
                      <div className="receipt-menu" onClick={e => e.stopPropagation()}>
                        <button
                          className="receipt-menu-item receipt-menu-delete"
                          onClick={() => handleReceiptDelete(r.id)}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>

                  <div className="receipt-card-body">
                    <div className="receipt-card-name" title={r.file_name}>
                      {r.file_name || 'Untitled'}
                    </div>
                    <div className="receipt-card-detail">
                      <span className="receipt-card-label">Merchant</span>
                      <span>{r.merchant_name || '—'}</span>
                    </div>
                    <div className="receipt-card-detail">
                      <span className="receipt-card-label">Date</span>
                      <span>{r.receipt_date ? formatDate(r.receipt_date) : '—'}</span>
                    </div>
                    <div className="receipt-card-detail">
                      <span className="receipt-card-label">Amount</span>
                      <span>{r.total_amount != null ? formatMoney(r.total_amount) : '—'}</span>
                    </div>
                  </div>

                  <div className="receipt-card-footer">
                    <span className={`receipt-badge ${r.match_status || 'unmatched'}`}>
                      {receiptMatchLabel(r.match_status)}
                    </span>
                    <span className="receipt-card-date">
                      {r.created_at ? formatUploadDate(r.created_at) : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Receipt Detail Modal ── */}
      {selectedReceipt && (
        <ReceiptDetailModal
          receipt={selectedReceipt}
          onClose={() => setSelectedReceipt(null)}
          onUpdate={(id, field, value) => {
            const parsed = ['subtotal', 'tax_amount', 'total_amount'].includes(field) && value !== ''
              ? parseFloat(value) : value
            setReceipts(prev => prev.map(r => r.id === id ? { ...r, [field]: parsed } : r))
            setSelectedReceipt(prev => prev && prev.id === id ? { ...prev, [field]: parsed } : prev)
          }}
        />
      )}
    </div>
  )
}

export default App
