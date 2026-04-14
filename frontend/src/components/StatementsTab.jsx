import { useState } from 'react'
import { ShimmerRows } from './ShimmerRows'
import { TransactionRow } from './TransactionRow'
import { ExpenseReportSection } from './ExpenseReportSection'
import { formatMoney, formatUploadDate } from '../utils/formatters'
import { API, authFetch } from '../utils/api'

export function StatementsTab({
  statements, currentIndex, currentStatement,
  setCurrentId, uploading, setUploading, deleteConfirm, setDeleteConfirm,
  transactions, loadingTx, glCodes, companies, expenseTypes, receipts,
  fetchStatements, fetchTransactions, currentId,
  updateTransaction, handleManualMatch, handleUnmatch, handleConfirmMatch,
  showReceiptPreview, receiptPreviewTxId, receiptPreviewUrl, receiptPreviewLoading,
  setReceiptPreviewTxId, linkingTxId, setLinkingTxId,
  handleUpload, handleDelete, fileRef,
  cardAccounts, selectedAccountId, setSelectedAccountId, fetchCardAccounts,
}) {
  const [showNewAccount, setShowNewAccount] = useState(false)
  const [newAccountName, setNewAccountName] = useState('')
  const [newAccountType, setNewAccountType] = useState('amex')
  const [newAccountHolder, setNewAccountHolder] = useState('')
  const [creatingAccount, setCreatingAccount] = useState(false)
  const handleCreateAccount = async () => {
    if (!newAccountName.trim()) return
    setCreatingAccount(true)
    try {
      const res = await authFetch(`${API}/lookups/card-accounts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newAccountName.trim(),
          card_type: newAccountType,
          card_holder: newAccountHolder.trim() || null,
        }),
      })
      const created = await res.json()
      await fetchCardAccounts()
      setSelectedAccountId(created.id)
      setShowNewAccount(false)
      setNewAccountName('')
      setNewAccountType('amex')
      setNewAccountHolder('')
    } catch (err) {
      alert('Failed to create account: ' + err.message)
    }
    setCreatingAccount(false)
  }

  const selectedAccount = cardAccounts.find(a => a.id === selectedAccountId)

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

  return (
    <>
      <div className="card-account-bar">
        <div className="card-account-selector">
          <label>Card Account</label>
          <select
            value={selectedAccountId || ''}
            onChange={(e) => setSelectedAccountId(e.target.value)}
          >
            {cardAccounts.map(a => (
              <option key={a.id} value={a.id}>
                {a.name} {a.card_holder ? `(${a.card_holder})` : ''}
              </option>
            ))}
          </select>
          <button className="btn btn-sm" onClick={() => setShowNewAccount(!showNewAccount)}>
            + New Account
          </button>
        </div>
        {showNewAccount && (
          <div className="new-account-form">
            <input
              type="text"
              placeholder="Account name (e.g. Anupam Amex)"
              value={newAccountName}
              onChange={(e) => setNewAccountName(e.target.value)}
            />
            <select value={newAccountType} onChange={(e) => setNewAccountType(e.target.value)}>
              <option value="amex">Amex</option>
              <option value="mastercard">Mastercard</option>
              <option value="visa">Visa</option>
            </select>
            <input
              type="text"
              placeholder="Card holder name"
              value={newAccountHolder}
              onChange={(e) => setNewAccountHolder(e.target.value)}
            />
            <button className="btn btn-primary btn-sm" onClick={handleCreateAccount} disabled={creatingAccount}>
              {creatingAccount ? 'Creating...' : 'Create'}
            </button>
            <button className="btn btn-sm" onClick={() => setShowNewAccount(false)}>Cancel</button>
          </div>
        )}
      </div>

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
                  {currentStatement.matching_status === 'matching' && <span style={{color: '#f0a500', marginLeft: 8}}>Matching...</span>}
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
                <th>Location</th>
                <th className="amount-col">Amount</th>
                <th className="amount-col">Tax (HST/GST)</th>
                <th>Company</th>
                <th>GL Code</th>
                <th>Type of Expense</th>
                <th>Receipt</th>
              </tr>
            </thead>
            <tbody>
              {loadingTx ? (
                <ShimmerRows />
              ) : transactions.length === 0 ? (
                <tr><td colSpan={9} className="empty-cell">No transactions in this statement.</td></tr>
              ) : (
                transactions.map(tx => (
                  <TransactionRow
                    key={tx.id}
                    tx={tx}
                    companies={companies}
                    glCodes={glCodes}
                    expenseTypes={expenseTypes}
                    receipts={receipts}
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
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {currentStatement && !loadingTx && transactions.length > 0 && (
        <ExpenseReportSection
          transactions={transactions}
          companies={companies}
          glCodes={glCodes}
          statementId={currentId}
        />
      )}

      {!currentStatement && selectedAccountId && (
        <div className="empty">No statements for this account yet. Upload a CSV to get started.</div>
      )}
      {!selectedAccountId && (
        <div className="empty">Create a card account to get started.</div>
      )}
    </>
  )
}
