import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import { registerPatient } from "../api/patients.js";
import { loadPatientFlow, savePatientFlow } from "../lib/patientFlowStorage.js";
import "../styles/forms.css";
import "../styles/login.css";
import "../styles/patient.css";

export default function PatientRegistrationPage() {
  const navigate = useNavigate();
  const flow = loadPatientFlow();
  const [registrationForm, setRegistrationForm] = useState({
    name: "",
    age: "",
    gender: "",
    phone: "",
    address: "",
    allergy: "",
    medical_conditions: "",
    email: "",
    password: "",
  });
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [registrationState, setRegistrationState] = useState({
    status: flow.registrationPatient ? "success" : "idle",
    message: "",
    patient: flow.registrationPatient,
  });
  const registrationCompleted = registrationState.status === "success";

  function updateRegistrationField(field, value) {
    setRegistrationForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleRegistrationSubmit(event) {
    event.preventDefault();
    if (!termsAccepted) {
      setRegistrationState({
        status: "error",
        message: "Please agree to the Terms and Conditions before registration.",
        patient: null,
      });
      return;
    }
    setRegistrationState({
      status: "loading",
      message: "Creating your SynMed account...",
      patient: null,
    });

    try {
      const result = await registerPatient({
        ...registrationForm,
        age: Number(registrationForm.age),
      });
      setRegistrationState({
        status: "success",
        message: result.message,
        patient: result.patient || null,
      });
      savePatientFlow({
        registrationPatient: result.patient || null,
        newPayment: null,
      });
      window.setTimeout(() => {
        navigate("/signin", { replace: true });
      }, 3500);
    } catch (error) {
      setRegistrationState({
        status: "error",
        message: error.message || "Unable to complete registration.",
        patient: null,
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap login-page__wrap--wide">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

          {!registrationCompleted ? (
            <>
              <form className="form-panel" onSubmit={handleRegistrationSubmit}>
                <label className="form-field">
                  <span className="form-field__label">Full Name</span>
                  <input className="form-field__input" type="text" value={registrationForm.name} onChange={(event) => updateRegistrationField("name", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Age</span>
                  <input className="form-field__input" type="number" min="0" value={registrationForm.age} onChange={(event) => updateRegistrationField("age", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Gender</span>
                  <input className="form-field__input" type="text" value={registrationForm.gender} onChange={(event) => updateRegistrationField("gender", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Phone</span>
                  <input className="form-field__input" type="tel" value={registrationForm.phone} onChange={(event) => updateRegistrationField("phone", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Email</span>
                  <input className="form-field__input" type="email" value={registrationForm.email} onChange={(event) => updateRegistrationField("email", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Password</span>
                  <PasswordInput value={registrationForm.password} onChange={(event) => updateRegistrationField("password", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Address</span>
                  <textarea className="form-field__input form-field__input--textarea" rows="3" value={registrationForm.address} onChange={(event) => updateRegistrationField("address", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Allergies</span>
                  <input className="form-field__input" type="text" placeholder="None" value={registrationForm.allergy} onChange={(event) => updateRegistrationField("allergy", event.target.value)} />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Prior Medical Conditions</span>
                  <input className="form-field__input" type="text" placeholder="Hypertension, diabetes, sickle cell, asthma..." value={registrationForm.medical_conditions} onChange={(event) => updateRegistrationField("medical_conditions", event.target.value)} />
                </label>
                <label className="login-page__checkbox">
                  <input
                    className="login-page__checkbox-input"
                    type="checkbox"
                    checked={termsAccepted}
                    onChange={(event) => setTermsAccepted(event.target.checked)}
                    required
                  />
                  <span>
                    I agree to the <Link to="/terms" target="_blank" rel="noreferrer">Terms and Conditions</Link>.
                  </span>
                </label>
                <button className="button button--primary login-page__button" type="submit" disabled={!termsAccepted || registrationState.status === "loading"}>
                  {registrationState.status === "loading" ? "Creating account..." : "Register"}
                </button>
              </form>

              <div className="login-page__links">
                <p>
                  Already registered? <Link to="/signin">Sign in here</Link>
                </p>
              </div>
            </>
          ) : (
            <div className="login-page__status-panel">
              <div className="lookup-result lookup-result--success">
                <p className="lookup-result__message">
                  {registrationState.message ||
                    "Registration completed. Please check your email and verify your account before signing in."}
                </p>
                <div className="payment-actions">
                  <Link className="button button--primary" to="/signin">
                    Go to Sign In
                  </Link>
                </div>
              </div>
            </div>
          )}

          {registrationState.status === "error" && !registrationCompleted ? (
            <div className={`lookup-result lookup-result--${registrationState.status}`}>
              <p className="lookup-result__message">{registrationState.message}</p>
            </div>
          ) : null}

      </div>
    </div>
  );
}
