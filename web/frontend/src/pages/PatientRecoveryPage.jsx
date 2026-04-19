import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  requestPatientRecovery,
  setPendingPatientRecoveryIdentifier,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function PatientRecoveryPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState({
    identifier: "",
    email: "",
    newPassword: "",
  });
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Use this once if you already have a SynMed patient record but have not set up web access yet.",
    debugCode: "",
  });

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: "Sending recovery OTP to your email...",
      debugCode: "",
    });

    try {
      const result = await requestPatientRecovery(
        formState.identifier.trim(),
        formState.email.trim(),
        formState.newPassword,
      );
      setPendingPatientRecoveryIdentifier(formState.identifier.trim());
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
    <SectionCard
      title="Recover Existing Patient Account"
      subtitle="Set your password and verify your email without registering a new patient profile."
    >
      <form className="form-panel" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-field__label">Hospital Number, Phone, or Email</span>
          <input
            className="form-field__input"
            type="text"
            value={formState.identifier}
            onChange={(event) =>
              setFormState((current) => ({ ...current, identifier: event.target.value }))
            }
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">Email Address</span>
          <input
            className="form-field__input"
            type="email"
            value={formState.email}
            onChange={(event) =>
              setFormState((current) => ({ ...current, email: event.target.value }))
            }
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">New Password</span>
          <input
            className="form-field__input"
            type="password"
            value={formState.newPassword}
            onChange={(event) =>
              setFormState((current) => ({ ...current, newPassword: event.target.value }))
            }
          />
        </label>
        <button className="button button--primary" type="submit">
          Send Recovery OTP
        </button>
      </form>

      <div className={`lookup-result lookup-result--${status.kind}`}>
        <p className="lookup-result__message">{status.message}</p>
        {status.debugCode ? <p className="lookup-result__message">Dev OTP: {status.debugCode}</p> : null}
      </div>

      <p className="patient-auth-link">
        Already have your password? <Link to="/patient/signin">Back to sign in</Link>
      </p>
    </SectionCard>
  );
}
