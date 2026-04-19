export default function SectionCard({ title, subtitle, children }) {
  return (
    <section className="section-card">
      <div className="section-card__header">
        <h2 className="section-card__title">{title}</h2>
        {subtitle ? <p className="section-card__subtitle">{subtitle}</p> : null}
      </div>
      <div className="section-card__body">{children}</div>
    </section>
  );
}
