import { ProcessingDot } from './ProcessingDot'
import { formatDate, formatMoney, formatUploadDate, receiptMatchLabel, fileTypeIcon } from '../utils/formatters'

export function ReceiptCard({ receipt, receiptMenuOpen, setReceiptMenuOpen, onSelect, onDelete, onRetry, onConfirmMatch }) {
  return (
    <div
      className="receipt-card"
      onClick={() => onSelect(receipt)}
    >
      <div className="receipt-card-top">
        <div className="receipt-card-top-left">
          <div className={`receipt-type-icon ${fileTypeIcon(receipt.file_type).toLowerCase()}`}>
            {fileTypeIcon(receipt.file_type)}
          </div>
          <ProcessingDot status={receipt.processing_status} />
        </div>
        <div
          className="receipt-menu-trigger"
          onClick={e => {
            e.stopPropagation()
            setReceiptMenuOpen(receiptMenuOpen === receipt.id ? null : receipt.id)
          }}
        >
          &#x22EF;
        </div>
        {receiptMenuOpen === receipt.id && (
          <div className="receipt-menu" onClick={e => e.stopPropagation()}>
            {(receipt.processing_status === 'failed' || receipt.processing_status === 'completed') && (
              <button
                className="receipt-menu-item"
                onClick={() => onRetry(receipt.id)}
              >
                Retry
              </button>
            )}
            <button
              className="receipt-menu-item receipt-menu-delete"
              onClick={() => onDelete(receipt.id)}
            >
              Delete
            </button>
          </div>
        )}
      </div>

      <div className="receipt-card-body">
        <div className="receipt-card-name" title={receipt.file_name}>
          {receipt.file_name || 'Untitled'}
        </div>
        <div className="receipt-card-detail">
          <span className="receipt-card-label">Merchant</span>
          <span>{receipt.merchant_name || '—'}</span>
        </div>
        <div className="receipt-card-detail">
          <span className="receipt-card-label">Date</span>
          <span>{receipt.receipt_date ? formatDate(receipt.receipt_date) : '—'}</span>
        </div>
        <div className="receipt-card-detail">
          <span className="receipt-card-label">Amount</span>
          <span>{receipt.total_amount != null ? formatMoney(receipt.total_amount) : '—'}</span>
        </div>
      </div>

      <div className="receipt-card-footer">
        <span className={`receipt-badge ${receipt.match_status || 'unmatched'}`}>
          {receiptMatchLabel(receipt.match_status)}
        </span>
        {receipt.match_status === 'matched_unsure' && (
          <button
            className="receipt-confirm-btn-card"
            onClick={e => { e.stopPropagation(); onConfirmMatch(receipt.id) }}
            title="Confirm match"
          >
            Confirm
          </button>
        )}
        <span className="receipt-card-date">
          {receipt.created_at ? formatUploadDate(receipt.created_at) : ''}
        </span>
      </div>
    </div>
  )
}
