export default function StatusPill({ label, tone = "neutral" }) {
  return <span className={`status-pill status-pill--${tone}`}>{label}</span>;
}
