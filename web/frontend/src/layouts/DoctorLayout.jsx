import { useEffect, useState } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  clearAuthToken,
  clearPendingDoctorLoginIdentifier,
  clearPendingDoctorRecoveryIdentifier,
  clearPendingDoctorSignupIdentifier,
  clearPendingLogin,
  restoreSession,
} from "../api/auth.js";
import { fetchDoctorMail, fetchDoctorWorkspace, updateDoctorPresence } from "../api/doctors.js";
import "../styles/doctor.css";

const DOCTOR_CONSULTATION_VIEW_KEY = "synmed_doctor_consultation_view_active";
const SESSION_LAST_ACTIVITY_KEY = "synmed_session_last_activity_at";
const BACKGROUND_THEME_KEY = "synmed-background-theme";
const BACKGROUND_OPTIONS = [
  { key: "dark", label: "Dark" },
  { key: "light", label: "Light" },
];
const doctorLinks = [
  { to: "/doctor", label: "Dashboard", end: true },
  { to: "/doctor/medical-reports", label: "Medical Report Requests" },
  { to: "/doctor/account", label: "My account" },
];

function isOnlineStatus(status) {
  return status === "available" || status === "busy";
}

export default function DoctorLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [authState, setAuthState] = useState({ status: "loading", user: null });
  const [presence, setPresence] = useState("offline");
  const [presenceUpdating, setPresenceUpdating] = useState(false);
  const [unreadMessages, setUnreadMessages] = useState(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [backgroundTheme, setBackgroundTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    return window.localStorage.getItem(BACKGROUND_THEME_KEY) || document.body.dataset.backgroundTheme || "dark";
  });
  const [consultationViewActive, setConsultationViewActive] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.sessionStorage.getItem(DOCTOR_CONSULTATION_VIEW_KEY) === "true";
  });

  useEffect(() => {
    let ignore = false;
    async function checkSession() {
      try {
        const session = await restoreSession();
        if (ignore) return;
        if (session.user?.role !== "doctor") {
          setAuthState({ status: "denied", user: session.user || null });
          return;
        }
        setAuthState({ status: "ready", user: session.user });
        try {
          const workspace = await fetchDoctorWorkspace();
          if (!ignore) setPresence(workspace.doctor?.status || "offline");
        } catch {
          if (!ignore) setPresence("offline");
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
    document.body.dataset.backgroundTheme = backgroundTheme;
    window.localStorage.setItem(BACKGROUND_THEME_KEY, backgroundTheme);
  }, [backgroundTheme]);

  useEffect(() => {
    if (authState.status !== "ready") return undefined;
    let ignore = false;
    async function syncUnreadMessages() {
      try {
        const result = await fetchDoctorMail();
        if (!ignore) {
          setUnreadMessages((result.messages || []).filter((message) => !message.read_at).length);
        }
      } catch {}
    }
    syncUnreadMessages();
    const intervalId = window.setInterval(syncUnreadMessages, 30000);
    window.addEventListener("synmed:doctor-mail-updated", syncUnreadMessages);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
      window.removeEventListener("synmed:doctor-mail-updated", syncUnreadMessages);
    };
  }, [authState.status]);

  useEffect(() => {
    function syncConsultationView() {
      setConsultationViewActive(
        window.sessionStorage.getItem(DOCTOR_CONSULTATION_VIEW_KEY) === "true",
      );
    }
    function syncPresence(event) {
      const nextPresence = event.detail?.doctor?.status;
      if (nextPresence) setPresence(nextPresence);
    }
    window.addEventListener("storage", syncConsultationView);
    window.addEventListener("synmed:doctor-consultation-view", syncConsultationView);
    window.addEventListener("synmed:doctor-presence-updated", syncPresence);
    syncConsultationView();
    return () => {
      window.removeEventListener("storage", syncConsultationView);
      window.removeEventListener("synmed:doctor-consultation-view", syncConsultationView);
      window.removeEventListener("synmed:doctor-presence-updated", syncPresence);
    };
  }, []);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const desktopQuery = window.matchMedia("(min-width: 861px)");
    function handleScreenChange(event) {
      if (event.matches) setMobileMenuOpen(false);
    }
    desktopQuery.addEventListener("change", handleScreenChange);
    return () => desktopQuery.removeEventListener("change", handleScreenChange);
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function handleKeyDown(event) {
      if (event.key === "Escape") setMobileMenuOpen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [mobileMenuOpen]);

  async function handlePresenceToggle() {
    if (!authState.user) return;
    const nextAction = isOnlineStatus(presence) ? "offline" : "online";
    setPresenceUpdating(true);
    try {
      const result = await updateDoctorPresence({
        doctor_id: authState.user.user_id,
        action: nextAction,
      });
      window.dispatchEvent(new CustomEvent("synmed:doctor-presence-updated", { detail: result }));
      if (result.doctor?.status) {
        setPresence(result.doctor.status);
      } else {
        const workspace = await fetchDoctorWorkspace();
        setPresence(
          workspace.doctor?.status || (nextAction === "online" ? "available" : "offline"),
        );
        window.dispatchEvent(
          new CustomEvent("synmed:doctor-presence-updated", { detail: workspace }),
        );
      }
    } catch {
      try {
        const workspace = await fetchDoctorWorkspace();
        setPresence(workspace.doctor?.status || "offline");
      } catch {}
    } finally {
      setPresenceUpdating(false);
    }
  }

  function handleLogout() {
    clearAuthToken();
    clearPendingLogin();
    clearPendingDoctorLoginIdentifier();
    clearPendingDoctorRecoveryIdentifier();
    clearPendingDoctorSignupIdentifier();
    window.localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);
    window.sessionStorage.removeItem(DOCTOR_CONSULTATION_VIEW_KEY);
    navigate("/", { replace: true });
  }

  if (authState.status === "loading") {
    return <div className="doctor-portal__loading">Checking doctor session...</div>;
  }
  if (authState.status !== "ready") {
    return <Navigate to="/doctor/signin" replace />;
  }
  const consultationFullscreen =
    location.pathname === "/doctor" && consultationViewActive;

  return (
    <div className={consultationFullscreen ? "doctor-portal doctor-portal--consultation" : "doctor-portal"}>
      <aside className={mobileMenuOpen ? "doctor-sidebar doctor-sidebar--mobile-open" : "doctor-sidebar"}>
        <div className="doctor-sidebar__header">
          <NavLink className="doctor-sidebar__brand" to="/doctor">
            <img src="/logo-removebg-preview.png" alt="" />
            <span><small>SynMed Clinical</small><strong>Doctor Workspace</strong></span>
          </NavLink>
          <button
            aria-label="Close doctor menu"
            className="doctor-sidebar__close"
            type="button"
            onClick={() => setMobileMenuOpen(false)}
          >
            &#215;
          </button>
        </div>
        <nav className="doctor-sidebar__nav" aria-label="Doctor workspace">
          {doctorLinks.map((link) => (
            <NavLink
              className={({ isActive }) =>
                isActive ? "doctor-sidebar__link doctor-sidebar__link--active" : "doctor-sidebar__link"
              }
              end={link.end}
              key={link.to}
              to={link.to}
            >
              {link.label}
            </NavLink>
          ))}
          <NavLink
            aria-label={unreadMessages ? `Messages, ${unreadMessages} unread` : "Messages"}
            className={({ isActive }) =>
              isActive
                ? "doctor-sidebar__link doctor-sidebar__link--messages doctor-sidebar__link--active"
                : "doctor-sidebar__link doctor-sidebar__link--messages"
            }
            to="/doctor/messages"
          >
            <span className="doctor-sidebar__message-label">
              <span aria-hidden="true">&#9993;</span>
              Messages
            </span>
            {unreadMessages ? (
              <span className="doctor-sidebar__message-count">
                {unreadMessages > 99 ? "99+" : unreadMessages}
              </span>
            ) : null}
          </NavLink>
        </nav>
        <section className="doctor-sidebar__presence" aria-label="Availability">
          <div>
            <span
              className={
                isOnlineStatus(presence)
                  ? "doctor-sidebar__presence-dot doctor-sidebar__presence-dot--online"
                  : "doctor-sidebar__presence-dot"
              }
              aria-hidden="true"
            />
            <span><small>Availability</small><strong>{isOnlineStatus(presence) ? "Online" : "Offline"}</strong></span>
          </div>
          <button
            className={
              isOnlineStatus(presence)
                ? "doctor-sidebar__presence-button doctor-sidebar__presence-button--online"
                : "doctor-sidebar__presence-button"
            }
            disabled={presenceUpdating}
            type="button"
            onClick={handlePresenceToggle}
          >
            {presenceUpdating ? "Updating..." : isOnlineStatus(presence) ? "Go offline" : "Go online"}
          </button>
        </section>
        <div className="doctor-sidebar__account">
          <span><small>Signed in as</small><strong>{authState.user?.display_name || "Doctor"}</strong></span>
          <button type="button" onClick={handleLogout}>Log out</button>
        </div>
      </aside>

      <div className="doctor-portal__workspace">
        <div className="doctor-mobile-nav">
          <button
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? "Close doctor menu" : "Open doctor menu"}
            className="doctor-mobile-nav__menu"
            type="button"
            onClick={() => setMobileMenuOpen((current) => !current)}
          >
            <span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" />
          </button>
          <div><small>SynMed Clinical</small><strong>Doctor Workspace</strong></div>
          <span className={isOnlineStatus(presence) ? "doctor-mobile-nav__status doctor-mobile-nav__status--online" : "doctor-mobile-nav__status"}>
            {isOnlineStatus(presence) ? "Online" : "Offline"}
          </span>
        </div>
        {mobileMenuOpen ? (
          <button aria-label="Close doctor menu" className="doctor-sidebar-backdrop" type="button" onClick={() => setMobileMenuOpen(false)} />
        ) : null}
        {consultationFullscreen ? (
          <div className="consultation-floating-theme doctor-consultation-theme" aria-label="Theme">
            {BACKGROUND_OPTIONS.map((option) => (
              <button
                key={option.key}
                className={
                  backgroundTheme === option.key
                    ? "site-shell__theme-toggle site-shell__theme-toggle--active"
                    : "site-shell__theme-toggle"
                }
                type="button"
                onClick={() => setBackgroundTheme(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : null}
        <main className="doctor-portal__main">
          <Outlet context={{ user: authState.user, presence }} />
        </main>
      </div>
    </div>
  );
}
