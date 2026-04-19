import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingDoctorSignupIdentifier,
  getPendingDoctorSignupIdentifier,
  verifyDoctorSignup,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorSignupVerifyPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Enter the OTP that was sent to complete doctor web activation.",
  });

  useEffect(() => {
    const pendingIdentifier = getPendingDoctorSignupIdentifier();
    if (!pendingIdentifier) {
      navigate("/doctor/signup", { replace: true });
      return;
    }
    setIdentifier(pendingIdentifier);
  }, [navigate]);

  async function handleVerify(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: "Verifying activation OTP...",
    });

    try {
      await verifyDoctorSignup(identifier, otpCode.trim());
      clearPendingDoctorSignupIdentifier();
      setStatus({
        kind: "success",
        message: "Doctor web access activated. Redirecting to sign in...",
      });
      navigate("/doctor/signin", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to verify activation OTP right now.",
      });
    }
  }

  return (
    <SectionCard
      title="Verify Doctor Activation"
      subtitle="Confirm the OTP to finish creating your doctor web access."
    >
      <form className="form-panel" onSubmit={handleVerify}>
        <label className="form-field">
          <span className="form-field__label">Activation OTP</span>
          <input
            className="form-field__input"
            type="text"
            value={otpCode}
            onChange={(event) => setOtpCode(event.target.value)}
          />
        </label>
        <button className="button button--primary" type="submit">
          Complete Activation
        </button>
      </form>

      <div className={`lookup-result lookup-result--${status.kind}`}>
        <p className="lookup-result__message">{status.message}</p>
      </div>

      <p className="patient-auth-link">
        Need to start again? <Link to="/doctor/signup">Back to activation</Link>
      </p>
    </SectionCard>
  );
}
