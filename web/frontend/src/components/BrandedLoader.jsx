export default function BrandedLoader({ label = "Loading...", compact = false }) {
  return (
    <div className={compact ? "branded-loader branded-loader--compact" : "branded-loader"} aria-live="polite">
      <div className="branded-loader__visual">
        <img className="branded-loader__logo" src="/logo-removebg-preview.png" alt="" aria-hidden="true" />
        <span className="branded-loader__ring" />
      </div>
      <p className="branded-loader__label">{label}</p>
    </div>
  );
}
