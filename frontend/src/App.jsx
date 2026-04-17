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
  const [receiptsHasMore, setReceiptsHasMore] = useState(false)
  const [receiptsOffset, setReceiptsOffset] = useState(0)
  const [uploadingReceipt, setUploadingReceipt] = useState(false)
  const [selectedReceipt, setSelectedReceipt] = useState(null)
  const [receiptMenuOpen, setReceiptMenuOpen] = useState(null)
  const [receiptFilter, setReceiptFilter] = useState({ unmatched: true, unsure: true, matched: false })
  const [receiptViewMode, setReceiptViewMode] = useState('byMonth')
  const [receiptSearchQuery, setReceiptSearchQuery] = useState('')
  const [linkingTxId, setLinkingTxId] = useState(null)
  const [receiptPreviewTxId, setReceiptPreviewTxId] = useState(null)
  const [receiptPreviewUrl, setReceiptPreviewUrl] = useState(null)
  const [receiptPreviewLoading, setReceiptPreviewLoading] = useState(false)
  const receiptFileRef = useRef()

  // Month picker state (lifted from ReceiptsTab so effects can trigger fetches)
  const now = new Date()
  const [pickerYear, setPickerYear] = useState(now.getFullYear())
  const [pickerMonth, setPickerMonth] = useState(now.getMonth() + 1) // 1-12 for API

  // Statement groups for By Statement view
  const [statementGroups, setStatementGroups] = useState([])
  const [expandedStatements, setExpandedStatements] = useState({}) // { sid: [receipts] }

  // Unmatched receipts for StatementsTab receipt picker
  const [unmatchedReceipts, setUnmatchedReceipts] = useState([])

  const searchTimerRef = useRef(null)

  // ── Receipts cache (stale-while-revalidate) ──
  // Key = URL params string, Value = { receipts, has_more, offset, timestamp }
  const receiptsCacheRef = useRef(new Map())
  const statementGroupsCacheRef = useRef(null) // cached statement groups
  const CACHE_TTL = 5 * 60 * 1000 // 5 min — beyond this, force refresh even for background

  const invalidateReceiptsCache = useCallback(() => {
    receiptsCacheRef.current.clear()
    statementGroupsCacheRef.current = null
    setExpandedStatements({})
  }, [])

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

  // ── Receipts: fetch-per-view ──

  const buildMatchStatusParam = useCallback(() => {
    // For byStatement view, always matched+unsure
    if (receiptViewMode === 'byStatement') return null // handled differently
    const parts = []
    if (receiptFilter.unmatched) parts.push('unmatched')
    if (receiptFilter.unsure) parts.push('unsure')
    if (receiptFilter.matched) parts.push('matched')
    return parts.length > 0 ? parts.join(',') : null
  }, [receiptFilter, receiptViewMode])

  const fetchReceiptsForView = useCallback(async (opts = {}) => {
    const { append = false, offsetOverride, skipCache = false } = opts

    const params = new URLSearchParams()
    const effectiveOffset = offsetOverride !== undefined ? offsetOverride : (append ? receiptsOffset : 0)

    // Search overrides view
    if (receiptSearchQuery.trim()) {
      params.set('q', receiptSearchQuery.trim())
      params.set('limit', '20')
      params.set('offset', String(effectiveOffset))
      const ms = buildMatchStatusParam()
      if (ms) params.set('match_status', ms)
    } else if (receiptViewMode === 'byMonth') {
      params.set('view', 'byMonth')
      params.set('year', String(pickerYear))
      params.set('month', String(pickerMonth))
      const ms = buildMatchStatusParam()
      if (ms) params.set('match_status', ms)
    } else if (receiptViewMode === 'recent') {
      params.set('view', 'recent')
      params.set('limit', '20')
      params.set('offset', String(effectiveOffset))
      const ms = buildMatchStatusParam()
      if (ms) params.set('match_status', ms)
    }

    // byStatement: fetch statement groups instead of receipts
    if (receiptViewMode === 'byStatement' && !receiptSearchQuery.trim()) {
      const cached = statementGroupsCacheRef.current
      if (cached && !skipCache) {
        // Show cached immediately
        setStatementGroups(cached.data)
        setReceipts([])
        setReceiptsHasMore(false)
        setLoadingReceipts(false)
        // Background refresh if stale
        if (Date.now() - cached.timestamp > CACHE_TTL) {
          authFetch(`${API}/receipts/statement-groups`).then(r => r.json()).then(data => {
            statementGroupsCacheRef.current = { data, timestamp: Date.now() }
            setStatementGroups(data)
          }).catch(() => {})
        }
        return
      }
      setLoadingReceipts(true)
      try {
        const res = await authFetch(`${API}/receipts/statement-groups`)
        const data = await res.json()
        statementGroupsCacheRef.current = { data, timestamp: Date.now() }
        setStatementGroups(data)
        setExpandedStatements({})
      } catch (err) {
        console.error('Failed to fetch statement groups:', err)
      }
      setReceipts([])
      setReceiptsHasMore(false)
      setLoadingReceipts(false)
      return
    }

    const cacheKey = params.toString()

    // Check cache for non-append requests
    if (!append && !skipCache) {
      const cached = receiptsCacheRef.current.get(cacheKey)
      if (cached) {
        // Show cached data instantly (no loading spinner)
        setReceipts(cached.receipts)
        setReceiptsHasMore(cached.has_more)
        setReceiptsOffset(cached.offset)
        setLoadingReceipts(false)
        // Background revalidate if older than TTL
        if (Date.now() - cached.timestamp > CACHE_TTL) {
          authFetch(`${API}/receipts?${cacheKey}`).then(r => r.json()).then(data => {
            const entry = { receipts: data.receipts, has_more: data.has_more, offset: data.receipts.length, timestamp: Date.now() }
            receiptsCacheRef.current.set(cacheKey, entry)
            setReceipts(data.receipts)
            setReceiptsHasMore(data.has_more)
            setReceiptsOffset(data.receipts.length)
          }).catch(() => {})
        }
        return
      }
    }

    if (!append) setLoadingReceipts(true)

    try {
      const res = await authFetch(`${API}/receipts?${params.toString()}`)
      const data = await res.json()
      if (append) {
        setReceipts(prev => {
          const merged = [...prev, ...data.receipts]
          // Update cache with the full accumulated list
          receiptsCacheRef.current.set(cacheKey, { receipts: merged, has_more: data.has_more, offset: effectiveOffset + data.receipts.length, timestamp: Date.now() })
          return merged
        })
      } else {
        setReceipts(data.receipts)
        receiptsCacheRef.current.set(cacheKey, { receipts: data.receipts, has_more: data.has_more, offset: data.receipts.length, timestamp: Date.now() })
      }
      setReceiptsHasMore(data.has_more)
      setReceiptsOffset(effectiveOffset + data.receipts.length)
    } catch (err) {
      console.error('Failed to fetch receipts:', err)
    }
    setLoadingReceipts(false)
  }, [receiptViewMode, receiptFilter, pickerYear, pickerMonth, receiptSearchQuery, receiptsOffset, buildMatchStatusParam])

  // Trigger fetch when view, filter, month, or tab changes
  useEffect(() => {
    if (activeTab !== 'receipts') return
    // Don't fetch for search — that's handled by the debounced search effect
    if (receiptSearchQuery.trim()) return
    fetchReceiptsForView()
  }, [receiptViewMode, receiptFilter, pickerYear, pickerMonth, activeTab])

  // Debounced search
  useEffect(() => {
    if (activeTab !== 'receipts') return
    if (!receiptSearchQuery.trim()) return // handled by the main effect above
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    searchTimerRef.current = setTimeout(() => {
      setReceiptsOffset(0)
      fetchReceiptsForView()
    }, 300)
    return () => { if (searchTimerRef.current) clearTimeout(searchTimerRef.current) }
  }, [receiptSearchQuery, activeTab])

  // When search is cleared, the main effect above handles the refetch

  // Load more handler
  const handleLoadMore = useCallback(() => {
    fetchReceiptsForView({ append: true, offsetOverride: receiptsOffset })
  }, [fetchReceiptsForView, receiptsOffset])

  // Expand a statement group (lazy-load receipts)
  const handleExpandStatement = useCallback(async (statementId) => {
    if (expandedStatements[statementId]) return // already loaded
    try {
      const res = await authFetch(`${API}/receipts?statement_id=${statementId}`)
      const data = await res.json()
      setExpandedStatements(prev => ({ ...prev, [statementId]: data.receipts }))
    } catch (err) {
      console.error('Failed to load statement receipts:', err)
    }
  }, [expandedStatements])

  // Fetch unmatched receipts for StatementsTab receipt picker
  const fetchUnmatchedReceipts = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/receipts?match_status=unmatched&limit=200&view=recent`)
      const data = await res.json()
      setUnmatchedReceipts(data.receipts)
    } catch {}
  }, [])

  useEffect(() => {
    fetchUnmatchedReceipts()
  }, [fetchUnmatchedReceipts])

  // Poll for status updates — only hit /receipts/processing
  useEffect(() => {
    const hasInFlight = receipts.some(r => r.processing_status === 'pending' || r.processing_status === 'processing')
    if (!hasInFlight || activeTab !== 'receipts') return
    const interval = setInterval(async () => {
      try {
        const res = await authFetch(`${API}/receipts/processing`)
        const processing = await res.json()
        if (processing.length === 0) {
          // All done processing — invalidate cache and refresh current view
          clearInterval(interval)
          invalidateReceiptsCache()
          fetchReceiptsForView({ skipCache: true })
          fetchUnmatchedReceipts()
          return
        }
        // Update processing receipts in-place
        setReceipts(prev => prev.map(r => {
          const updated = processing.find(p => p.id === r.id)
          return updated || r
        }))
        // Sync selectedReceipt if open
        setSelectedReceipt(prev => {
          if (!prev) return prev
          const updated = processing.find(p => p.id === prev.id)
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
          invalidateReceiptsCache()
          if (activeTab === 'receipts') fetchReceiptsForView({ skipCache: true })
          fetchUnmatchedReceipts()
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  }, [statements, currentId, selectedAccountId, fetchTransactions, activeTab])

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
      invalidateReceiptsCache()
      if (activeTab === 'receipts') fetchReceiptsForView({ skipCache: true })
      fetchUnmatchedReceipts()
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
    const receipt = unmatchedReceipts.find(r => r.id === receiptId)
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
    setUnmatchedReceipts(prev => prev.filter(r => r.id !== receiptId))
    try {
      const res = await authFetch(`${API}/transactions/${txId}/match`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_id: receiptId }),
      })
      if (!res.ok) throw new Error()
      invalidateReceiptsCache()
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
      fetchUnmatchedReceipts()
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
      invalidateReceiptsCache()
      fetchUnmatchedReceipts()
    } catch {
      // Revert — just refetch
      invalidateReceiptsCache()
      if (currentId) fetchTransactions(currentId)
      if (activeTab === 'receipts') fetchReceiptsForView({ skipCache: true })
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
        invalidateReceiptsCache()
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
      invalidateReceiptsCache()
      if (currentId) fetchTransactions(currentId, true)
      fetchUnmatchedReceipts()
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
    try {
      await authFetch(`${API}/receipts/${receiptId}/match`, { method: 'DELETE' })
      invalidateReceiptsCache()
      if (currentId) fetchTransactions(currentId, true)
      fetchUnmatchedReceipts()
    } catch {}
  }

  const handleReceiptRematch = async (receiptId) => {
    try {
      await authFetch(`${API}/receipts/${receiptId}/rematch`, { method: 'POST' })
      // Poll to pick up the new match
      setTimeout(async () => {
        try {
          invalidateReceiptsCache()
          fetchReceiptsForView({ skipCache: true })
          fetchUnmatchedReceipts()
          setSelectedReceipt(prev => {
            if (!prev || prev.id !== receiptId) return prev
            const updated = receipts.find(r => r.id === receiptId)
            return updated || prev
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
    invalidateReceiptsCache()
    try {
      await authFetch(`${API}/receipts/${receiptId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ match_status: 'matched_sure' }),
      })
    } catch {}
  }

  // Month change handler for ReceiptsTab
  const handleMonthChange = useCallback((y, m) => {
    setPickerYear(y)
    setPickerMonth(m)
  }, [])

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
          receipts={unmatchedReceipts}
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
          viewMode={receiptViewMode}
          setViewMode={setReceiptViewMode}
          searchQuery={receiptSearchQuery}
          setSearchQuery={setReceiptSearchQuery}
          cardAccounts={cardAccounts}
          hasMore={receiptsHasMore}
          onLoadMore={handleLoadMore}
          pickerYear={pickerYear}
          pickerMonth={pickerMonth}
          onMonthChange={handleMonthChange}
          statementGroups={statementGroups}
          expandedStatements={expandedStatements}
          onExpandStatement={handleExpandStatement}
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
