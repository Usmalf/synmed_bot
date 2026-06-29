import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingPatientRecoveryIdentifier,
  getPendingPatientRecoveryIdentifier,
  verifyPatientRecovery,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/auth.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function PatientRecoveryOtpPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Enter the OTP sent to your email to finish activating your web account.",
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
    <AuthShell
      eyebrow="Recovery Verification"
      title="Confirm the recovery code and restore access."
      body="Once this one-time code is accepted, the patient’s email and new password become the active web access path."
      asideTitle="This finishes the recovery flow."
      asideBody="After verification, the patient can go straight back to the normal sign-in experience with the updated password."
    >
      <SectionCard
        title="Verify Recovery OTP"
        subtitle="Enter the one-time recovery code to complete patient account activation."
      >
        <form className="form-panel" onSubmit={handleVerify}>
          <label className="form-field">
            <span className="form-field__label">Recovery OTP</span>
            <input
              className="form-field__input"
              type="text"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value)}
            />
          </label>
          <button className="button button--primary" type="submit">
            Complete Recovery
          </button>
        </form>

        <div className={`lookup-result lookup-result--${status.kind}`}>
          <p className="lookup-result__message">{status.message}</p>
        </div>

        <p className="patient-auth-link">
          Need to start again? <Link to="/patient/recover">Back to recovery</Link>
        </p>
      </SectionCard>
    </AuthShell>
  );
}
