import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearAuthToken, restoreSession } from "../api/auth.js";
import { fetchCustomerCareDesk, fetchCustomerCareMail } from "../api/customerCare.js";
import "../styles/admin-portal.css";
import "../styles/customer-care.css";

const CUSTOMER_CARE_NAV = [
  { panel: "overview", label: "Overview" },
  { panel: "tickets", label: "Support tickets" },
  { panel: "messages", label: "Messages" },
  { panel: "payments", label: "Payment access" },
  { panel: "consultations", label: "Consultations" },
  { panel: "accounts", label: "Accounts", adminOnly: true },
];

export default function CustomerCareLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [authState, setAuthState] = useState({ status: "loading", user: null });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [badgeCounts, setBadgeCounts] = useState({ tickets: 0, messages: 0 });

  useEffect(() => {
    let ignore = false;
    async function checkSession() {
      try {
        const session = await restoreSession();
        if (!ignore) {
          setAuthState({
            status: ["admin", "customer_care"].includes(session.user?.role) ? "ready" : "denied",
            user: session.user || null,
          });
        }
      } catch {
        if (!ignore) setAuthState({ status: "denied", user: null });
      }
    }
    checkSession();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 861px)");
    function handleScreenChange(event) {
      if (event.matches) setMobileMenuOpen(false);
    }
    desktopQuery.addEventListener("change", handleScreenChange);
    return () => desktopQuery.removeEventListener("change", handleScreenChange);
  }, []);

  useEffect(() => {
    if (authState.status !== "ready") return undefined;
    let ignore = false;
    async function loadBadges() {
      try {
        const [desk, mail] = await Promise.all([fetchCustomerCareDesk(), fetchCustomerCareMail()]);
        if (ignore) return;
        const unreadTicketMessages = (desk.support_tickets || []).reduce(
          (total, ticket) => total + Number(ticket.unread_patient_messages || 0),
          0,
        );
        setBadgeCounts({
          tickets: unreadTicketMessages,
          messages: (mail.messages || []).filter((message) => !message.read_at).length,
        });
      } catch {}
    }
    loadBadges();
    const intervalId = window.setInterval(loadBadges, 15000);
    window.addEventListener("synmed:customer-care-notifications-updated", loadBadges);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
      window.removeEventListener("synmed:customer-care-notifications-updated", loadBadges);
    };
  }, [authState.status]);

  function handleLogout() {
    clearAuthToken();
    navigate("/", { replace: true });
  }

  if (authState.status === "loading") {
    return <div className="admin-portal__loading">Checking customer care session...</div>;
  }
  if (authState.status !== "ready") {
    return <Navigate to="/signin" replace />;
  }

  const activePanel = new URLSearchParams(location.search).get("panel") || "overview";
  const visibleNav = CUSTOMER_CARE_NAV.filter((item) => !item.adminOnly || authState.user?.role === "admin").map((item) => ({
    ...item,
    badge: item.panel === "tickets" ? badgeCounts.tickets : item.panel === "messages" ? badgeCounts.messages : 0,
  }));

  return (
    <div className="admin-portal customer-care-portal">
      <aside className={mobileMenuOpen ? "admin-sidebar admin-sidebar--mobile-open" : "admin-sidebar"}>
        <NavLink className="admin-sidebar__brand" to="/customer-care">
          <img src="/logo-removebg-preview.png" alt="" />
          <span>
            <small>SynMed Support</small>
            <strong>Customer Care</strong>
          </span>
        </NavLink>

        <nav className="admin-sidebar__nav customer-care-sidebar__nav" aria-label="Customer care sections">
          {visibleNav.map((item) => (
            <NavLink
              className={activePanel === item.panel ? "admin-sidebar__link admin-sidebar__link--active" : "admin-sidebar__link"}
              key={item.panel}
              to={`/customer-care?panel=${item.panel}`}
            >
              <span>{item.label}</span>
              {item.badge ? <span className="admin-sidebar__badge">{item.badge > 99 ? "99+" : item.badge}</span> : null}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar__account customer-care-sidebar__account">
          <span>{authState.user?.display_name || "Customer agent"}</span>
          <button type="button" onClick={handleLogout} aria-label="Log out" title="Log out">
            Sign out
          </button>
        </div>
      </aside>

      <div className="admin-portal__workspace">
        <div className="admin-mobile-nav">
          <button
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Close customer care menu" : "Open customer care menu"}
            className="admin-mobile-nav__menu"
            type="button"
            onClick={() => setMobileMenuOpen((current) => !current)}
          >
            <span aria-hidden="true" />
            <span aria-hidden="true" />
            <span aria-hidden="true" />
          </button>
          <div>
            <small>SynMed Support</small>
            <strong>Customer Care</strong>
          </div>
        </div>
        {mobileMenuOpen ? (
          <button
            aria-label="Close customer care menu"
            className="admin-sidebar-backdrop"
            type="button"
            onClick={() => setMobileMenuOpen(false)}
          />
        ) : null}
        <main className="admin-portal__main customer-care-main">
          <Outlet context={{ user: authState.user }} />
        </main>
      </div>
    </div>
  );
}
