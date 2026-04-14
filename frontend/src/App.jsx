import { useState, useEffect, useCallback, useRef } from 'react'
import './App.css'
import { API, authFetch, getReceiptUrl } from './utils/api'
import { useDebounce } from './hooks/useDebounce'
import { useAuth } from './hooks/useAuth'
import { StatementsTab } from './components/StatementsTab'
import { ReceiptsTab } from './components/ReceiptsTab'
import { ReceiptDetailModal } from './components/ReceiptDetailModal'
import { SettingsTab } from './components/SettingsTab'

function App() {
  const { signOut, userRole } = useAuth()
  const [activeTab, setActiveTab] = useState('statements')

  // ── Statements state ──
  const [statements, setStatements] = useState([])
  const [currentId, setCurrentId] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [glCodes, setGlCodes] = useState([])
  const [companies, setCompanies] = useState([])
  const [expenseTypes, setExpenseTypes] = useState([])
  const [cardAccounts, setCardAccounts] = useState([])
  const [selectedAccountId, setSelectedAccountId] = useState(null)
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
  const [receiptFilter, setReceiptFilter] = useState({ unmatched: true, unsure: true, matched: false })
  const [linkingTxId, setLinkingTxId] = useState(null) // tx id with open receipt picker
  const [receiptPreviewTxId, setReceiptPreviewTxId] = useState(null)
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null)
  const [receiptPreviewLoading, setReceiptPreviewLoading] = useState(false)
  const receiptFileRef = useRef()

  const currentIndex = statements.findIndex(s => s.id === currentId)
  const currentStatement = currentIndex >= 0 ? statements[currentIndex] : null

  // ── Statements data ──
  const fetchStatements = useCallback(async (accountId) => {
    const aid = accountId || selectedAccountId
    const url = aid ? `${API}/statements?card_account_id=${aid}` : `${API}/statements`
    const res = await authFetch(url)
    const data = await res.json()
    setStatements(data)
    setLoadingStatements(false)
    return data
  }, [selectedAccountId])

  const fetchTransactions = useCallback(async (statementId, silent = false) => {
    if (!silent) { setLoadingTx(true); setTransactions([]) }
    const res = await authFetch(`${API}/statements/${statementId}/transactions`)
    const data = await res.json()
    setTransactions(data)
    if (!silent) setLoadingTx(false)
  }, [])

  const fetchCardAccounts = useCallback(async () => {
    const res = await authFetch(`${API}/lookups/card-accounts`)
    const data = await res.json()
    setCardAccounts(data)
    return data
  }, [])

  const refreshLookups = useCallback(() => {
    authFetch(`${API}/lookups/gl-codes`).then(r => r.json()).then(setGlCodes)
    authFetch(`${API}/lookups/companies`).then(r => r.json()).then(setCompanies)
    authFetch(`${API}/lookups/expense-types`).then(r => r.json()).then(setExpenseTypes)
    fetchCardAccounts()
  }, [fetchCardAccounts])

  useEffect(() => {
    fetchCardAccounts().then(accounts => {
      if (accounts.length > 0) {
        setSelectedAccountId(accounts[0].id)
      } else {
        setLoadingStatements(false)
      }
    })
    authFetch(`${API}/lookups/gl-codes`).then(r => r.json()).then(setGlCodes)
    authFetch(`${API}/lookups/companies`).then(r => r.json()).then(setCompanies)
    authFetch(`${API}/lookups/expense-types`).then(r => r.json()).then(setExpenseTypes)
  }, [fetchCardAccounts])

  // Fetch statements when selected account changes
  useEffect(() => {
    if (selectedAccountId) {
      setCurrentId(null)
      setTransactions([])
      fetchStatements(selectedAccountId).then(data => {
        if (data.length > 0) setCurrentId(data[0].id)
      })
    }
  }, [selectedAccountId, fetchStatements])

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
      const res = await authFetch(`${API}/receipts`)
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
        const res = await authFetch(`${API}/receipts`)
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
  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    if (!selectedAccountId) {
      alert('Please select a card account first.')
      return
    }
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    try {
      const res = await authFetch(`${API}/statements/upload?card_account_id=${selectedAccountId}`, { method: 'POST', body: form })
      const data = await res.json()
      await fetchStatements(selectedAccountId)
      setCurrentId(data.statement_id)
    } catch (err) {
      alert('Upload failed: ' + err.message)
    }
    setUploading(false)
    fileRef.current.value = ''
  }

  // Poll for background matching completion on statements
  useEffect(() => {
    const isMatching = statements.some(s => s.matching_status === 'matching')
    if (!isMatching) return
    const aid = selectedAccountId
    if (!aid) return
    const interval = setInterval(async () => {
      try {
        const res = await authFetch(`${API}/statements?card_account_id=${aid}`)
        const data = await res.json()
        setStatements(data)
        // If matching just finished for current statement, refresh transactions
        const prev = statements.find(s => s.id === currentId)
        const curr = data.find(s => s.id === currentId)
        if (prev?.matching_status === 'matching' && curr?.matching_status !== 'matching') {
          if (currentId) fetchTransactions(currentId, true)
          fetchReceipts()
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  }, [statements, currentId, selectedAccountId, fetchTransactions, fetchReceipts])

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
      await authFetch(`${API}/statements/${deletedId}`, { method: 'DELETE' })
      fetchReceipts()  // refresh receipts since their matches were cleared
    } catch {
      await fetchStatements(selectedAccountId)
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
        const res = await authFetch(`${API}/transactions/${txId}`, {
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
    const tx = transactions.find(t => t.id === txId)
    setReceipts(prev => prev.map(r => r.id === receiptId ? {
      ...r, match_status: 'matched_sure', transaction_id: txId,
      tx_merchant: tx?.merchant, tx_amount: tx?.amount_cad, tx_date: tx?.transaction_date,
    } : r))
    try {
      const res = await authFetch(`${API}/transactions/${txId}/match`, {
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
      setReceipts(prev => prev.map(r => r.id === receiptId ? {
        ...r, match_status: 'unmatched', transaction_id: null,
        tx_merchant: null, tx_amount: null, tx_date: null,
      } : r))
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
      setReceipts(prev => prev.map(r => r.id === oldReceiptId ? {
        ...r, match_status: 'unmatched', transaction_id: null,
        tx_merchant: null, tx_amount: null, tx_date: null,
      } : r))
    }
    setReceiptPreviewTxId(null)
    try {
      const res = await authFetch(`${API}/transactions/${txId}/match`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
    } catch {
      // Revert — just refetch
      if (currentId) fetchTransactions(currentId)
      fetchReceipts()
    }
  }

  const showReceiptPreview = async (txId, receiptId) => {
    if (receiptPreviewTxId === txId) {
      setReceiptPreviewTxId(null)
      return
    }
    setReceiptPreviewTxId(txId)
    setReceiptPreviewUrl(null)
    setReceiptPreviewLoading(true)
    try {
      setReceiptPreviewUrl(await getReceiptUrl(receiptId))
    } catch {
      setReceiptPreviewUrl(null)
    }
    setReceiptPreviewLoading(false)
  }

  // ── Receipts handlers ──
  const handleReceiptUpload = async (e) => {
    const files = Array.from(e.target.files)
    if (!files.length) return
    setUploadingReceipt(true)
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      try {
        const res = await authFetch(`${API}/receipts/upload`, { method: 'POST', body: form })
        if (!res.ok) throw new Error(`Upload failed: ${file.name}`)
        const data = await res.json()
        data.processing_status = 'processing'
        setReceipts(prev => [data, ...prev])
      } catch (err) {
        alert(err.message)
      }
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
      const res = await authFetch(`${API}/receipts/${receiptId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error()
      if (currentId) fetchTransactions(currentId, true)  // refresh transactions since match was cleared
    } catch {
      setReceipts(prev => [...prev, removed].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)))
    }
  }

  const handleReceiptRetry = async (receiptId) => {
    setReceiptMenuOpen(null)
    setReceipts(prev => prev.map(r => r.id === receiptId ? { ...r, processing_status: 'processing' } : r))
    try {
      const res = await authFetch(`${API}/receipts/${receiptId}/retry`, { method: 'POST' })
      if (!res.ok) throw new Error()
    } catch {
      setReceipts(prev => prev.map(r => r.id === receiptId ? { ...r, processing_status: 'failed' } : r))
    }
  }

  const handleReceiptUnmatch = async (receiptId) => {
    // Optimistic: clear match locally
    setReceipts(prev => prev.map(r => r.id === receiptId
      ? { ...r, transaction_id: null, match_status: 'unmatched', tx_merchant: null, tx_amount: null, tx_date: null }
      : r
    ))
    setSelectedReceipt(prev => prev && prev.id === receiptId
      ? { ...prev, transaction_id: null, match_status: 'unmatched', tx_merchant: null, tx_amount: null, tx_date: null }
      : prev
    )
    // Also refresh transactions if viewing a statement
    try {
      await authFetch(`${API}/receipts/${receiptId}/match`, { method: 'DELETE' })
      if (currentId) fetchTransactions(currentId, true)
    } catch {}
  }

  const handleReceiptRematch = async (receiptId) => {
    try {
      await authFetch(`${API}/receipts/${receiptId}/rematch`, { method: 'POST' })
      // Poll receipts to pick up the new match
      setTimeout(async () => {
        try {
          const res = await authFetch(`${API}/receipts`)
          const data = await res.json()
          setReceipts(data)
          setSelectedReceipt(prev => {
            if (!prev || prev.id !== receiptId) return prev
            return data.find(r => r.id === receiptId) || prev
          })
          if (currentId) fetchTransactions(currentId, true)
        } catch {}
      }, 2000)
    } catch {}
  }

  const handleConfirmMatch = async (receiptId) => {
    setReceipts(prev => prev.map(r => r.id === receiptId ? { ...r, match_status: 'matched_sure' } : r))
    setSelectedReceipt(prev => prev && prev.id === receiptId ? { ...prev, match_status: 'matched_sure' } : prev)
    setTransactions(prev => prev.map(t => t.matched_receipt_id === receiptId ? { ...t, match_status: 'matched_sure' } : t))
    try {
      await authFetch(`${API}/receipts/${receiptId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_status: 'matched_sure' }),
      })
    } catch {}
  }

  if (loadingStatements) {
    return <div className="app"><div className="loading">Loading...</div></div>
  }

  return (
    <div className="app">
      <header>
        <h1>Kothari Group Expenses</h1>
        <button className="btn sign-out-btn" onClick={signOut}>Sign out</button>
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
        <button
          className={`tab ${activeTab === 'settings' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </div>

      {activeTab === 'statements' && (
        <StatementsTab
          statements={statements}
          currentIndex={currentIndex}
          currentStatement={currentStatement}
          setCurrentId={setCurrentId}
          uploading={uploading}
          setUploading={setUploading}
          deleteConfirm={deleteConfirm}
          setDeleteConfirm={setDeleteConfirm}
          transactions={transactions}
          loadingTx={loadingTx}
          glCodes={glCodes}
          companies={companies}
          expenseTypes={expenseTypes}
          receipts={receipts}
          fetchStatements={fetchStatements}
          fetchTransactions={fetchTransactions}
          currentId={currentId}
          updateTransaction={updateTransaction}
          handleManualMatch={handleManualMatch}
          handleUnmatch={handleUnmatch}
          handleConfirmMatch={handleConfirmMatch}
          showReceiptPreview={showReceiptPreview}
          receiptPreviewTxId={receiptPreviewTxId}
          receiptPreviewUrl={receiptPreviewUrl}
          receiptPreviewLoading={receiptPreviewLoading}
          setReceiptPreviewTxId={setReceiptPreviewTxId}
          linkingTxId={linkingTxId}
          setLinkingTxId={setLinkingTxId}
          handleUpload={handleUpload}
          handleDelete={handleDelete}
          fileRef={fileRef}
          cardAccounts={cardAccounts}
          selectedAccountId={selectedAccountId}
          setSelectedAccountId={setSelectedAccountId}
          fetchCardAccounts={fetchCardAccounts}
          userRole={userRole}
        />
      )}

      {activeTab === 'receipts' && (
        <ReceiptsTab
          receipts={receipts}
          loadingReceipts={loadingReceipts}
          uploadingReceipt={uploadingReceipt}
          receiptFilter={receiptFilter}
          setReceiptFilter={setReceiptFilter}
          receiptMenuOpen={receiptMenuOpen}
          setReceiptMenuOpen={setReceiptMenuOpen}
          handleReceiptUpload={handleReceiptUpload}
          handleReceiptDelete={handleReceiptDelete}
          handleReceiptRetry={handleReceiptRetry}
          handleConfirmMatch={handleConfirmMatch}
          setSelectedReceipt={setSelectedReceipt}
          receiptFileRef={receiptFileRef}
        />
      )}

      {activeTab === 'settings' && (
        <SettingsTab
          companies={companies}
          glCodes={glCodes}
          expenseTypes={expenseTypes}
          onRefresh={refreshLookups}
          userRole={userRole}
        />
      )}

      {selectedReceipt && (
        <ReceiptDetailModal
          receipt={selectedReceipt}
          onClose={() => setSelectedReceipt(null)}
          onRetry={(id) => { handleReceiptRetry(id); setSelectedReceipt(null) }}
          onUnmatch={(id) => handleReceiptUnmatch(id)}
          onRematch={(id) => handleReceiptRematch(id)}
          onConfirmMatch={(id) => handleConfirmMatch(id)}
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
