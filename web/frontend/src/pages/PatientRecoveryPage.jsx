import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import {
  requestPatientRecovery,
  setPendingPatientRecoveryIdentifier,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/login.css";

export default function PatientRecoveryPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState({
    email: "",
    newPassword: "",
    confirmPassword: "",
  });
  const [status, setStatus] = useState({
    kind: "idle",
    message: "",
    debugCode: "",
  });

  async function handleSubmit(event) {
    event.preventDefault();
    const email = formState.email.trim().toLowerCase();
    if (!email) {
      setStatus({ kind: "error", message: "Enter your registered email address.", debugCode: "" });
      return;
    }
    if (formState.newPassword.length < 6) {
      setStatus({ kind: "error", message: "Password must be at least 6 characters long.", debugCode: "" });
      return;
    }
    if (formState.newPassword !== formState.confirmPassword) {
      setStatus({ kind: "error", message: "Passwords do not match.", debugCode: "" });
      return;
    }

    setStatus({
      kind: "loading",
      message: "Sending recovery OTP to your email...",
      debugCode: "",
    });

    try {
      const result = await requestPatientRecovery(email, email, formState.newPassword);
      setPendingPatientRecoveryIdentifier(email);
      setStatus({
        kind: "success",
        message: "Recovery OTP sent. Redirecting to verification...",
        debugCode: result.debug_code || "",
      });
      navigate("/patient/recover/verify", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to start recovery right now.",
        debugCode: "",
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <div className="login-page__plain-panel">
          <h1 className="login-page__inline-title">Recover your account</h1>
          <p className="login-page__plain-subtitle">Reset access with your registered email</p>
          <form className="form-panel" onSubmit={handleSubmit}>
            <label className="form-field">
              <span className="form-field__label">Email Address</span>
              <input
                className="form-field__input"
                type="email"
                autoComplete="email"
                value={formState.email}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, email: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">New Password</span>
              <PasswordInput
                value={formState.newPassword}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, newPassword: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Confirm Password</span>
              <PasswordInput
                value={formState.confirmPassword}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, confirmPassword: event.target.value }))
                }
              />
            </label>
            <button className="button button--primary login-page__button" type="submit">
              Send Recovery OTP
            </button>
          </form>

          {status.message ? (
            <div className={`lookup-result lookup-result--${status.kind}`}>
              <p className="lookup-result__message">{status.message}</p>
              {status.debugCode ? <p className="lookup-result__message">Dev OTP: {status.debugCode}</p> : null}
            </div>
          ) : null}

          <div className="login-page__links">
            <p>
              Remembered your password? <Link to="/signin">Back to sign in</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
