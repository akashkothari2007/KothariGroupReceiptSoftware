export function ShimmerCards({ count = 6 }) {
  return (
    <div className="receipts-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="receipt-card receipt-card-shimmer">
          <div className="shimmer-block shimmer-icon" />
          <div className="shimmer-block shimmer-line" />
          <div className="shimmer-block shimmer-line-short" />
          <div className="shimmer-block shimmer-line-short" />
        </div>
      ))}
    </div>
  )
}
