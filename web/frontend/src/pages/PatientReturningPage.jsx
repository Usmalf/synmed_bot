import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { lookupPatient } from "../api/patients.js";
import { fetchPaymentConfig, initializePayment, verifyPayment } from "../api/payments.js";
import { loadPatientFlow, savePatientFlow } from "../lib/patientFlowStorage.js";
import "../styles/forms.css";
import "../styles/patient.css";

export default function PatientReturningPage() {
  const navigate = useNavigate();
  const flow = loadPatientFlow();
  const [lookupIdentifier, setLookupIdentifier] = useState(flow.lookupIdentifier || "");
  const [returningEmail, setReturningEmail] = useState(flow.returningEmail || "");
  const [paymentConfig, setPaymentConfig] = useState(null);
  const [lookupState, setLookupState] = useState({
    status: flow.lookupPatient ? "success" : "idle",
    message: flow.lookupPatient
      ? "Saved returning patient record restored."
      : "Enter a hospital number or phone number to find an existing record.",
    patient: flow.lookupPatient,
  });
  const [returningPaymentState, setReturningPaymentState] = useState({
    status: flow.returningPayment ? "success" : "idle",
    message: flow.returningPayment
      ? "Saved payment state restored."
      : "Returning patient payment has not started yet.",
    payment: flow.returningPayment,
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

  async function handleLookupSubmit(event) {
    event.preventDefault();
    setLookupState({
      status: "loading",
      message: "Checking patient record...",
      patient: null,
    });

    try {
      const result = await lookupPatient(lookupIdentifier.trim());
      setLookupState({
        status: result.found ? "success" : "empty",
        message: result.message,
        patient: result.patient,
      });
      setReturningPaymentState({
        status: "idle",
        message: "Returning patient payment has not started yet.",
        payment: null,
      });
      savePatientFlow({
        lookupIdentifier: lookupIdentifier.trim(),
        returningEmail: returningEmail.trim(),
        lookupPatient: result.patient,
        returningPayment: null,
        consultationReference: "",
      });
    } catch {
      setLookupState({
        status: "error",
        message: "Unable to reach the patient lookup service right now.",
        patient: null,
      });
    }
  }

  async function handleReturningPaymentStart() {
    if (!lookupState.patient || !returningEmail.trim()) {
      setReturningPaymentState({
        status: "error",
        message: "Look up a patient first and enter an email address for payment.",
        payment: null,
      });
      return;
    }

    setReturningPaymentState({
      status: "loading",
      message: "Initializing payment...",
      payment: null,
    });

    try {
      const result = await initializePayment({
        email: returningEmail.trim(),
        patient_type: "returning",
        patient_id: lookupState.patient.hospital_number,
      });
      setReturningPaymentState({
        status: "success",
        message: result.message,
        payment: result,
      });
      savePatientFlow({
        lookupIdentifier: lookupIdentifier.trim(),
        returningEmail: returningEmail.trim(),
        lookupPatient: lookupState.patient,
        returningPayment: result,
        consultationReference: result.reference || "",
      });
    } catch (error) {
      setReturningPaymentState({
        status: "error",
        message: error.message || "Unable to initialize payment.",
        payment: null,
      });
    }
  }

  async function handleVerifyPayment(reference) {
    setReturningPaymentState({
      status: "loading",
      message: "Verifying payment...",
      payment: null,
    });

    try {
      const result = await verifyPayment(reference);
      setReturningPaymentState({
        status: result.verified ? "success" : "empty",
        message: result.message,
        payment: result,
      });
      savePatientFlow({
        lookupIdentifier: lookupIdentifier.trim(),
        returningEmail: returningEmail.trim(),
        lookupPatient: lookupState.patient,
        returningPayment: result,
        consultationReference: result.verified ? result.reference : "",
      });
      if (result.verified) {
        window.setTimeout(() => {
          navigate("/patient/consultation");
        }, 400);
      }
    } catch (error) {
      setReturningPaymentState({
        status: "error",
        message: error.message || "Unable to verify payment.",
        payment: null,
      });
    }
  }

  return (
    <SectionCard
      title="Returning Patient"
      subtitle="Look up an existing record and handle returning-patient payment in its own focused screen."
    >
      <form className="form-panel" onSubmit={handleLookupSubmit}>
        <label className="form-field">
          <span className="form-field__label">Hospital Number or Phone</span>
          <input
            className="form-field__input"
            type="text"
            placeholder="SM0001 or 080..."
            value={lookupIdentifier}
            onChange={(event) => setLookupIdentifier(event.target.value)}
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">Email Address</span>
          <input
            className="form-field__input"
            type="email"
            placeholder="name@example.com"
            value={returningEmail}
            onChange={(event) => setReturningEmail(event.target.value)}
          />
        </label>
        <button className="button button--primary" type="submit">
          Look Up Record
        </button>
      </form>

      {paymentConfig ? (
        <div className="fee-box">
          <strong>{paymentConfig.returning_patient_label}</strong>
          <span>
            {paymentConfig.currency} {paymentConfig.returning_patient_fee.toLocaleString()}
          </span>
        </div>
      ) : null}

      <div className={`lookup-result lookup-result--${lookupState.status}`}>
        <p className="lookup-result__message">{lookupState.message}</p>
        {lookupState.patient ? (
          <dl className="lookup-result__details">
            <div><dt>Hospital Number</dt><dd>{lookupState.patient.hospital_number}</dd></div>
            <div><dt>Name</dt><dd>{lookupState.patient.name}</dd></div>
            <div><dt>Age</dt><dd>{lookupState.patient.age}</dd></div>
            <div><dt>Gender</dt><dd>{lookupState.patient.gender}</dd></div>
            <div><dt>Phone</dt><dd>{lookupState.patient.phone}</dd></div>
            <div><dt>Address</dt><dd>{lookupState.patient.address || "N/A"}</dd></div>
            <div><dt>Allergy</dt><dd>{lookupState.patient.allergy || "None recorded"}</dd></div>
          </dl>
        ) : null}
      </div>

      <div className={`lookup-result lookup-result--${returningPaymentState.status}`}>
        <p className="lookup-result__message">{returningPaymentState.message}</p>
        <div className="payment-actions">
          <button className="button button--primary" type="button" onClick={handleReturningPaymentStart}>
            Start Returning Patient Payment
          </button>
          {returningPaymentState.payment?.reference ? (
            <button
              className="button button--secondary"
              type="button"
              onClick={() => handleVerifyPayment(returningPaymentState.payment.reference)}
            >
              Verify Payment
            </button>
          ) : null}
          {returningPaymentState.payment?.authorization_url ? (
            <a
              className="button button--secondary"
              href={returningPaymentState.payment.authorization_url}
              target="_blank"
              rel="noreferrer"
            >
              Open Paystack Checkout
            </a>
          ) : null}
        </div>
        {returningPaymentState.payment ? (
          <dl className="lookup-result__details">
            <div><dt>Reference</dt><dd>{returningPaymentState.payment.reference}</dd></div>
            <div>
              <dt>Amount</dt>
              <dd>
                {returningPaymentState.payment.currency}{" "}
                {returningPaymentState.payment.amount?.toLocaleString()}
              </dd>
            </div>
            <div><dt>Status</dt><dd>{returningPaymentState.payment.paystack_status || "initialized"}</dd></div>
          </dl>
        ) : null}
      </div>
    </SectionCard>
  );
}
