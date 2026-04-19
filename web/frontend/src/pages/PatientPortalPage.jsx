import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearAuthToken, restoreSession } from "../api/auth.js";
import { fetchCurrentPatient } from "../api/patients.js";
import "../styles/patient.css";
import "../styles/patient-portal.css";

const navItems = [
  { to: "/patient", label: "Patient Home", end: true },
  { to: "/patient/account", label: "Account" },
  { to: "/patient/documents", label: "Prescriptions" },
  { to: "/patient/history", label: "Past History" },
  { to: "/patient/appointments", label: "Appointments" },
  { to: "/patient/followup", label: "Follow-Up" },
];

const publicPatientPaths = new Set([
  "/patient/signin",
  "/patient/login-otp",
  "/patient/register",
  "/patient/recover",
  "/patient/recover/verify",
  "/patient/verify-email",
]);

export default function PatientPortalPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [sessionState, setSessionState] = useState({
    status: "idle",
    patient: null,
  });

  useEffect(() => {
    let ignore = false;

    async function loadSession() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "patient") {
          return;
        }
        const currentPatient = await fetchCurrentPatient();
        if (!ignore) {
          setSessionState({
            status: "success",
            patient: currentPatient.patient,
          });
          if (publicPatientPaths.has(location.pathname)) {
            navigate("/patient", { replace: true });
          }
        }
      } catch {
        if (!ignore) {
          setSessionState({
            status: "idle",
            patient: null,
          });
          if (!publicPatientPaths.has(location.pathname)) {
            navigate("/patient/signin", { replace: true });
          }
        }
      }
    }

    loadSession();
    return () => {
      ignore = true;
    };
  }, [location.pathname, navigate]);

  function handleSignOut() {
    clearAuthToken();
    setSessionState({
      status: "idle",
      patient: null,
    });
    navigate("/patient/signin", { replace: true });
  }

  return (
    <div className="patient-shell">
      {sessionState.patient ? (
        <nav className="workspace-nav" aria-label="Patient workspace navigation">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              end={item.end}
              to={item.to}
              className={({ isActive }) =>
                isActive ? "workspace-nav__link workspace-nav__link--active" : "workspace-nav__link"
              }
            >
              {item.label}
            </NavLink>
          ))}
          <button
            className="workspace-nav__link workspace-nav__link--button workspace-nav__link--logout"
            type="button"
            onClick={handleSignOut}
          >
            Log Out
          </button>
        </nav>
      ) : null}

      <Outlet />
    </div>
  );
}
