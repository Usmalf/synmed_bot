import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingPatientRecoveryIdentifier,
  getPendingPatientRecoveryIdentifier,
  verifyPatientRecovery,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/login.css";

export default function PatientRecoveryOtpPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [status, setStatus] = useState({
    kind: "idle",
    message: "",
  });

  useEffect(() => {
    const pendingIdentifier = getPendingPatientRecoveryIdentifier();
    if (!pendingIdentifier) {
      navigate("/patient/recover", { replace: true });
      return;
    }
    setIdentifier(pendingIdentifier);
  }, [navigate]);

  async function handleVerify(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: "Verifying recovery OTP...",
    });

    try {
      await verifyPatientRecovery(identifier, otpCode.trim());
      clearPendingPatientRecoveryIdentifier();
      setStatus({
        kind: "success",
        message: "Recovery completed. Redirecting to sign in...",
      });
      navigate("/signin", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to verify recovery OTP right now.",
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <SectionCard title="Verify recovery code" subtitle="Enter the OTP sent to your email">
          <form className="form-panel" onSubmit={handleVerify}>
            <label className="form-field">
              <span className="form-field__label">Recovery OTP</span>
              <input
                className="form-field__input"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value)}
              />
            </label>
            <button className="button button--primary login-page__button" type="submit">
              Complete Recovery
            </button>
          </form>

          {status.message ? (
            <div className={`lookup-result lookup-result--${status.kind}`}>
              <p className="lookup-result__message">{status.message}</p>
            </div>
          ) : null}

          <div className="login-page__links">
            <p>
              Need to start again? <Link to="/patient/recover">Back to recovery</Link>
            </p>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
