export default function SiteShell({ header, children }) {
  return (
    <div className="site-shell">
      <header className="site-shell__header">{header}</header>
      <main className="site-shell__main">{children}</main>
    </div>
  );
}
