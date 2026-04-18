import { useState } from 'react'
import { formatDate, formatMoney } from '../utils/formatters'
import { hasRole } from '../utils/roles'

export function TransactionRow({
  tx, companies, glCodes, expenseTypes, receipts,
  updateTransaction, handleManualMatch, handleUnmatch, handleConfirmMatch,
  showReceiptPreview, receiptPreviewTxId, receiptPreviewUrl, receiptPreviewLoading,
  setReceiptPreviewTxId, linkingTxId, setLinkingTxId, userRole,
}) {
  const canEdit = hasRole(userRole, 'delegate')
  const [linkSearch, setLinkSearch] = useState('')

  const companyName = tx.company_id ? (companies.find(c => c.id === tx.company_id)?.name || '—') : '—'
  const glDisplay = tx.gl_code_id ? (() => { const g = glCodes.find(g => g.id === tx.gl_code_id); return g ? `${g.code} — ${g.name}` : '—' })() : '—'
  const expenseTypeName = tx.expense_type_id ? (expenseTypes.find(e => e.id === tx.expense_type_id)?.name || '—') : '—'

  return (
    <tr className={tx.amount_cad < 0 ? 'credit-row' : ''} data-tx-id={tx.id}>
      <td className="date-cell">{formatDate(tx.transaction_date)}</td>
      <td className="merchant-cell">
        <div className="merchant-text">{tx.merchant || ''}</div>
      </td>
      <td className="location-cell">
        {canEdit ? (
          <>
            <input
              type="text"
              value={tx.city || ''}
              onChange={e => updateTransaction(tx.id, 'city', e.target.value)}
              className="cell-input"
              placeholder="City"
              style={{ marginBottom: 2 }}
            />
            <input
              type="text"
              value={tx.country || ''}
              onChange={e => updateTransaction(tx.id, 'country', e.target.value)}
              className="cell-input cell-input-secondary"
              placeholder="Country"
            />
          </>
        ) : (
          <span className="cell-text">{[tx.city, tx.country].filter(Boolean).join(', ') || '—'}</span>
        )}
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
        {canEdit ? (
          <input
            type="number"
            step="0.01"
            value={tx.tax_amount != null ? tx.tax_amount : ''}
            onChange={e => {
              const val = e.target.value
              updateTransaction(tx.id, 'tax_amount', val === '' ? null : parseFloat(val))
            }}
            className="cell-input cell-input-num"
            placeholder="—"
          />
        ) : (
          <span className="cell-text">{tx.tax_amount != null ? formatMoney(tx.tax_amount) : '—'}</span>
        )}
      </td>
      <td>
        {canEdit ? (
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
        ) : (
          <span className="cell-text">{companyName}</span>
        )}
      </td>
      <td>
        {canEdit ? (
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
        ) : (
          <span className="cell-text">{glDisplay}</span>
        )}
      </td>
      <td>
        {canEdit ? (
          <select
            value={tx.expense_type_id || ''}
            onChange={e => updateTransaction(tx.id, 'expense_type_id', e.target.value, true)}
            className="cell-select"
          >
            <option value="">—</option>
            {expenseTypes.map(et => (
              <option key={et.id} value={et.id}>{et.name}</option>
            ))}
          </select>
        ) : (
          <span className="cell-text">{expenseTypeName}</span>
        )}
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
            {canEdit && tx.match_status === 'matched_unsure' && (
              <button
                className="receipt-confirm-btn"
                onClick={() => handleConfirmMatch(tx.matched_receipt_id)}
                title="Confirm match"
              >&#x2713;</button>
            )}
            {canEdit && (
              <button
                className="receipt-unmatch-btn"
                onClick={() => handleUnmatch(tx.id)}
                title="Remove match"
              >&times;</button>
            )}
            {receiptPreviewTxId === tx.id && (
              <div className="receipt-popup" onClick={e => e.stopPropagation()}>
                <div className="receipt-popup-header">
                  <span className="receipt-popup-title">{tx.receipt_merchant || tx.receipt_file_name}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button
                      type="button"
                      className="btn"
                      style={{ padding: '4px 8px', fontSize: 12 }}
                      onClick={() => {
                        if (!receiptPreviewUrl) return
                        window.open(receiptPreviewUrl, '_blank', 'noopener,noreferrer')
                      }}
                      disabled={!receiptPreviewUrl}
                      title="Open full-size receipt in new tab"
                    >
                      Expand
                    </button>
                    <button type="button" className="modal-close" onClick={() => setReceiptPreviewTxId(null)}>&times;</button>
                  </div>
                </div>
                {receiptPreviewLoading ? (
                  <div className="shimmer-block" style={{ width: '100%', height: 200, borderRadius: 8 }} />
                ) : tx.receipt_file_type?.includes('html') ? (
                  <div style={{ padding: 16, fontSize: 13, color: '#6b7280', textAlign: 'center' }}>
                    Email receipt — open in Receipts tab to view
                  </div>
                ) : receiptPreviewUrl ? (
                  tx.receipt_file_type?.includes('pdf') ? (
                    <iframe src={receiptPreviewUrl} className="receipt-popup-img" title="receipt" style={{ width: '100%', height: 300, border: 'none' }} />
                  ) : (
                    <img src={receiptPreviewUrl} alt="receipt" className="receipt-popup-img" />
                  )
                ) : (
                  <div className="receipt-preview-placeholder" style={{ padding: 20 }}>No preview</div>
                )}
              </div>
            )}
          </div>
        ) : canEdit ? (
          <div className="receipt-link-wrapper">
            <button
              className="receipt-link-btn"
              onClick={e => { e.stopPropagation(); setLinkingTxId(linkingTxId === tx.id ? null : tx.id) }}
            >
              Link
            </button>
            {linkingTxId === tx.id && (
              <div className="receipt-link-dropdown" onClick={e => e.stopPropagation()}>
                <input
                  className="receipt-link-search"
                  type="text"
                  placeholder="Search vendor..."
                  value={linkSearch}
                  onChange={e => setLinkSearch(e.target.value)}
                  autoFocus
                />
                {(() => {
                  const unmatched = receipts.filter(r => !r.match_status || r.match_status === 'unmatched')
                  const q = linkSearch.toLowerCase()
                  const filtered = q ? unmatched.filter(r =>
                    (r.merchant_name || r.file_name || '').toLowerCase().includes(q)
                  ) : unmatched
                  if (unmatched.length === 0) return <div className="receipt-link-empty">No unmatched receipts</div>
                  if (filtered.length === 0) return <div className="receipt-link-empty">No matches for "{linkSearch}"</div>
                  return filtered.map(r => (
                    <button
                      key={r.id}
                      className="receipt-link-option"
                      onClick={() => handleManualMatch(tx.id, r.id)}
                    >
                      <span className="receipt-link-name">{r.merchant_name || r.file_name || 'Untitled'}</span>
                      <span className="receipt-link-amount">{r.total_amount != null ? formatMoney(r.total_amount) : ''}</span>
                    </button>
                  ))
                })()}
              </div>
            )}
          </div>
        ) : (
          <span className="cell-text">—</span>
        )}
      </td>
    </tr>
  )
}
