export default function HeroCard({ eyebrow, title, body, actions }) {
  return (
    <section className="hero-card">
      <p className="hero-card__eyebrow">{eyebrow}</p>
      <h1 className="hero-card__title">{title}</h1>
      <p className="hero-card__body">{body}</p>
      <div className="hero-card__actions">{actions}</div>
    </section>
  );
}
