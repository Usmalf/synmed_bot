import { useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import {
  clearAuthToken,
  clearPendingDoctorLoginIdentifier,
  clearPendingDoctorRecoveryIdentifier,
  clearPendingDoctorSignupIdentifier,
  clearPendingPatientLoginIdentifier,
  clearPendingPatientRecoveryIdentifier,
  restoreSession,
} from "./api/auth.js";
import SiteShell from "./layouts/SiteShell.jsx";
import AdminDashboardPage from "./pages/AdminDashboardPage.jsx";
import ConsultationPage from "./pages/ConsultationPage.jsx";
import DoctorAccountPage from "./pages/DoctorAccountPage.jsx";
import DoctorDashboardPage from "./pages/DoctorDashboardPage.jsx";
import DoctorLoginOtpPage from "./pages/DoctorLoginOtpPage.jsx";
import DoctorRecoveryOtpPage from "./pages/DoctorRecoveryOtpPage.jsx";
import DoctorRecoveryPage from "./pages/DoctorRecoveryPage.jsx";
import DoctorSignInPage from "./pages/DoctorSignInPage.jsx";
import DoctorSignupPage from "./pages/DoctorSignupPage.jsx";
import DoctorSignupVerifyPage from "./pages/DoctorSignupVerifyPage.jsx";
import LandingPage from "./pages/LandingPage.jsx";
import PatientAccountPage from "./pages/PatientAccountPage.jsx";
import PatientAppointmentsPage from "./pages/PatientAppointmentsPage.jsx";
import PatientConsultationRequestPage from "./pages/PatientConsultationRequestPage.jsx";
import PatientDocumentsPage from "./pages/PatientDocumentsPage.jsx";
import PatientFollowUpPage from "./pages/PatientFollowUpPage.jsx";
import PatientHistoryPage from "./pages/PatientHistoryPage.jsx";
import PatientLoginOtpPage from "./pages/PatientLoginOtpPage.jsx";
import PatientPortalPage from "./pages/PatientPortalPage.jsx";
import PatientRecoveryOtpPage from "./pages/PatientRecoveryOtpPage.jsx";
import PatientRecoveryPage from "./pages/PatientRecoveryPage.jsx";
import PatientRegistrationPage from "./pages/PatientRegistrationPage.jsx";
import PatientReturningPage from "./pages/PatientReturningPage.jsx";
import PatientSignInPage from "./pages/PatientSignInPage.jsx";
import PatientVerifyEmailPage from "./pages/PatientVerifyEmailPage.jsx";
import PatientWorkspaceHomePage from "./pages/PatientWorkspaceHomePage.jsx";

const navItems = [
  { to: "/", label: "Home" },
  { to: "/patient", label: "Patient Portal" },
  { to: "/doctor", label: "Doctor Dashboard" },
  { to: "/admin", label: "Admin" },
];

function AppNav() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sessionUser, setSessionUser] = useState(null);

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
    return () => {
      ignore = true;
    };
  }, [location.pathname]);

  function handleLogout() {
    clearAuthToken();
    clearPendingDoctorLoginIdentifier();
    clearPendingDoctorRecoveryIdentifier();
    clearPendingDoctorSignupIdentifier();
    clearPendingPatientLoginIdentifier();
    clearPendingPatientRecoveryIdentifier();
    setSessionUser(null);
    navigate("/");
  }

  return (
    <nav className="top-nav" aria-label="Primary navigation">
      <div className="top-nav__brand">
        <div className="top-nav__brand-mark">
          <img className="top-nav__logo" src="/synmed_logo.png" alt="SynMed Telehealth" />
        </div>
        <div className="top-nav__brand-copy">
          <span className="top-nav__eyebrow">SynMed Telehealth</span>
          <strong className="top-nav__title">Digital care, organized calmly.</strong>
        </div>
      </div>

      <div className="top-nav__links">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            className={({ isActive }) =>
              isActive ? "top-nav__link top-nav__link--active" : "top-nav__link"
            }
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </div>

      <div className="top-nav__actions">
        {sessionUser?.role === "patient" ? (
          <>
            <NavLink className="button button--secondary top-nav__action" to="/patient/account">
              👤 Account
            </NavLink>
            <button className="button button--secondary top-nav__action" type="button" onClick={handleLogout}>
              Log Out
            </button>
          </>
        ) : sessionUser?.role === "doctor" ? (
          <>
            <NavLink className="button button--secondary top-nav__action" to="/doctor/account">
              🩺 Account
            </NavLink>
            <button className="button button--secondary top-nav__action" type="button" onClick={handleLogout}>
              Log Out
            </button>
          </>
        ) : (
          <NavLink className="button button--secondary top-nav__action" to="/patient/signin">
            Patient Login
          </NavLink>
        )}
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <SiteShell header={<AppNav />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/patient" element={<PatientPortalPage />}>
          <Route index element={<PatientWorkspaceHomePage />} />
          <Route path="account" element={<PatientAccountPage />} />
          <Route path="documents" element={<PatientDocumentsPage />} />
          <Route path="signin" element={<PatientSignInPage />} />
          <Route path="login-otp" element={<PatientLoginOtpPage />} />
          <Route path="history" element={<PatientHistoryPage />} />
          <Route path="appointments" element={<PatientAppointmentsPage />} />
          <Route path="followup" element={<PatientFollowUpPage />} />
          <Route path="recover" element={<PatientRecoveryPage />} />
          <Route path="recover/verify" element={<PatientRecoveryOtpPage />} />
          <Route path="verify-email" element={<PatientVerifyEmailPage />} />
          <Route path="returning" element={<PatientReturningPage />} />
          <Route path="register" element={<PatientRegistrationPage />} />
          <Route path="consultation" element={<PatientConsultationRequestPage />} />
        </Route>
        <Route path="/doctor" element={<DoctorDashboardPage />} />
        <Route path="/doctor/account" element={<DoctorAccountPage />} />
        <Route path="/doctor/signin" element={<DoctorSignInPage />} />
        <Route path="/doctor/login-otp" element={<DoctorLoginOtpPage />} />
        <Route path="/doctor/signup" element={<DoctorSignupPage />} />
        <Route path="/doctor/signup-verify" element={<DoctorSignupVerifyPage />} />
        <Route path="/doctor/recover" element={<DoctorRecoveryPage />} />
        <Route path="/doctor/recover/verify" element={<DoctorRecoveryOtpPage />} />
        <Route path="/consultation" element={<ConsultationPage />} />
        <Route path="/admin" element={<AdminDashboardPage />} />
      </Routes>
    </SiteShell>
  );
}
