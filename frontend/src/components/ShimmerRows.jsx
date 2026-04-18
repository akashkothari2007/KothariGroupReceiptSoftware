export function ShimmerRows({ count = 8 }) {
  return Array.from({ length: count }).map((_, i) => (
    <tr key={i} className="shimmer-row">
      {Array.from({ length: 9 }).map((_, j) => (
        <td key={j}><div className="shimmer-block" /></td>
      ))}
    </tr>
  ))
}
