import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearAuthToken, restoreSession } from "../api/auth.js";
import { fetchAdminSupportTickets } from "../api/admin.js";
import "../styles/admin-portal.css";

const adminLinks = [
  { to: "/admin", label: "Overview", end: true },
  { to: "/admin/doctors", label: "Doctors" },
  { to: "/admin/patients", label: "Patients" },
  { to: "/admin/consultations", label: "Consultations" },
  { to: "/admin/payments", label: "Payments" },
  { to: "/admin/doctor-earnings", label: "Doctor Earnings" },
  { to: "/admin/reports", label: "Medical Reports" },
  { to: "/admin/partners", label: "Partners" },
  { to: "/admin/ratings", label: "Ratings" },
  { to: "/admin/content", label: "Content" },
  { to: "/admin/settings", label: "Settings" },
  { to: "/admin/ticket-log", label: "Ticket Log" },
  { to: "/customer-care", label: "Customer Care" },
  { to: "/admin/errors", label: "Errors" },
  { to: "/admin/activity", label: "Activity" },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [authState, setAuthState] = useState({ status: "loading", user: null });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [ticketLogBadge, setTicketLogBadge] = useState(0);

  useEffect(() => {
    let ignore = false;
    async function checkSession() {
      try {
        const session = await restoreSession();
        if (!ignore) {
          setAuthState({
            status: session.user?.role === "admin" ? "ready" : "denied",
            user: session.user || null,
          });
        }
      } catch {
        if (!ignore) {
          setAuthState({ status: "denied", user: null });
        }
      }
    }
    checkSession();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 861px)");
    function handleScreenChange(event) {
      if (event.matches) {
        setMobileMenuOpen(false);
      }
    }
    desktopQuery.addEventListener("change", handleScreenChange);
    return () => desktopQuery.removeEventListener("change", handleScreenChange);
  }, []);

  useEffect(() => {
    if (authState.status !== "ready") return undefined;
    let ignore = false;
    async function loadTicketLogBadge() {
      try {
        const result = await fetchAdminSupportTickets("all");
        if (ignore) return;
        const unread = (result.tickets || []).reduce(
          (total, ticket) => total + Number(ticket.unread_patient_messages || 0),
          0,
        );
        setTicketLogBadge(unread);
      } catch {}
    }
    loadTicketLogBadge();
    const intervalId = window.setInterval(loadTicketLogBadge, 15000);
    window.addEventListener("synmed:admin-notifications-updated", loadTicketLogBadge);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
      window.removeEventListener("synmed:admin-notifications-updated", loadTicketLogBadge);
    };
  }, [authState.status]);

  function handleLogout() {
    clearAuthToken();
    navigate("/", { replace: true });
  }

  if (authState.status === "loading") {
    return <div className="admin-portal__loading">Checking admin session...</div>;
  }
  if (authState.status !== "ready") {
    return <Navigate to="/signin" replace />;
  }

  return (
    <div className="admin-portal">
      <aside className={mobileMenuOpen ? "admin-sidebar admin-sidebar--mobile-open" : "admin-sidebar"}>
        <NavLink className="admin-sidebar__brand" to="/admin">
          <img src="/logo-removebg-preview.png" alt="" />
          <span>
            <small>SynMed Operations</small>
            <strong>Admin</strong>
          </span>
        </NavLink>

        <nav className="admin-sidebar__nav" aria-label="Admin workspace">
          {adminLinks.map((link) => (
            <NavLink
              className={({ isActive }) =>
                isActive ? "admin-sidebar__link admin-sidebar__link--active" : "admin-sidebar__link"
              }
              end={link.end}
              key={link.to}
              to={link.to}
            >
              <span>{link.label}</span>
              {link.to === "/admin/ticket-log" && ticketLogBadge ? (
                <span className="admin-sidebar__badge">{ticketLogBadge > 99 ? "99+" : ticketLogBadge}</span>
              ) : null}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar__account">
          <span>{authState.user?.display_name || "Administrator"}</span>
          <button type="button" onClick={handleLogout}>Log out</button>
        </div>
      </aside>

      <div className="admin-portal__workspace">
        <div className="admin-mobile-nav">
          <button
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Close admin menu" : "Open admin menu"}
            className="admin-mobile-nav__menu"
            type="button"
            onClick={() => setMobileMenuOpen((current) => !current)}
          >
            <span aria-hidden="true" />
            <span aria-hidden="true" />
            <span aria-hidden="true" />
          </button>
          <div>
            <small>SynMed Operations</small>
            <strong>Admin</strong>
          </div>
        </div>
        {mobileMenuOpen ? (
          <button
            aria-label="Close admin menu"
            className="admin-sidebar-backdrop"
            type="button"
            onClick={() => setMobileMenuOpen(false)}
          />
        ) : null}
        <main className="admin-portal__main">
          <Outlet context={{ user: authState.user }} />
        </main>
      </div>
    </div>
  );
}
