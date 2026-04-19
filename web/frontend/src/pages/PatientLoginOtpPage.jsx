import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingPatientLoginIdentifier,
  getPendingPatientLoginIdentifier,
  verifyPatientLogin,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function PatientLoginOtpPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpState, setOtpState] = useState({
    status: "idle",
    message: "Enter the OTP sent to your email to complete sign in.",
  });

  useEffect(() => {
    const pendingIdentifier = getPendingPatientLoginIdentifier();
    if (!pendingIdentifier) {
      navigate("/patient/signin", { replace: true });
      return;
    }
    setIdentifier(pendingIdentifier);
  }, [navigate]);

  async function handleVerify(event) {
    event.preventDefault();
    setOtpState({
      status: "loading",
      message: "Verifying login OTP...",
    });

    try {
      await verifyPatientLogin(identifier, otpCode.trim());
      clearPendingPatientLoginIdentifier();
      setOtpState({
        status: "success",
        message: "Login successful. Redirecting to patient home...",
      });
      navigate("/patient", { replace: true });
    } catch (error) {
      setOtpState({
        status: "error",
        message: error.message || "Unable to verify login OTP right now.",
      });
    }
  }

  return (
    <SectionCard
      title="Verify Login"
      subtitle="We sent a sign-in OTP to your email address. Enter it here to continue into your patient dashboard."
    >
      <form className="form-panel" onSubmit={handleVerify}>
        <label className="form-field">
          <span className="form-field__label">Login OTP</span>
          <input
            className="form-field__input"
            type="text"
            value={otpCode}
            onChange={(event) => setOtpCode(event.target.value)}
          />
        </label>
        <button className="button button--primary" type="submit">
          Verify OTP
        </button>
      </form>

      <div className={`lookup-result lookup-result--${otpState.status}`}>
        <p className="lookup-result__message">{otpState.message}</p>
      </div>

      <p className="patient-auth-link">
        Need to change your details? <Link to="/patient/signin">Back to sign in</Link>
      </p>
    </SectionCard>
  );
}
