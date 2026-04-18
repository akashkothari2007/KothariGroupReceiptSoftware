import { useState } from 'react'
import { ShimmerCards } from './ShimmerCards'
import { ReceiptCard } from './ReceiptCard'
import { hasRole } from '../utils/roles'

function formatMonth(year, month) {
  // month is 1-12 from API convention
  const d = new Date(year, month - 1)
  return d.toLocaleString('default', { month: 'long', year: 'numeric' })
}

function MonthPicker({ year, month, onChange }) {
  const prev = () => {
    if (month === 1) onChange(year - 1, 12)
    else onChange(year, month - 1)
  }
  const next = () => {
    if (month === 12) onChange(year + 1, 1)
    else onChange(year, month + 1)
  }
  return (
    <div className="month-picker">
      <button className="btn month-picker-arrow" onClick={prev}>&larr;</button>
      <span className="month-picker-label">{formatMonth(year, month)}</span>
      <button className="btn month-picker-arrow" onClick={next}>&rarr;</button>
    </div>
  )
}

function StatementGroup({ label, count, receipts, defaultOpen, onExpand, statementId, receiptMenuOpen, setReceiptMenuOpen, onSelect, onDelete, onRetry, onConfirmMatch }) {
  const [open, setOpen] = useState(defaultOpen)
  const handleToggle = () => {
    const willOpen = !open
    setOpen(willOpen)
    if (willOpen && onExpand) onExpand(statementId)
  }
  return (
    <div className="statement-group">
      <button className="statement-group-header" onClick={handleToggle}>
        <span className="statement-group-arrow">{open ? '▾' : '▸'}</span>
        <span className="statement-group-label">{label}</span>
        <span className="statement-group-count">{count} receipt{count !== 1 ? 's' : ''}</span>
      </button>
      {open && receipts && (
        <div className="receipts-grid">
          {receipts.map(r => (
            <ReceiptCard
              key={r.id}
              receipt={r}
              receiptMenuOpen={receiptMenuOpen}
              setReceiptMenuOpen={setReceiptMenuOpen}
              onSelect={onSelect}
              onDelete={onDelete}
              onRetry={onRetry}
              onConfirmMatch={onConfirmMatch}
            />
          ))}
        </div>
      )}
      {open && !receipts && (
        <ShimmerCards />
      )}
    </div>
  )
}

