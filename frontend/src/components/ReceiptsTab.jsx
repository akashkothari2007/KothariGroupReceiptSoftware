import { useRef } from 'react'
import { ShimmerCards } from './ShimmerCards'
import { ReceiptCard } from './ReceiptCard'

export function ReceiptsTab({
  receipts, loadingReceipts, uploadingReceipt, receiptSort, setReceiptSort,
  receiptMenuOpen, setReceiptMenuOpen,
  handleReceiptUpload, handleReceiptDelete, handleReceiptRetry, handleConfirmMatch,
  setSelectedReceipt, receiptFileRef,
}) {
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
