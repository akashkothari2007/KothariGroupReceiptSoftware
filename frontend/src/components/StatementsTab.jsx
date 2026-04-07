import { useRef } from 'react'
import { ShimmerRows } from './ShimmerRows'
import { TransactionRow } from './TransactionRow'
import { formatMoney, formatUploadDate } from '../utils/formatters'

export function StatementsTab({
  statements, currentIndex, currentStatement,
  setCurrentId, uploading, setUploading, deleteConfirm, setDeleteConfirm,
  transactions, loadingTx, glCodes, companies, receipts,
  fetchStatements, fetchTransactions, currentId,
  updateTransaction, handleManualMatch, handleUnmatch, handleConfirmMatch,
  showReceiptPreview, receiptPreviewTxId, receiptPreviewUrl, receiptPreviewLoading,
  setReceiptPreviewTxId, linkingTxId, setLinkingTxId,
  handleUpload, handleDelete, fileRef,
}) {
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
                  <TransactionRow
                    key={tx.id}
                    tx={tx}
                    companies={companies}
                    glCodes={glCodes}
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

      {!currentStatement && (
        <div className="empty">Upload an Amex CSV to get started.</div>
      )}
    </>
  )
}