export function ReceiptsTab({
  receipts, loadingReceipts, uploadingReceipt, receiptFilter, setReceiptFilter,
  receiptMenuOpen, setReceiptMenuOpen,
  handleReceiptUpload, handleReceiptDelete, handleReceiptRetry, handleConfirmMatch,
  setSelectedReceipt, receiptFileRef,
  viewMode, setViewMode, searchQuery, setSearchQuery, cardAccounts,
  hasMore, onLoadMore,
  pickerYear, pickerMonth, onMonthChange,
  statementGroups, expandedStatements, onExpandStatement,
  userRole,
}) {
  const canEdit = hasRole(userRole, 'delegate')
  const toggle = (key) => setReceiptFilter(prev => ({ ...prev, [key]: !prev[key] }))

  const filtersDisabled = viewMode === 'byStatement' && !searchQuery

  const isSearching = searchQuery.trim().length > 0

  // Split receipts into dated and no-date for byMonth view
  const dated = viewMode === 'byMonth' && !isSearching ? receipts.filter(r => r.receipt_date) : []
  const noDate = viewMode === 'byMonth' && !isSearching ? receipts.filter(r => !r.receipt_date) : []

  const displayCount = viewMode === 'byStatement' && !isSearching
    ? statementGroups.reduce((sum, g) => sum + g.receipt_count, 0)
    : receipts.length

  const cardProps = { receiptMenuOpen, setReceiptMenuOpen, onSelect: setSelectedReceipt, onDelete: canEdit ? handleReceiptDelete : null, onRetry: canEdit ? handleReceiptRetry : null, onConfirmMatch: canEdit ? handleConfirmMatch : null }

  return (
    <div className="receipts-tab">
      <div className="receipts-toolbar">
        {canEdit && (
          <>
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
          </>
        )}
        <span className="receipts-count">
          {!loadingReceipts && `${displayCount} receipt${displayCount !== 1 ? 's' : ''}`}
        </span>
      </div>

      <div className="receipts-controls">
        <div className={`view-mode-toggle${isSearching ? ' dimmed' : ''}`}>
          <button className={`view-mode-btn${viewMode === 'byMonth' ? ' active' : ''}`} onClick={() => { setSearchQuery(''); setViewMode('byMonth') }}>By Month</button>
          <button className={`view-mode-btn${viewMode === 'recent' ? ' active' : ''}`} onClick={() => { setSearchQuery(''); setViewMode('recent') }}>Recent</button>
          <button className={`view-mode-btn${viewMode === 'byStatement' ? ' active' : ''}`} onClick={() => { setSearchQuery(''); setViewMode('byStatement') }}>By Statement</button>
        </div>
        <input
          className="receipt-search"
          type="text"
          placeholder="Search by merchant..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
        />
        <div className={`receipt-filter-toggles${filtersDisabled ? ' disabled' : ''}`}>
          <button className={`filter-chip${receiptFilter.unmatched ? ' active' : ''}`} onClick={() => !filtersDisabled && toggle('unmatched')} disabled={filtersDisabled}>Unmatched</button>
          <button className={`filter-chip${receiptFilter.unsure ? ' active' : ''}`} onClick={() => !filtersDisabled && toggle('unsure')} disabled={filtersDisabled}>Unsure</button>
          <button className={`filter-chip${receiptFilter.matched ? ' active' : ''}`} onClick={() => !filtersDisabled && toggle('matched')} disabled={filtersDisabled}>Matched</button>
        </div>
      </div>

      {loadingReceipts ? (
        <ShimmerCards />
      ) : isSearching ? (
        // Search results — flat grid
        receipts.length === 0 ? (
          <div className="empty">No receipts match "{searchQuery}"</div>
        ) : (
          <>
            <div className="receipts-grid">
              {receipts.map(r => (
                <ReceiptCard key={r.id} receipt={r} {...cardProps} />
              ))}
            </div>
            {hasMore && (
              <div className="load-more-wrapper">
                <button className="btn load-more-btn" onClick={onLoadMore}>Load more</button>
              </div>
            )}
          </>
        )
      ) : viewMode === 'byMonth' ? (
        // By Month view
        <>
          <MonthPicker year={pickerYear} month={pickerMonth} onChange={onMonthChange} />
          {dated.length === 0 && noDate.length === 0 ? (
            <div className="empty">No receipts for {formatMonth(pickerYear, pickerMonth)}</div>
          ) : (
            <>
              <div className="receipts-grid">
                {dated.map(r => (
                  <ReceiptCard key={r.id} receipt={r} {...cardProps} />
                ))}
              </div>
              {noDate.length > 0 && (
                <div className="no-date-section">
                  <div className="no-date-label">No Date ({noDate.length})</div>
                  <div className="receipts-grid">
                    {noDate.map(r => (
                      <ReceiptCard key={r.id} receipt={r} {...cardProps} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </>
      ) : viewMode === 'recent' ? (
        // Recently Uploaded view
        receipts.length === 0 ? (
          <div className="empty">No receipts match the current filter.</div>
        ) : (
          <>
            <div className="receipts-grid">
              {receipts.map(r => (
                <ReceiptCard key={r.id} receipt={r} {...cardProps} />
              ))}
            </div>
            {hasMore && (
              <div className="load-more-wrapper">
                <button className="btn load-more-btn" onClick={onLoadMore}>Load more</button>
              </div>
            )}
          </>
        )
      ) : (
        // By Statement view
        statementGroups.length === 0 ? (
          <div className="empty">No matched receipts with statement info.</div>
        ) : (
          statementGroups.map(g => (
            <StatementGroup
              key={g.statement_id}
              statementId={g.statement_id}
              label={`${g.card_account_name} — ${g.cycle_start || '?'} to ${g.cycle_end || '?'}`}
              count={g.receipt_count}
              receipts={expandedStatements[g.statement_id] || null}
              defaultOpen={false}
              onExpand={onExpandStatement}
              {...cardProps}
            />
          ))
        )
      )}
    </div>
  )
}
