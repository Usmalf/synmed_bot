import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { fetchPaymentConfig, initializePayment, verifyPayment } from "../api/payments.js";
import { loadPatientFlow, savePatientFlow } from "../lib/patientFlowStorage.js";
import "../styles/forms.css";
import "../styles/patient.css";

export default function PatientRegistrationPage() {
  const navigate = useNavigate();
  const flow = loadPatientFlow();
  const [paymentConfig, setPaymentConfig] = useState(null);
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
    message: flow.registrationPatient
      ? "Registration completed after payment verification."
      : "Enter your details, then click register to continue into payment.",
    patient: flow.registrationPatient,
  });
  const [paymentState, setPaymentState] = useState({
    status: flow.newPayment ? "success" : "idle",
    message: flow.newPayment ? "Saved payment state restored." : "Payment has not started yet.",
    payment: flow.newPayment,
  });

  useEffect(() => {
    let ignore = false;
    async function loadPaymentConfig() {
      try {
        const result = await fetchPaymentConfig();
        if (!ignore) {
          setPaymentConfig(result);
        }
      } catch {
        if (!ignore) {
          setPaymentConfig(null);
        }
      }
    }
    loadPaymentConfig();
    return () => {
      ignore = true;
    };
  }, []);

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
        status: "success",
        message: result.message,
        payment: result,
      });
      savePatientFlow({
        newPayment: result,
      });
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to initialize registration payment.",
        payment: null,
      });
    }
  }

  async function handleVerifyPayment(reference) {
    setPaymentState({
      status: "loading",
      message: "Verifying payment and completing registration...",
      payment: null,
    });

    try {
      const result = await verifyPayment(reference);
      setPaymentState({
        status: result.verified ? "success" : "empty",
        message: result.message,
        payment: result,
      });
      if (result.verified && result.patient) {
        setRegistrationState({
          status: "success",
          message: result.message,
          patient: result.patient,
        });
        savePatientFlow({
          registrationPatient: result.patient,
          newPayment: result,
        });
        window.setTimeout(() => {
          navigate("/patient/signin", { replace: true });
        }, 1600);
      }
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to verify payment.",
        payment: null,
      });
    }
  }

  return (
    <SectionCard
      title="Patient Sign Up"
      subtitle="Enter your details once, complete payment, then wait for the verification email before signing in."
    >
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
          <input className="form-field__input" type="password" value={registrationForm.password} onChange={(event) => updateRegistrationField("password", event.target.value)} />
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
        <button className="button button--primary" type="submit">
          Register
        </button>
      </form>

      {paymentConfig ? (
        <div className="fee-box">
          <strong>{paymentConfig.new_patient_label}</strong>
          <span>
            {paymentConfig.currency} {paymentConfig.new_patient_fee.toLocaleString()}
          </span>
        </div>
      ) : null}

      <div className={`lookup-result lookup-result--${paymentState.status}`}>
        <p className="lookup-result__message">{paymentState.message}</p>
        <div className="payment-actions">
          {paymentState.payment?.reference ? (
            <button className="button button--secondary" type="button" onClick={() => handleVerifyPayment(paymentState.payment.reference)}>
              Verify Payment
            </button>
          ) : null}
          {paymentState.payment?.authorization_url ? (
            <a className="button button--secondary" href={paymentState.payment.authorization_url} target="_blank" rel="noreferrer">
              Open Paystack Checkout
            </a>
          ) : null}
        </div>
        {paymentState.payment ? (
          <dl className="lookup-result__details">
            <div><dt>Reference</dt><dd>{paymentState.payment.reference}</dd></div>
            <div><dt>Amount</dt><dd>{paymentState.payment.currency} {paymentState.payment.amount?.toLocaleString()}</dd></div>
            <div><dt>Status</dt><dd>{paymentState.payment.paystack_status || "initialized"}</dd></div>
          </dl>
        ) : null}
      </div>

      <div className={`lookup-result lookup-result--${registrationState.status}`}>
        <p className="lookup-result__message">{registrationState.message}</p>
        {registrationState.patient ? (
          <>
            <dl className="lookup-result__details">
              <div><dt>Hospital Number</dt><dd>{registrationState.patient.hospital_number}</dd></div>
              <div><dt>Name</dt><dd>{registrationState.patient.name}</dd></div>
              <div><dt>Email</dt><dd>{registrationState.patient.email || "N/A"}</dd></div>
              <div><dt>Allergies</dt><dd>{registrationState.patient.allergy || "None recorded"}</dd></div>
              <div><dt>Medical Conditions</dt><dd>{registrationState.patient.medical_conditions || "None recorded"}</dd></div>
            </dl>
            <p className="patient-auth-link">
              After clicking the verification email, <Link to="/patient/signin">sign in here</Link>.
            </p>
          </>
        ) : null}
      </div>
    </SectionCard>
  );
}
