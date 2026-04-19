import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingDoctorRecoveryIdentifier,
  getPendingDoctorRecoveryIdentifier,
  verifyDoctorRecovery,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorRecoveryOtpPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Enter the OTP sent to finish doctor account recovery.",
  });

  useEffect(() => {
    const pendingIdentifier = getPendingDoctorRecoveryIdentifier();
    if (!pendingIdentifier) {
      navigate("/doctor/recover", { replace: true });
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
      await verifyDoctorRecovery(identifier, otpCode.trim());
      clearPendingDoctorRecoveryIdentifier();
      setStatus({
        kind: "success",
        message: "Recovery completed. Redirecting to doctor sign in...",
      });
      navigate("/doctor/signin", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to verify recovery OTP right now.",
      });
    }
  }

  return (
    <SectionCard
      title="Verify Doctor Recovery"
      subtitle="Once this OTP is confirmed, your new doctor web password will be active."
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
        Need to start again? <Link to="/doctor/recover">Back to doctor recovery</Link>
      </p>
    </SectionCard>
  );
}
