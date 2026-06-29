import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import { initializePayment, verifyPayment } from "../api/payments.js";
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
  const [registrationState, setRegistrationState] = useState({
    status: flow.registrationPatient ? "success" : "idle",
    message: "",
    patient: flow.registrationPatient,
  });
  const [paymentState, setPaymentState] = useState({
    status: flow.newPayment ? "restored" : "idle",
    message: "",
    payment: flow.newPayment,
  });
  const hasPendingPayment =
    paymentState.status === "loading" && Boolean(paymentState.payment && !registrationState.patient);

  useEffect(() => {
    if (!paymentState.payment?.reference || registrationState.patient) {
      return undefined;
    }

    let cancelled = false;
    let timeoutId = null;

    async function pollVerification() {
      try {
        const result = await verifyPayment(paymentState.payment.reference);
        if (cancelled) {
          return;
        }

        if (result.verified && result.patient) {
          setPaymentState({
            status: "success",
            message: "",
            payment: result,
          });
          setRegistrationState({
            status: "success",
            message: "",
            patient: result.patient,
          });
          savePatientFlow({
            registrationPatient: result.patient,
            newPayment: result,
          });
          window.setTimeout(() => {
            navigate("/signin", { replace: true });
          }, 1600);
          return;
        }

        setPaymentState((current) => ({
          ...current,
          status: "pending",
          message: "",
        }));
      } catch {
        if (!cancelled) {
          setPaymentState((current) => ({
            ...current,
            status: current.payment?.paystack_status === "success" ? "pending" : current.status,
            message: current.message,
          }));
        }
      }

      if (!cancelled) {
        timeoutId = window.setTimeout(pollVerification, 5000);
      }
    }

    timeoutId = window.setTimeout(pollVerification, 2500);

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [navigate, paymentState.payment?.reference, paymentState.payment?.paystack_status, registrationState.patient]);

  function updateRegistrationField(field, value) {
    setRegistrationForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleRegistrationSubmit(event) {
    event.preventDefault();
    setPaymentState({
      status: "loading",
      message: "Initializing registration payment...",
      payment: null,
    });
    setRegistrationState({
      status: "idle",
      message: "Payment is being prepared. Complete payment to finish registration.",
      patient: null,
    });

    try {
      const result = await initializePayment({
        email: registrationForm.email.trim(),
        patient_type: "new",
        registration_payload: {
          ...registrationForm,
          age: Number(registrationForm.age),
        },
      });
      setPaymentState({
        status: "loading",
        message: "Redirecting to secure payment...",
        payment: result,
      });
      savePatientFlow({
        newPayment: result,
      });
      if (result.authorization_url) {
        window.setTimeout(() => {
          window.location.assign(result.authorization_url);
        }, 450);
      }
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to initialize registration payment.",
        payment: null,
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap login-page__wrap--wide">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        {hasPendingPayment ? <h2 className="login-page__inline-title">Confirming your registration</h2> : null}
          {!hasPendingPayment ? (
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
                <button className="button button--primary login-page__button" type="submit">
                  Register
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
              <div className={`lookup-result lookup-result--${paymentState.status}`}>
                <p className="lookup-result__message">Redirecting you securely to payment...</p>
              </div>
            </div>
          )}

          {paymentState.status === "error" ? (
            <div className={`lookup-result lookup-result--${paymentState.status}`}>
              <p className="lookup-result__message">{paymentState.message}</p>
            </div>
          ) : null}
          {!hasPendingPayment && paymentState.payment?.authorization_url && paymentState.status !== "restored" ? (
            <div className={`lookup-result lookup-result--${paymentState.status}`}>
              <div className="payment-actions">
                <a className="button button--secondary" href={paymentState.payment.authorization_url} target="_blank" rel="noreferrer">
                  Open Paystack Checkout
                </a>
              </div>
            </div>
          ) : null}

      </div>
    </div>
  );
}
