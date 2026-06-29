export default function SectionCard({ id, title, subtitle, children }) {
  return (
    <section className="section-card" id={id}>
      {title || subtitle ? (
        <div className="section-card__header">
          {title ? <h2 className="section-card__title">{title}</h2> : null}
          {subtitle ? <p className="section-card__subtitle">{subtitle}</p> : null}
        </div>
      ) : null}
      <div className="section-card__body">{children}</div>
    </section>
  );
}
