import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import {
  clearPendingDoctorLoginIdentifier,
  loginDoctor,
  restoreSession,
  setPendingDoctorLoginIdentifier,
} from "../api/auth.js";
import "../styles/forms.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function DoctorSignInPage() {
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState({
    identifier: "",
    password: "",
    otpChannel: "telegram",
  });
  const [state, setState] = useState({
    status: "idle",
    message: "Sign in with your verified doctor ID or registered email, then complete OTP delivery on the next step.",
    debugCode: "",
  });

  useEffect(() => {
    let ignore = false;

    async function bootstrapSession() {
      try {
        const session = await restoreSession();
        if (!ignore && session.user?.role === "doctor") {
          navigate("/doctor", { replace: true });
        }
      } catch {}
    }

    clearPendingDoctorLoginIdentifier();
    bootstrapSession();
    return () => {
      ignore = true;
    };
  }, [navigate]);

  async function handleSubmit(event) {
    event.preventDefault();
    setState({
      status: "loading",
      message: `Sending doctor OTP via ${credentials.otpChannel}...`,
      debugCode: "",
    });

    try {
      const result = await loginDoctor(
        credentials.identifier.trim(),
        credentials.password,
        credentials.otpChannel,
      );
      setPendingDoctorLoginIdentifier(credentials.identifier.trim());
      setState({
        status: "success",
        message: `OTP sent to ${result.delivery_target}. Redirecting to verification...`,
        debugCode: result.debug_code || "",
      });
      navigate("/doctor/login-otp", { replace: true });
    } catch (error) {
      setState({
        status: "error",
        message: error.message || "Unable to sign in right now.",
        debugCode: "",
      });
    }
  }

  return (
    <SectionCard
      title="Doctor Sign In"
      subtitle="Use your verified SynMed doctor identity, password, and preferred OTP delivery channel."
    >
      <form className="form-panel" onSubmit={handleSubmit}>
        <label className="form-field">
          <span className="form-field__label">Doctor ID or Registered Email</span>
          <input
            className="form-field__input"
            type="text"
            value={credentials.identifier}
            onChange={(event) =>
              setCredentials((current) => ({ ...current, identifier: event.target.value }))
            }
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">Password</span>
          <input
            className="form-field__input"
            type="password"
            value={credentials.password}
            onChange={(event) =>
              setCredentials((current) => ({ ...current, password: event.target.value }))
            }
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">Receive OTP Through</span>
          <select
            className="form-field__input"
            value={credentials.otpChannel}
            onChange={(event) =>
              setCredentials((current) => ({ ...current, otpChannel: event.target.value }))
            }
          >
            <option value="telegram">Telegram</option>
            <option value="email">Email</option>
          </select>
        </label>
        <button className="button button--primary" type="submit">
          Sign In
        </button>
      </form>

      <div className={`lookup-result lookup-result--${state.status}`}>
        <p className="lookup-result__message">{state.message}</p>
        {state.debugCode ? <p className="lookup-result__message">Dev OTP: {state.debugCode}</p> : null}
      </div>

      <p className="patient-auth-link">
        First time on web? <Link to="/doctor/signup">Activate doctor web access</Link>
      </p>
      <p className="patient-auth-link">
        Forgot password? <Link to="/doctor/recover">Recover doctor account</Link>
      </p>
    </SectionCard>
  );
}
