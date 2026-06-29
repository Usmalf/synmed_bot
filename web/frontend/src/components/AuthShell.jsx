export default function AuthShell({
  eyebrow,
  title,
  body,
  asideTitle,
  asideBody,
  asidePoints = [],
  children,
}) {
  return (
    <section className="auth-shell">
      <div className="auth-shell__intro">
        {eyebrow ? <span className="workspace-pill">{eyebrow}</span> : null}
        <h1>{title}</h1>
        {body ? <p>{body}</p> : null}
      </div>

      <aside className="auth-shell__aside">
        <div className="auth-shell__aside-card">
          <span className="landing-kicker">What Happens Here</span>
          <h2>{asideTitle}</h2>
          <p>{asideBody}</p>
        </div>

        {asidePoints.length ? (
          <div className="auth-shell__points">
            {asidePoints.map((point) => (
              <article key={point.title} className="auth-shell__point">
                <h3>{point.title}</h3>
                <p>{point.body}</p>
              </article>
            ))}
          </div>
        ) : null}
      </aside>

      <div className="auth-shell__panel">{children}</div>
    </section>
  );
}
