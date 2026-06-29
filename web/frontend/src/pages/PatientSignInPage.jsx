import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import PasswordInput from "../components/PasswordInput.jsx";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingPatientLoginIdentifier,
  loginPatient,
  restoreSession,
  setPendingPatientLoginIdentifier,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/auth.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function PatientSignInPage() {
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState({
    identifier: "",
    password: "",
    otpChannel: "email",
  });
  const [signInState, setSignInState] = useState({
    status: "idle",
    message: "Sign in with hospital number, phone number, or email plus your password.",
    debugCode: "",
  });

  useEffect(() => {
    let ignore = false;

    async function bootstrapSession() {
      try {
        const session = await restoreSession();
        if (!ignore && session.user?.role === "patient") {
          navigate("/patient", { replace: true });
        }
      } catch {}
    }

    clearPendingPatientLoginIdentifier();
    bootstrapSession();
    return () => {
      ignore = true;
    };
  }, [navigate]);

  async function handleSignIn(event) {
    event.preventDefault();
    setSignInState({
      status: "loading",
      message: "Sending login OTP to your email...",
      debugCode: "",
    });

    try {
      const identifier = credentials.identifier.trim();
      const result = await loginPatient(identifier, credentials.password, credentials.otpChannel);
      setPendingPatientLoginIdentifier(identifier);
      setSignInState({
        status: "success",
        message: `OTP sent to ${result.delivery_target}. Redirecting to the verification page...`,
        debugCode: result.debug_code || "",
      });
      navigate("/patient/login-otp", { replace: true });
    } catch (error) {
      setSignInState({
        status: "error",
        message: error.message || "Unable to sign in right now.",
        debugCode: "",
      });
    }
  }

  return (
    <AuthShell
      eyebrow="Patient Access"
      title="Sign in to the patient portal."
      body="Use the patient record details you registered with, then complete the OTP step on the next screen."
      asideTitle="A guided login, not a crowded entry page."
      asideBody="Credentials are checked first, then SynMed sends a one-time code to your chosen delivery channel before access opens."
      asidePoints={[
        {
          title: "Use one identifier",
          body: "Hospital number, phone number, or email all work here as long as they belong to the same patient record.",
        },
        {
          title: "OTP stays separate",
          body: "The verification code appears on its own step so the sign-in page stays calmer and easier to understand.",
        },
      ]}
    >
      <SectionCard
        title="Patient Sign In"
        subtitle="Enter your details below, then continue to the OTP verification step."
      >
        <form className="form-panel" onSubmit={handleSignIn}>
          <label className="form-field">
            <span className="form-field__label">Hospital Number, Phone, or Email</span>
            <input
              className="form-field__input"
              type="text"
              value={credentials.identifier}
              onChange={(event) =>
                setCredentials((current) => ({ ...current, identifier: event.target.value }))
              }
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">Password</span>
            <PasswordInput
              value={credentials.password}
              onChange={(event) =>
                setCredentials((current) => ({ ...current, password: event.target.value }))
              }
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">Receive OTP Through</span>
            <select
              className="form-field__input"
              value={credentials.otpChannel}
              onChange={(event) =>
                setCredentials((current) => ({ ...current, otpChannel: event.target.value }))
              }
            >
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
            </select>
          </label>
          <button className="button button--primary" type="submit">
            Continue To OTP
          </button>
        </form>

        <div className={`lookup-result lookup-result--${signInState.status}`}>
          <p className="lookup-result__message">{signInState.message}</p>
          {signInState.debugCode ? (
            <p className="lookup-result__message">Dev OTP: {signInState.debugCode}</p>
          ) : null}
        </div>

        <p className="patient-auth-link">
          Forgot password or need to activate web access? <Link to="/patient/recover">Recover account</Link>
        </p>
        <p className="patient-auth-link">
          New patient? <Link to="/patient/register">Sign up here</Link>
        </p>
      </SectionCard>
    </AuthShell>
  );
}
