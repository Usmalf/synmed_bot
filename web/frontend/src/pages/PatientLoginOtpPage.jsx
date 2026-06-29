import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthShell from "../components/AuthShell.jsx";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingPatientLoginIdentifier,
  getPendingPatientLoginIdentifier,
  verifyPatientLogin,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/auth.css";
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
    <AuthShell
      eyebrow="Patient Verification"
      title="Confirm the login code and enter the dashboard."
      body="This step is separated from the sign-in page so the patient flow stays clear and predictable."
      asideTitle="Only one more step remains."
      asideBody="The OTP sent to your selected delivery channel confirms that the person signing in still controls the registered contact path."
      asidePoints={[
        {
          title: "Fast re-entry",
          body: "Once this code is accepted, SynMed sends you straight into the patient workspace.",
        },
      ]}
    >
      <SectionCard
        title="Verify Login"
        subtitle="Enter the one-time code you received to complete patient sign in."
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
    </AuthShell>
  );
}
