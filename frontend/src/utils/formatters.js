export const formatDate = (d) => {
  if (!d) return ''
  const date = new Date(d + 'T00:00:00')
  return date.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

export const formatMoney = (amt) => {
  if (amt == null) return ''
  return new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD' }).format(amt)
}

export const formatUploadDate = (d) => {
  if (!d) return ''
  return new Date(d).toLocaleDateString('en-CA', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

export const statusLabel = (s) => {
  const map = { unmatched: 'No receipt', matched_sure: 'Matched', matched_unsure: 'Unsure', ignored: 'Ignored' }
  return map[s] || 'No receipt'
}

export const receiptMatchLabel = (s) => {
  const map = { unmatched: 'No match', matched_sure: 'Matched', matched_unsure: 'Unsure', ignored: 'Ignored' }
  return map[s] || 'No match'
}

export const fileTypeIcon = (type) => {
  if (!type) return 'FILE'
  if (type.includes('pdf')) return 'PDF'
  return 'IMG'
}
