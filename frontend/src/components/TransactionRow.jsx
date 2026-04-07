import { formatDate, formatMoney } from '../utils/formatters'

export function TransactionRow({
  tx, companies, glCodes, receipts,
  updateTransaction, handleManualMatch, handleUnmatch, handleConfirmMatch,
  showReceiptPreview, receiptPreviewTxId, receiptPreviewUrl, receiptPreviewLoading,
  setReceiptPreviewTxId, linkingTxId, setLinkingTxId,
}) {
  return (
    <tr className={tx.amount_cad < 0 ? 'credit-row' : ''}>
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
            {tx.match_status === 'matched_unsure' && (
              <button
                className="receipt-confirm-btn"
                onClick={() => handleConfirmMatch(tx.matched_receipt_id)}
                title="Confirm match"
              >&#x2713;</button>
            )}
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
  )
}
