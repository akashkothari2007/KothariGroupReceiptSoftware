import { useMemo } from 'react'
import { ShimmerCards } from './ShimmerCards'
import { ReceiptCard } from './ReceiptCard'

function statusBucket(match_status) {
  if (match_status === 'matched_sure') return 'matched'
  if (match_status === 'matched_unsure') return 'unsure'
  return 'unmatched'
}

export function ReceiptsTab({
  receipts, loadingReceipts, uploadingReceipt, receiptFilter, setReceiptFilter,
  receiptMenuOpen, setReceiptMenuOpen,
  handleReceiptUpload, handleReceiptDelete, handleReceiptRetry, handleConfirmMatch,
  setSelectedReceipt, receiptFileRef,
}) {
  const toggle = (key) => setReceiptFilter(prev => ({ ...prev, [key]: !prev[key] }))

  const filtered = useMemo(() => {
    const list = receipts.filter(r => receiptFilter[statusBucket(r.match_status)])
    list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    return list
  }, [receipts, receiptFilter])

  return (
    <div className="receipts-tab">
      <div className="receipts-toolbar">
        <input
          ref={receiptFileRef}
          type="file"
          accept="image/jpeg,image/png,application/pdf,image/heic,image/heif" multiple
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
          {!loadingReceipts && `${filtered.length} of ${receipts.length} receipt${receipts.length !== 1 ? 's' : ''}`}
        </span>
        <div className="receipt-filter-toggles">
          <button className={`filter-chip${receiptFilter.unmatched ? ' active' : ''}`} onClick={() => toggle('unmatched')}>Unmatched</button>
          <button className={`filter-chip${receiptFilter.unsure ? ' active' : ''}`} onClick={() => toggle('unsure')}>Unsure</button>
          <button className={`filter-chip${receiptFilter.matched ? ' active' : ''}`} onClick={() => toggle('matched')}>Matched</button>
        </div>
      </div>

      {loadingReceipts ? (
        <ShimmerCards />
      ) : filtered.length === 0 ? (
        <div className="empty">{receipts.length === 0 ? 'No receipts yet. Upload one to get started.' : 'No receipts match the current filter.'}</div>
      ) : (
        <div className="receipts-grid">
          {filtered.map(r => (
            <ReceiptCard
              key={r.id}
              receipt={r}
              receiptMenuOpen={receiptMenuOpen}
              setReceiptMenuOpen={setReceiptMenuOpen}
              onSelect={setSelectedReceipt}
              onDelete={handleReceiptDelete}
              onRetry={handleReceiptRetry}
              onConfirmMatch={handleConfirmMatch}
            />
          ))}
        </div>
      )}
    </div>
  )
}
