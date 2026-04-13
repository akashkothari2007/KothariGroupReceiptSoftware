import { useState, useEffect } from 'react'
import { useDebounce } from '../hooks/useDebounce'
import { API, authFetch, getReceiptUrl } from '../utils/api'
import { ProcessingDot } from './ProcessingDot'

export function ReceiptDetailModal({ receipt, onClose, onUpdate, onRetry, onUnmatch, onRematch, onConfirmMatch, onGoToTransaction }) {
  const [fileUrl, setFileUrl] = useState(null)
  const [htmlContent, setHtmlContent] = useState(null)
  const [loadingUrl, setLoadingUrl] = useState(false)
  const [fields, setFields] = useState({})
  const debounce = useDebounce()

  const isHtml = receipt?.file_type?.includes('html')

  useEffect(() => {
    if (!receipt) return
    setFields({
      merchant_name: receipt.merchant_name || '',
      receipt_date: receipt.receipt_date || '',
      subtotal: receipt.subtotal != null ? String(receipt.subtotal) : '',
      tax_amount: receipt.tax_amount != null ? String(receipt.tax_amount) : '',
      tax_type: receipt.tax_type || '',
      total_amount: receipt.total_amount != null ? String(receipt.total_amount) : '',
      city: receipt.city || '',
      province: receipt.province || '',
      country: receipt.country || '',
    })
    setLoadingUrl(true)
    setFileUrl(null)
    setHtmlContent(null)
    getReceiptUrl(receipt.id)
      .then(async (url) => {
        setFileUrl(url)
        if (receipt.file_type?.includes('html')) {
          const resp = await fetch(url)
          const text = await resp.text()
          setHtmlContent(text)
        }
      })
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
        await authFetch(`${API}/receipts/${receipt.id}`, {
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
            {receipt.processing_status === 'failed' && onRetry && (
              <button
                style={{ marginLeft: 8, padding: '4px 12px', fontSize: 12, background: '#f0a500', color: '#000', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                onClick={() => onRetry(receipt.id)}
              >
                Retry
              </button>
            )}
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
              ) : isHtml && htmlContent ? (
                <iframe srcDoc={htmlContent} className="receipt-pdf-embed" title={receipt.file_name} sandbox="allow-same-origin" />
              ) : !isHtml ? (
                <img src={fileUrl} alt={receipt.file_name} className="receipt-image" />
              ) : null
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
                <option value="none">None</option>
              </select>
            </div>
            <div className="meta-row">
              <span className="meta-label">Total amount</span>
              <input className="meta-input meta-input-num" value={fields.total_amount} onChange={e => handleChange('total_amount', e.target.value)} placeholder="—" />
            </div>
            <div className="meta-row">
              <span className="meta-label">City</span>
              <input className="meta-input" value={fields.city} onChange={e => handleChange('city', e.target.value)} placeholder="—" style={{ maxWidth: 140 }} />
            </div>
            <div className="meta-row">
              <span className="meta-label">Province</span>
              <input className="meta-input" value={fields.province} onChange={e => handleChange('province', e.target.value)} placeholder="—" style={{ maxWidth: 80 }} />
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
                <span
                  className="meta-value meta-value-linked"
                  style={onGoToTransaction ? { cursor: 'pointer', textDecoration: 'underline' } : {}}
                  onClick={() => onGoToTransaction && onGoToTransaction(receipt.transaction_id)}
                  title={onGoToTransaction ? 'Go to transaction' : ''}
                >
                  {receipt.tx_merchant || 'Transaction'} — {receipt.tx_amount != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(receipt.tx_amount) : ''}
                  {receipt.tx_date ? ` (${receipt.tx_date})` : ''}
                </span>
              </div>
            )}
            {receipt.processing_status === 'completed' && (
              <div className="meta-row" style={{ gap: 8, justifyContent: 'flex-end', borderTop: '1px solid #333', paddingTop: 10, marginTop: 4 }}>
                {receipt.transaction_id && onUnmatch && (
                  <button
                    style={{ padding: '5px 14px', fontSize: 12, background: '#dc3545', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                    onClick={() => onUnmatch(receipt.id)}
                  >
                    Unmatch
                  </button>
                )}
                {receipt.match_status === 'matched_unsure' && receipt.transaction_id && onConfirmMatch && (
                  <button
                    style={{ padding: '5px 14px', fontSize: 12, background: '#16a34a', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                    onClick={() => onConfirmMatch(receipt.id)}
                  >
                    Confirm Match
                  </button>
                )}
                {onRematch && (
                  <button
                    style={{ padding: '5px 14px', fontSize: 12, background: '#2563eb', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer' }}
                    onClick={() => onRematch(receipt.id)}
                  >
                    {receipt.transaction_id ? 'Re-match' : 'Find Match'}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
