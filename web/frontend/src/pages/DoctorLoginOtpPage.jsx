import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingDoctorLoginIdentifier,
  getPendingDoctorLoginIdentifier,
  verifyDoctorLogin,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorLoginOtpPage() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [state, setState] = useState({
    status: "idle",
    message: "Enter the OTP sent to your chosen doctor channel to complete sign in.",
  });

  useEffect(() => {
    const pendingIdentifier = getPendingDoctorLoginIdentifier();
    if (!pendingIdentifier) {
      navigate("/doctor/signin", { replace: true });
      return;
    }
    setIdentifier(pendingIdentifier);
  }, [navigate]);

  async function handleVerify(event) {
    event.preventDefault();
    setState({
      status: "loading",
      message: "Verifying doctor OTP...",
    });

    try {
      await verifyDoctorLogin(identifier, otpCode.trim());
      clearPendingDoctorLoginIdentifier();
      setState({
        status: "success",
        message: "Doctor login successful. Redirecting to dashboard...",
      });
      navigate("/doctor", { replace: true });
    } catch (error) {
      setState({
        status: "error",
        message: error.message || "Unable to verify doctor OTP right now.",
      });
    }
  }

  return (
    <SectionCard
      title="Verify Doctor Login"
      subtitle="Complete your doctor web sign-in with the OTP we just delivered."
    >
      <form className="form-panel" onSubmit={handleVerify}>
        <label className="form-field">
          <span className="form-field__label">Doctor OTP</span>
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

      <div className={`lookup-result lookup-result--${state.status}`}>
        <p className="lookup-result__message">{state.message}</p>
      </div>

      <p className="patient-auth-link">
        Need to start again? <Link to="/doctor/signin">Back to doctor sign in</Link>
      </p>
    </SectionCard>
  );
}
