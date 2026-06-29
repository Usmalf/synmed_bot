import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  dismissAdminAlert,
  fetchAdminAlerts,
  fetchAdminMail,
  markAdminAlertReviewed,
} from "../api/admin.js";
import CustomerSupportWidget from "../components/CustomerSupportWidget.jsx";

const BACKGROUND_OPTIONS = [
  { key: "dark", label: "Dark" },
  { key: "light", label: "Light" },
];

const STORAGE_KEY = "synmed-background-theme";
const DOCTOR_CONSULTATION_VIEW_KEY = "synmed_doctor_consultation_view_active";

function getSystemTheme() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "dark";
  }

  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

const AUTH_ONLY_ROUTES = new Set([
  "/signin",
  "/login-otp",
  "/patient/signin",
  "/patient/login-otp",
  "/patient/register",
  "/patient/recover",
  "/patient/recover/verify",
  "/patient/verify-email",
  "/doctor/signin",
  "/doctor/login-otp",
  "/doctor/signup",
  "/doctor/signup-verify",
  "/doctor/recover",
  "/doctor/recover/verify",
]);

export default function SiteShell({ header, children }) {
  const location = useLocation();
  const [backgroundTheme, setBackgroundTheme] = useState(() => {
    if (typeof window === "undefined") {
      return getSystemTheme();
    }
    return window.localStorage.getItem(STORAGE_KEY) || getSystemTheme();
  });
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [adminNotifications, setAdminNotifications] = useState({
    unreadMessages: [],
    alerts: [],
  });
  const [adminNotificationsOpen, setAdminNotificationsOpen] = useState(false);
  const [adminNotificationBusy, setAdminNotificationBusy] = useState("");
  const [doctorConsultationViewActive, setDoctorConsultationViewActive] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.sessionStorage.getItem(DOCTOR_CONSULTATION_VIEW_KEY) === "true";
  });
  const adminNotificationsRef = useRef(null);

  useEffect(() => {
    document.body.dataset.backgroundTheme = backgroundTheme;
    window.localStorage.setItem(STORAGE_KEY, backgroundTheme);
  }, [backgroundTheme]);

  useEffect(() => {
    if (location.hash) {
      return;
    }

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [location.pathname, location.hash]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const handleScroll = () => {
      setShowBackToTop(window.scrollY > 420);
    };

    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const isAdminWorkspaceRoute = location.pathname.startsWith("/admin");
  const isCustomerCareWorkspaceRoute = location.pathname.startsWith("/customer-care");
  const isDoctorWorkspaceRoute =
    location.pathname.startsWith("/doctor") && !AUTH_ONLY_ROUTES.has(location.pathname);
  const isPatientConsultationRoute = location.pathname === "/consultation";
  const isPatientDashboardRoute = location.pathname === "/patient";

  useEffect(() => {
    function syncDoctorConsultationView() {
      setDoctorConsultationViewActive(
        window.sessionStorage.getItem(DOCTOR_CONSULTATION_VIEW_KEY) === "true",
      );
    }
    window.addEventListener("storage", syncDoctorConsultationView);
    window.addEventListener("synmed:doctor-consultation-view", syncDoctorConsultationView);
    syncDoctorConsultationView();
    return () => {
      window.removeEventListener("storage", syncDoctorConsultationView);
      window.removeEventListener("synmed:doctor-consultation-view", syncDoctorConsultationView);
    };
  }, []);

  useEffect(() => {
    if (!isAdminWorkspaceRoute) {
      setAdminNotifications({ unreadMessages: [], alerts: [] });
      setAdminNotificationsOpen(false);
      return undefined;
    }

    let ignore = false;
    async function syncAdminNotifications() {
      try {
        const [mail, operational] = await Promise.all([
          fetchAdminMail(),
          fetchAdminAlerts(),
        ]);
        if (!ignore) {
          setAdminNotifications({
            unreadMessages: (mail.messages || []).filter((message) => !message.read_at),
            alerts: operational.alerts || [],
          });
        }
      } catch {}
    }

    syncAdminNotifications();
    const intervalId = window.setInterval(syncAdminNotifications, 30000);
    window.addEventListener("synmed:admin-mail-updated", syncAdminNotifications);
    window.addEventListener("synmed:admin-notifications-updated", syncAdminNotifications);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
      window.removeEventListener("synmed:admin-mail-updated", syncAdminNotifications);
      window.removeEventListener("synmed:admin-notifications-updated", syncAdminNotifications);
    };
  }, [isAdminWorkspaceRoute]);

  useEffect(() => {
    setAdminNotificationsOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!adminNotificationsOpen) return undefined;
    function closeNotifications(event) {
      if (!adminNotificationsRef.current?.contains(event.target)) {
        setAdminNotificationsOpen(false);
      }
    }
    document.addEventListener("mousedown", closeNotifications);
    return () => document.removeEventListener("mousedown", closeNotifications);
  }, [adminNotificationsOpen]);

  function handleBackToTop() {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleAdminAlertAction(alert, action) {
    const busyKey = `${action}:${alert.id}`;
    setAdminNotificationBusy(busyKey);
    try {
      if (action === "dismiss") {
        await dismissAdminAlert(alert.id);
        setAdminNotifications((current) => ({
          ...current,
          alerts: current.alerts.filter((item) => item.id !== alert.id),
        }));
      } else {
        await markAdminAlertReviewed(alert.id);
        setAdminNotifications((current) => ({
          ...current,
          alerts: current.alerts.map((item) =>
            item.id === alert.id ? { ...item, reviewed: true } : item,
          ),
        }));
      }
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch {
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } finally {
      setAdminNotificationBusy("");
    }
  }

  const hideHeader =
    AUTH_ONLY_ROUTES.has(location.pathname) ||
    isAdminWorkspaceRoute ||
    isCustomerCareWorkspaceRoute ||
    isDoctorWorkspaceRoute;
  const isPatientWorkspaceRoute =
    location.pathname.startsWith("/patient") && !AUTH_ONLY_ROUTES.has(location.pathname);
  const showCustomerSupportWidget =
    location.pathname === "/" ||
    (isPatientWorkspaceRoute && location.pathname !== "/patient/consultation");
  const showBackHome = AUTH_ONLY_ROUTES.has(location.pathname);
  const backLink = isPatientWorkspaceRoute ? "/patient" : "/";
  const backLabel = isPatientWorkspaceRoute ? "Back to dashboard" : "Back to home";
  const adminNotificationCount =
    adminNotifications.unreadMessages.length +
    adminNotifications.alerts.filter((alert) => !alert.reviewed).length;

  return (
    <div className="site-shell">
      {!hideHeader ? <header className="site-shell__header">{header}</header> : null}
      {showBackHome ? (
        <Link className="site-shell__back-home" to={backLink}>
          {"\u2190"} {backLabel}
        </Link>
      ) : null}
      {!isPatientConsultationRoute && !(isDoctorWorkspaceRoute && doctorConsultationViewActive) ? (
        <div
          className={
            isAdminWorkspaceRoute
              ? "site-shell__controls site-shell__controls--admin"
              : isCustomerCareWorkspaceRoute
                ? "site-shell__controls site-shell__controls--customer-care"
              : isDoctorWorkspaceRoute
                ? "site-shell__controls site-shell__controls--doctor"
              : isPatientDashboardRoute
                ? "site-shell__controls site-shell__controls--patient-dashboard"
                : "site-shell__controls"
          }
          aria-label="Workspace controls"
        >
        {isAdminWorkspaceRoute ? (
          <div className="site-shell__notification-center" ref={adminNotificationsRef}>
            <button
              aria-label={
                adminNotificationCount
                  ? `Admin notifications, ${adminNotificationCount} items`
                  : "Admin notifications"
              }
              aria-expanded={adminNotificationsOpen}
              className="site-shell__message-link"
              title="Notifications"
              type="button"
              onClick={() => setAdminNotificationsOpen((current) => !current)}
            >
              <span className="site-shell__message-icon" aria-hidden="true">&#9993;</span>
              {adminNotificationCount ? (
                <span className="site-shell__message-notification">
                  <span className="site-shell__message-bell" aria-hidden="true" />
                  <span>{adminNotificationCount > 99 ? "99+" : adminNotificationCount}</span>
                </span>
              ) : null}
            </button>
            {adminNotificationsOpen ? (
              <div className="site-shell__notification-panel">
                <header>
                  <div>
                    <strong>Notifications</strong>
                    <span>{adminNotificationCount} item(s) need attention</span>
                  </div>
                  <Link to="/admin/inbox">Inbox</Link>
                </header>
                <div className="site-shell__notification-list">
                  {adminNotifications.unreadMessages.slice(0, 4).map((message) => (
                    <Link className="site-shell__notification-item site-shell__notification-item--message site-shell__notification-copy" key={`message-${message.id}`} to="/admin/inbox">
                      <strong>{message.subject}</strong>
                      <span>Unread message from {message.sender_role === "doctor" ? `Doctor ${message.sender_id}` : "administrator"}</span>
                    </Link>
                  ))}
                  {adminNotifications.alerts.map((alert) => (
                    <article
                      className={
                        alert.reviewed
                          ? `site-shell__notification-item site-shell__notification-item--${alert.tone} site-shell__notification-item--reviewed`
                          : `site-shell__notification-item site-shell__notification-item--${alert.tone}`
                      }
                      key={alert.id}
                    >
                      <Link
                        className="site-shell__notification-copy"
                        to={alert.href}
                        onClick={() => {
                          if (!alert.reviewed) {
                            handleAdminAlertAction(alert, "review");
                          }
                        }}
                      >
                        <strong>{alert.title}</strong>
                        <span>{alert.message}</span>
                      </Link>
                      <div className="site-shell__notification-actions">
                        {!alert.reviewed ? (
                          <button
                            disabled={Boolean(adminNotificationBusy)}
                            type="button"
                            onClick={() => handleAdminAlertAction(alert, "review")}
                          >
                            {adminNotificationBusy === `review:${alert.id}` ? "Saving..." : "Mark reviewed"}
                          </button>
                        ) : (
                          <span>Reviewed</span>
                        )}
                        {alert.dismissible ? (
                          <button
                            disabled={Boolean(adminNotificationBusy)}
                            type="button"
                            onClick={() => handleAdminAlertAction(alert, "dismiss")}
                          >
                            {adminNotificationBusy === `dismiss:${alert.id}` ? "Dismissing..." : "Dismiss"}
                          </button>
                        ) : null}
                      </div>
                    </article>
                  ))}
                  {!adminNotifications.unreadMessages.length && !adminNotifications.alerts.length ? (
                    <p className="site-shell__notification-empty">No current notifications.</p>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
        <span className="site-shell__controls-label">Theme</span>
        <div className="site-shell__controls-group">
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
        </div>
      ) : null}
      <main
        className={
          isAdminWorkspaceRoute || isCustomerCareWorkspaceRoute || isDoctorWorkspaceRoute || isPatientConsultationRoute
            ? "site-shell__main site-shell__main--workspace"
            : "site-shell__main"
        }
      >
        {children}
      </main>
      {showBackToTop ? (
        <button
          className="site-shell__back-to-top"
          type="button"
          onClick={handleBackToTop}
          aria-label="Back to top"
          title="Back to top"
        >
          {"\u2191"}
        </button>
      ) : null}
      {showCustomerSupportWidget ? <CustomerSupportWidget nudgedUp={showBackToTop} /> : null}
    </div>
  );
}
