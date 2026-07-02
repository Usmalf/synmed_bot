import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  clearAuthToken,
  clearPendingDoctorLoginIdentifier,
  clearPendingDoctorRecoveryIdentifier,
  clearPendingDoctorSignupIdentifier,
  clearPendingLogin,
  clearPendingPatientLoginIdentifier,
  clearPendingPatientRecoveryIdentifier,
  restoreSession,
} from "./api/auth.js";
import SiteShell from "./layouts/SiteShell.jsx";
import AdminLayout from "./layouts/AdminLayout.jsx";
import CustomerCareLayout from "./layouts/CustomerCareLayout.jsx";
import DoctorLayout from "./layouts/DoctorLayout.jsx";
import {
  AdminActivityPage,
  AdminConsultationsPage,
  AdminContentPage,
  AdminDoctorsPage,
  AdminErrorsPage,
  AdminInboxPage,
  AdminOverviewPage,
  AdminPaymentsPage,
  AdminPatientsPage,
  AdminPartnersPage,
  AdminRatingsPage,
  AdminReportsPage,
  AdminSettingsPage,
  AdminTicketLogPage,
} from "./pages/admin/AdminPortalPages.jsx";
import ConsultationPage from "./pages/ConsultationPage.jsx";
import CustomerCareDashboardPage from "./pages/CustomerCareDashboardPage.jsx";
import DoctorAccountPage from "./pages/DoctorAccountPage.jsx";
import DoctorDashboardPage from "./pages/DoctorDashboardPage.jsx";
import DoctorMedicalReportRequestsPage from "./pages/DoctorMedicalReportRequestsPage.jsx";
import DoctorMessagesPage from "./pages/DoctorMessagesPage.jsx";
import DoctorRecoveryOtpPage from "./pages/DoctorRecoveryOtpPage.jsx";
import DoctorRecoveryPage from "./pages/DoctorRecoveryPage.jsx";
import DoctorSignupPage from "./pages/DoctorSignupPage.jsx";
import DoctorSignupVerifyPage from "./pages/DoctorSignupVerifyPage.jsx";
import LandingPage from "./pages/LandingPage.jsx";
import { PrivacyPage, TermsPage } from "./pages/LegalPages.jsx";
import PatientAccountPage from "./pages/PatientAccountPage.jsx";
import PatientAppointmentsPage from "./pages/PatientAppointmentsPage.jsx";
import PatientConsultationRequestPage from "./pages/PatientConsultationRequestPage.jsx";
import PatientDocumentsPage from "./pages/PatientDocumentsPage.jsx";
import PatientFollowUpPage from "./pages/PatientFollowUpPage.jsx";
import PatientHistoryPage from "./pages/PatientHistoryPage.jsx";
import PatientMedicalReportRequestPage from "./pages/PatientMedicalReportRequestPage.jsx";
import PatientPortalPage from "./pages/PatientPortalPage.jsx";
import PatientRecoveryOtpPage from "./pages/PatientRecoveryOtpPage.jsx";
import PatientRecoveryPage from "./pages/PatientRecoveryPage.jsx";
import PatientRegistrationPage from "./pages/PatientRegistrationPage.jsx";
import PatientReturningPage from "./pages/PatientReturningPage.jsx";
import PatientSetupPasswordPage from "./pages/PatientSetupPasswordPage.jsx";
import PatientVerifyEmailPage from "./pages/PatientVerifyEmailPage.jsx";
import PatientWorkspaceHomePage from "./pages/PatientWorkspaceHomePage.jsx";
import WebLoginOtpPage from "./pages/WebLoginOtpPage.jsx";
import WebSignInPage from "./pages/WebSignInPage.jsx";

const navItems = [
  { to: "/", label: "Home" },
  { to: "/patient", label: "Patients" },
  { to: "/doctor", label: "Doctors" },
  { href: "/#contact", label: "Contact Us" },
];

const patientNavItems = [
  { to: "/patient", label: "Patient Home", end: true },
  { to: "/patient/account", label: "Account" },
  { to: "/patient/documents", label: "Documents" },
  { to: "/patient/medical-report-request", label: "Request Medical Report" },
  { to: "/patient/appointments", label: "Appointments" },
  { to: "/patient/followup", label: "Follow-Up" },
];

const INACTIVITY_LOGOUT_MS = 30 * 60 * 1000;
const SESSION_IDLE_CHECK_MS = 30 * 1000;
const SESSION_LAST_ACTIVITY_KEY = "synmed_session_last_activity_at";
const LOGOUT_HOME_REDIRECT_KEY = "synmed_logout_redirect_home";
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart", "input"];

function AppNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const inactivityTimeoutRef = useRef(null);
  const inactivityIntervalRef = useRef(null);
  const lastSessionActivityRef = useRef(Date.now());
  const [sessionUser, setSessionUser] = useState(null);
  const [patientMenuOpen, setPatientMenuOpen] = useState(false);
  const [landingMenuOpen, setLandingMenuOpen] = useState(false);
  const [landingDropdownOpen, setLandingDropdownOpen] = useState("");

  useEffect(() => {
    let ignore = false;

    async function syncSession() {
      try {
        const session = await restoreSession();
        if (!ignore && session.user) {
          setSessionUser(session.user);
          return;
        }
      } catch {}

      if (!ignore) {
        setSessionUser(null);
      }
    }

    syncSession();
    window.addEventListener("synmed:session-updated", syncSession);
    return () => {
      ignore = true;
      window.removeEventListener("synmed:session-updated", syncSession);
    };
  }, [location.pathname]);

  useEffect(() => {
    setPatientMenuOpen(false);
    setLandingMenuOpen(false);
    setLandingDropdownOpen("");
  }, [location.pathname]);

  useEffect(() => {
    if (!patientMenuOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function handleKeyDown(event) {
      if (event.key === "Escape") setPatientMenuOpen(false);
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [patientMenuOpen]);

  function handleLogout() {
    clearAuthToken();
    clearPendingLogin();
    clearPendingDoctorLoginIdentifier();
    clearPendingDoctorRecoveryIdentifier();
    clearPendingDoctorSignupIdentifier();
    clearPendingPatientLoginIdentifier();
    clearPendingPatientRecoveryIdentifier();
    window.localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);
    window.sessionStorage.setItem(LOGOUT_HOME_REDIRECT_KEY, "true");
    setSessionUser(null);
    navigate("/", { replace: true });
  }

  function closeLandingMenu() {
    setLandingMenuOpen(false);
    setLandingDropdownOpen("");
  }

  useEffect(() => {
    const shouldTrackIdle = sessionUser?.role === "patient" || sessionUser?.role === "doctor";
    if (!shouldTrackIdle) {
      if (inactivityTimeoutRef.current) {
        window.clearTimeout(inactivityTimeoutRef.current);
        inactivityTimeoutRef.current = null;
      }
      if (inactivityIntervalRef.current) {
        window.clearInterval(inactivityIntervalRef.current);
        inactivityIntervalRef.current = null;
      }
      return undefined;
    }

    function markSessionActivity() {
      const now = Date.now();
      lastSessionActivityRef.current = now;
      window.localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(now));
      if (inactivityTimeoutRef.current) {
        window.clearTimeout(inactivityTimeoutRef.current);
      }

      inactivityTimeoutRef.current = window.setTimeout(() => {
        checkSessionIdleTime();
      }, INACTIVITY_LOGOUT_MS);
    }

    function getLastSessionActivity() {
      const storedValue = Number(window.localStorage.getItem(SESSION_LAST_ACTIVITY_KEY));
      return Number.isFinite(storedValue) && storedValue > 0
        ? storedValue
        : lastSessionActivityRef.current;
    }

    function checkSessionIdleTime() {
      if (Date.now() - getLastSessionActivity() >= INACTIVITY_LOGOUT_MS) {
        window.localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);
        handleLogout();
        return true;
      }
      return false;
    }

    markSessionActivity();
    ACTIVITY_EVENTS.forEach((eventName) => {
      window.addEventListener(eventName, markSessionActivity, { passive: true });
    });
    window.addEventListener("focus", checkSessionIdleTime);
    window.addEventListener("visibilitychange", checkSessionIdleTime);
    inactivityIntervalRef.current = window.setInterval(checkSessionIdleTime, SESSION_IDLE_CHECK_MS);

    return () => {
      ACTIVITY_EVENTS.forEach((eventName) => {
        window.removeEventListener(eventName, markSessionActivity);
      });
      window.removeEventListener("focus", checkSessionIdleTime);
      window.removeEventListener("visibilitychange", checkSessionIdleTime);
      if (inactivityTimeoutRef.current) {
        window.clearTimeout(inactivityTimeoutRef.current);
        inactivityTimeoutRef.current = null;
      }
      if (inactivityIntervalRef.current) {
        window.clearInterval(inactivityIntervalRef.current);
        inactivityIntervalRef.current = null;
      }
    };
  }, [sessionUser]);

  if (
    sessionUser?.role === "patient" &&
    (location.pathname === "/consultation" || location.pathname === "/patient/consultation")
  ) {
    return null;
  }

  if (sessionUser?.role === "patient") {
    return (
      <>
        <div className="patient-mobile-nav">
          <button
            aria-expanded={patientMenuOpen}
            aria-label={patientMenuOpen ? "Close patient menu" : "Open patient menu"}
            className="patient-mobile-nav__menu"
            type="button"
            onClick={() => setPatientMenuOpen((current) => !current)}
          >
            <span aria-hidden="true" />
            <span aria-hidden="true" />
            <span aria-hidden="true" />
          </button>
          <img className="patient-mobile-nav__logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
          <div>
            <small>SynMed Patient</small>
            <strong>My Health Workspace</strong>
          </div>
        </div>
        <nav
          className={
            patientMenuOpen
              ? "top-nav top-nav--workspace top-nav--patient top-nav--patient-open"
              : "top-nav top-nav--workspace top-nav--patient"
          }
          aria-label="Patient workspace navigation"
        >
          <button
            aria-label="Close patient menu"
            className="patient-nav__close"
            type="button"
            onClick={() => setPatientMenuOpen(false)}
          >
            &#215;
          </button>
          <div className="top-nav__patient-brand" aria-label="SynMed Telehealth">
            <img className="top-nav__patient-logo" src="/logo-removebg-preview.png" alt="" />
            <div>
              <span>SynMed Telehealth</span>
              <strong>Patient Workspace</strong>
            </div>
          </div>
          <div className="top-nav__workspace-links">
            {patientNavItems.map((item) => (
              <NavLink
                key={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive ? "top-nav__link top-nav__link--active" : "top-nav__link"
                }
                to={item.to}
              >
                {item.label}
              </NavLink>
            ))}
            <button className="top-nav__link top-nav__link--logout" type="button" onClick={handleLogout}>
              Log Out
            </button>
          </div>
        </nav>
        {patientMenuOpen ? (
          <button
            aria-label="Close patient menu"
            className="patient-nav-backdrop"
            type="button"
            onClick={() => setPatientMenuOpen(false)}
          />
        ) : null}
      </>
    );
  }

  if (sessionUser?.role === "doctor") {
    return null;
  }

  if (sessionUser?.role === "admin") {
    return null;
  }

  if (sessionUser?.role === "customer_care") {
    return null;
  }

  return (
    <>
    <nav className={landingMenuOpen ? "top-nav top-nav--landing-open" : "top-nav"} aria-label="Primary navigation">
      <div className="top-nav__brand">
        <div className="top-nav__brand-mark">
          <img className="top-nav__logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>
        <div className="top-nav__brand-copy">
          <span className="top-nav__eyebrow">SynMed Telehealth</span>
          <strong className="top-nav__title">Your Health In Sync</strong>
        </div>
      </div>

      <button
        aria-expanded={landingMenuOpen}
        aria-label={landingMenuOpen ? "Close navigation menu" : "Open navigation menu"}
        className="top-nav__menu-toggle"
        type="button"
        onClick={() => {
          setLandingMenuOpen((current) => {
            const nextOpen = !current;
            if (!nextOpen) setLandingDropdownOpen("");
            return nextOpen;
          });
        }}
      >
        <span aria-hidden="true" />
        <span aria-hidden="true" />
        <span aria-hidden="true" />
      </button>

      <div className="top-nav__links">
        {navItems.map((item) => (
          item.href ? (
            <a
              key={item.href}
              className="top-nav__link"
              href={item.href}
              onClick={closeLandingMenu}
            >
              {item.label}
            </a>
          ) : (
            <NavLink
              key={item.to}
              className={({ isActive }) =>
                isActive ? "top-nav__link top-nav__link--active" : "top-nav__link"
              }
              to={item.to}
              onClick={closeLandingMenu}
            >
              {item.label}
            </NavLink>
          )
        ))}
        <div
          className={
            landingDropdownOpen === "partners"
              ? "top-nav__policy-menu top-nav__policy-menu--open"
              : "top-nav__policy-menu"
          }
        >
          <button
            aria-expanded={landingDropdownOpen === "partners"}
            className="top-nav__link top-nav__dropdown-trigger"
            type="button"
            onClick={() =>
              setLandingDropdownOpen((current) => (current === "partners" ? "" : "partners"))
            }
          >
            Partners
          </button>
          <div className="top-nav__policy-links">
            <span className="top-nav__coming-soon-link">Pharmacy <em>Coming soon</em></span>
            <span className="top-nav__coming-soon-link">Laboratory <em>Coming soon</em></span>
          </div>
        </div>
        <div
          className={
            landingDropdownOpen === "policies"
              ? "top-nav__policy-menu top-nav__policy-menu--open"
              : "top-nav__policy-menu"
          }
        >
          <button
            aria-expanded={landingDropdownOpen === "policies"}
            className="top-nav__link top-nav__dropdown-trigger"
            type="button"
            onClick={() =>
              setLandingDropdownOpen((current) => (current === "policies" ? "" : "policies"))
            }
          >
            Policies
          </button>
          <div className="top-nav__policy-links">
            <Link to="/terms" onClick={closeLandingMenu}>Terms of Use</Link>
            <Link to="/privacy" onClick={closeLandingMenu}>Privacy Policy</Link>
          </div>
        </div>
      </div>

      <div className="top-nav__actions">
        <NavLink
          className="button button--primary top-nav__action top-nav__signin"
          to="/signin"
          onClick={closeLandingMenu}
        >
          Sign In
        </NavLink>
        {sessionUser?.role === "doctor" ? (
          <>
            <NavLink className="button button--secondary top-nav__action" to="/doctor/account">
              Account
            </NavLink>
            <button className="button button--secondary top-nav__action" type="button" onClick={handleLogout}>
              Log Out
            </button>
          </>
        ) : null}
      </div>
    </nav>
    {landingMenuOpen ? (
      <button
        aria-label="Close navigation menu"
        className="landing-nav-backdrop"
        type="button"
        onClick={closeLandingMenu}
      />
    ) : null}
    </>
  );
}

