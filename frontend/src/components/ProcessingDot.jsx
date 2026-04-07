export function ProcessingDot({ status }) {
  const config = {
    pending: { color: '#9ca3af', label: 'Pending' },
    processing: { color: '#eab308', label: 'Processing' },
    completed: { color: '#22c55e', label: 'Completed' },
    failed: { color: '#ef4444', label: 'Failed' },
  }
  const c = config[status] || config.pending
  return (
    <span className="processing-dot-wrapper" title={c.label}>
      <span className="processing-dot" style={{ background: c.color }} />
      <span className="processing-dot-label" style={{ color: c.color }}>{c.label}</span>
    </span>
  )
}
