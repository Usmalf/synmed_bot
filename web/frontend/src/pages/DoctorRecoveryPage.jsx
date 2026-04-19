import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { requestDoctorRecovery, setPendingDoctorRecoveryIdentifier } from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorRecoveryPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState({
    identifier: "",
    email: "",
    newPassword: "",
    otpChannel: "email",
  });
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Reset your doctor web password and choose whether the recovery OTP should reach you through email or Telegram.",
    debugCode: "",
  });

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: `Sending recovery OTP via ${formState.otpChannel}...`,
      debugCode: "",
    });

    try {
      const result = await requestDoctorRecovery(
        formState.identifier.trim(),
        formState.email.trim(),
        formState.newPassword,
        formState.otpChannel,
      );
      setPendingDoctorRecoveryIdentifier(formState.identifier.trim());
      setStatus({
        kind: "success",
        message: "Recovery OTP sent. Redirecting to verification...",
        debugCode: result.debug_code || "",
      });
      navigate("/doctor/recover/verify", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to start doctor recovery right now.",
        debugCode: "",
      });
    }
  }

  return (
    <SectionCard
      title="Recover Doctor Account"
      subtitle="Reset your doctor web password securely without affecting your verified SynMed doctor profile."
    >
      <form className="form-panel" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-field__label">Doctor ID or Registered Email</span>
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
        <label className="form-field">
          <span className="form-field__label">Receive OTP Through</span>
          <select
            className="form-field__input"
            value={formState.otpChannel}
            onChange={(event) =>
              setFormState((current) => ({ ...current, otpChannel: event.target.value }))
            }
          >
            <option value="email">Email</option>
            <option value="telegram">Telegram</option>
          </select>
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
        Remembered your password? <Link to="/doctor/signin">Back to sign in</Link>
      </p>
    </SectionCard>
  );
}