export default function App() {
  return (
    <SiteShell header={<AppNav />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/signin" element={<WebSignInPage />} />
        <Route path="/login-otp" element={<WebLoginOtpPage />} />
        <Route path="/patient" element={<PatientPortalPage />}>
          <Route index element={<PatientWorkspaceHomePage />} />
          <Route path="account" element={<PatientAccountPage />} />
          <Route path="documents" element={<PatientDocumentsPage />} />
          <Route path="signin" element={<WebSignInPage />} />
          <Route path="login-otp" element={<WebLoginOtpPage />} />
          <Route path="history" element={<PatientHistoryPage />} />
          <Route path="medical-report-request" element={<PatientMedicalReportRequestPage />} />
          <Route path="appointments" element={<PatientAppointmentsPage />} />
          <Route path="followup" element={<PatientFollowUpPage />} />
          <Route path="recover" element={<PatientRecoveryPage />} />
          <Route path="recover/verify" element={<PatientRecoveryOtpPage />} />
          <Route path="setup-password" element={<PatientSetupPasswordPage />} />
          <Route path="verify-email" element={<PatientVerifyEmailPage />} />
          <Route path="returning" element={<PatientReturningPage />} />
          <Route path="register" element={<PatientRegistrationPage />} />
          <Route path="consultation" element={<PatientConsultationRequestPage />} />
        </Route>
        <Route path="/doctor" element={<DoctorLayout />}>
          <Route index element={<DoctorDashboardPage />} />
          <Route path="medical-reports" element={<DoctorMedicalReportRequestsPage />} />
          <Route path="account" element={<DoctorAccountPage />} />
          <Route path="messages" element={<DoctorMessagesPage />} />
        </Route>
        <Route path="/doctor/signin" element={<WebSignInPage />} />
        <Route path="/doctor/login-otp" element={<WebLoginOtpPage />} />
        <Route path="/doctor/signup" element={<DoctorSignupPage />} />
        <Route path="/doctor/signup-verify" element={<DoctorSignupVerifyPage />} />
        <Route path="/doctor/recover" element={<DoctorRecoveryPage />} />
        <Route path="/doctor/recover/verify" element={<DoctorRecoveryOtpPage />} />
        <Route path="/consultation" element={<ConsultationPage />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminOverviewPage />} />
          <Route path="doctors" element={<AdminDoctorsPage />} />
          <Route path="patients" element={<AdminPatientsPage />} />
          <Route path="consultations" element={<AdminConsultationsPage />} />
          <Route path="payments" element={<AdminPaymentsPage />} />
          <Route path="reports" element={<AdminReportsPage />} />
          <Route path="partners" element={<AdminPartnersPage />} />
          <Route path="ratings" element={<AdminRatingsPage />} />
          <Route path="content" element={<AdminContentPage />} />
          <Route path="settings" element={<AdminSettingsPage />} />
          <Route path="inbox" element={<AdminInboxPage />} />
          <Route path="ticket-log" element={<AdminTicketLogPage />} />
          <Route path="errors" element={<AdminErrorsPage />} />
          <Route path="activity" element={<AdminActivityPage />} />
        </Route>
        <Route path="/customer-care" element={<CustomerCareLayout />}>
          <Route index element={<CustomerCareDashboardPage />} />
        </Route>
      </Routes>
    </SiteShell>
  );
}
