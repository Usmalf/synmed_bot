import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { setPendingDoctorSignupIdentifier, signupDoctor } from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorSignupPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState({
    identifier: "",
    email: "",
    password: "",
    otpChannel: "telegram",
  });
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Activate doctor web access with your verified doctor identity and choose whether OTP should reach you on Telegram or email.",
    debugCode: "",
  });

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: `Sending activation OTP via ${formState.otpChannel}...`,
      debugCode: "",
    });

    try {
      const result = await signupDoctor(
        formState.identifier.trim(),
        formState.email.trim(),
        formState.password,
        formState.otpChannel,
      );
      setPendingDoctorSignupIdentifier(formState.identifier.trim());
      setStatus({
        kind: "success",
        message: "Activation OTP sent. Redirecting to verification...",
        debugCode: result.debug_code || "",
      });
      navigate("/doctor/signup-verify", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to activate doctor web access right now.",
        debugCode: "",
      });
    }
  }

  return (
    <SectionCard
      title="Activate Doctor Web Access"
      subtitle="Verified SynMed doctors can create a web password here and confirm activation with OTP."
    >
      <form className="form-panel" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-field__label">Doctor ID or Existing Email</span>
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
          <span className="form-field__label">Create Password</span>
          <input
            className="form-field__input"
            type="password"
            value={formState.password}
            onChange={(event) =>
              setFormState((current) => ({ ...current, password: event.target.value }))
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
            <option value="telegram">Telegram</option>
            <option value="email">Email</option>
          </select>
        </label>
        <button className="button button--primary" type="submit">
          Activate Access
        </button>
      </form>

      <div className={`lookup-result lookup-result--${status.kind}`}>
        <p className="lookup-result__message">{status.message}</p>
        {status.debugCode ? <p className="lookup-result__message">Dev OTP: {status.debugCode}</p> : null}
      </div>

      <p className="patient-auth-link">
        Already activated? <Link to="/doctor/signin">Back to doctor sign in</Link>
      </p>
    </SectionCard>
  );
}
