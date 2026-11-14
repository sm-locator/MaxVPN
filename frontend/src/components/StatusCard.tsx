type StatusCardProps = {
  label: string
  value: string
  tone?: 'green' | 'gray' | 'red'
}

export function StatusCard({
  label,
  value,
  tone = 'gray',
}: StatusCardProps) {
  return (
    <div className="status-card">
      <span className={`status-dot status-${tone}`} />
      <div>
        <div className="status-label">{label}</div>
        <div className="status-value">{value}</div>
      </div>
    </div>
  )
}
