import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { restoreSession } from "../api/auth.js";
import { fetchCurrentPatient } from "../api/patients.js";
import "../styles/patient.css";
import "../styles/patient-portal.css";

const publicPatientPaths = new Set([
  "/signin",
  "/login-otp",
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
            navigate("/signin", { replace: true });
          }
        }
      }
    }

    loadSession();
    return () => {
      ignore = true;
    };
  }, [location.pathname, navigate]);

  return (
    <div className="patient-shell">
      <Outlet />
    </div>
  );
}
