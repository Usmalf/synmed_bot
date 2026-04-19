import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { requestConsultation } from "../api/consultations.js";
import { fetchCurrentPatient } from "../api/patients.js";
import {
  fetchCurrentPaymentStatus,
  fetchPaymentConfig,
  initializePayment,
  verifyPayment,
} from "../api/payments.js";
import { loadPatientFlow, savePatientFlow } from "../lib/patientFlowStorage.js";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

export default function PatientConsultationRequestPage() {
  const navigate = useNavigate();
  const flow = loadPatientFlow();
  const [patientState, setPatientState] = useState({
    status: "loading",
    patient: null,
  });
  const [paymentConfig, setPaymentConfig] = useState(null);
  const [paymentState, setPaymentState] = useState({
    status: "loading",
    message: "Checking active consultation payment...",
    payment: null,
    initiation: null,
  });
  const [consultationForm, setConsultationForm] = useState({
    reference: flow.consultationReference || "",
    symptoms: "",
  });
  const [consultationState, setConsultationState] = useState({
    status: "idle",
    message: "Use your valid consultation payment and submit symptoms to request a consultation.",
    result: null,
  });

  useEffect(() => {
    let ignore = false;

    async function bootstrap() {
      try {
        const [patientResult, configResult, paymentResult] = await Promise.all([
          fetchCurrentPatient(),
          fetchPaymentConfig(),
          fetchCurrentPaymentStatus(),
        ]);

        if (ignore) {
          return;
        }

        setPatientState({
          status: "success",
          patient: patientResult.patient,
        });
        setPaymentConfig(configResult);
        setPaymentState({
          status: paymentResult.active ? "success" : "idle",
          message: paymentResult.message,
          payment: paymentResult.payment,
          initiation: null,
        });
        if (paymentResult.payment?.reference) {
          setConsultationForm((current) => ({
            ...current,
            reference: paymentResult.payment.reference,
          }));
          savePatientFlow({
            consultationReference: paymentResult.payment.reference,
          });
        }
      } catch (error) {
        if (!ignore) {
          setPatientState({
            status: "error",
            patient: null,
          });
          setPaymentState({
            status: "error",
            message: error.message || "Unable to load consultation setup right now.",
            payment: null,
            initiation: null,
          });
        }
      }
    }

    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleStartPayment() {
    if (!patientState.patient?.email) {
      setPaymentState({
        status: "error",
        message: "Please update your account email first before starting consultation payment.",
        payment: null,
        initiation: null,
      });
      return;
    }

    setPaymentState({
      status: "loading",
      message: "Initializing consultation payment...",
      payment: null,
      initiation: null,
    });

    try {
      const result = await initializePayment({
        email: patientState.patient.email,
        patient_type: "returning",
        patient_id: patientState.patient.hospital_number,
      });
      setPaymentState({
        status: "success",
        message: result.message,
        payment: null,
        initiation: result,
      });
      setConsultationForm((current) => ({
        ...current,
        reference: result.reference || current.reference,
      }));
      savePatientFlow({
        consultationReference: result.reference || "",
      });
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to initialize consultation payment.",
        payment: null,
        initiation: null,
      });
    }
  }

  async function handleVerifyPayment() {
    const reference = paymentState.initiation?.reference || consultationForm.reference.trim();
    if (!reference) {
      return;
    }

    setPaymentState((current) => ({
      ...current,
      status: "loading",
      message: "Verifying consultation payment...",
    }));

    try {
      const result = await verifyPayment(reference);
      if (result.verified) {
        const payment = {
          reference: result.reference,
          verified_at: new Date().toISOString(),
          amount: result.amount,
          currency: result.currency,
          label: paymentConfig?.returning_patient_label || "Consultation Fee",
          patient_type: "returning",
        };
        setPaymentState({
          status: "success",
          message: result.message,
          payment,
          initiation: null,
        });
        setConsultationForm((current) => ({
          ...current,
          reference: result.reference,
        }));
        savePatientFlow({
          consultationReference: result.reference,
        });
      } else {
        setPaymentState({
          status: "error",
          message: result.message,
          payment: null,
          initiation: paymentState.initiation,
        });
      }
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to verify consultation payment.",
        payment: null,
        initiation: paymentState.initiation,
      });
    }
  }

  async function handleConsultationSubmit(event) {
    event.preventDefault();
    setConsultationState({
      status: "loading",
      message: "Submitting consultation request...",
      result: null,
    });

    try {
      const result = await requestConsultation({
        reference: consultationForm.reference.trim(),
        symptoms: consultationForm.symptoms,
      });
      setConsultationState({
        status: result.submitted ? "success" : "error",
        message: result.message,
        result,
      });
      if (consultationForm.reference.trim()) {
        savePatientFlow({
          consultationReference: consultationForm.reference.trim(),
        });
      }
      if (result.submitted && consultationForm.reference.trim()) {
        window.setTimeout(() => {
          navigate(`/consultation?reference=${encodeURIComponent(consultationForm.reference.trim())}`);
        }, 900);
      }
    } catch (error) {
      setConsultationState({
        status: "error",
        message: error.message || "Unable to submit consultation request.",
        result: null,
      });
    }
  }

  const hasValidPayment = Boolean(paymentState.payment?.reference);

  return (
    <div className="patient-account-grid">
      <SectionCard
        title="Consultation Access"
        subtitle="If your last consultation payment is still active within 24 hours, SynMed keeps it. If not, pay here and continue straight into consultation."
      >
        {paymentConfig ? (
          <div className="fee-box">
            <strong>{paymentConfig.returning_patient_label}</strong>
            <span>
              {paymentConfig.currency} {paymentConfig.returning_patient_fee.toLocaleString()}
            </span>
          </div>
        ) : null}

        {patientState.patient ? (
          <dl className="patient-profile-grid">
            <div>
              <dt>Patient</dt>
              <dd>{patientState.patient.name}</dd>
            </div>
            <div>
              <dt>Hospital Number</dt>
              <dd>{patientState.patient.hospital_number}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{patientState.patient.email || "No email recorded"}</dd>
            </div>
          </dl>
        ) : null}

        <div className={`lookup-result lookup-result--${paymentState.status}`}>
          <p className="lookup-result__message">{paymentState.message}</p>
          {paymentState.payment ? (
            <dl className="lookup-result__details">
              <div><dt>Reference</dt><dd>{paymentState.payment.reference}</dd></div>
              <div><dt>Verified At</dt><dd>{paymentState.payment.verified_at || "Recently verified"}</dd></div>
              <div><dt>Payment Code</dt><dd>{paymentState.payment.payment_token || "Available on appointment flow"}</dd></div>
            </dl>
          ) : null}
          <div className="payment-actions">
            {!hasValidPayment ? (
              <button className="button button--primary" type="button" onClick={handleStartPayment}>
                Pay for Consultation
              </button>
            ) : null}
            {paymentState.initiation?.authorization_url ? (
              <a
                className="button button--secondary"
                href={paymentState.initiation.authorization_url}
                target="_blank"
                rel="noreferrer"
              >
                Open Paystack Checkout
              </a>
            ) : null}
            {paymentState.initiation?.reference ? (
              <button className="button button--secondary" type="button" onClick={handleVerifyPayment}>
                Verify Payment
              </button>
            ) : null}
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Consultation Request"
        subtitle="Once payment is active, enter symptoms and continue into the live consultation room."
      >
        <form className="form-panel" onSubmit={handleConsultationSubmit}>
          <label className="form-field">
            <span className="form-field__label">Verified Payment Reference</span>
            <input
              className="form-field__input"
              type="text"
              value={consultationForm.reference}
              readOnly
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">Medical History / Symptoms</span>
            <textarea
              className="form-field__input form-field__input--textarea"
              rows="5"
              value={consultationForm.symptoms}
              onChange={(event) => setConsultationForm((current) => ({ ...current, symptoms: event.target.value }))}
            />
          </label>
          <button className="button button--primary" type="submit" disabled={!hasValidPayment}>
            Start Consultation
          </button>
        </form>

        <div className={`lookup-result lookup-result--${consultationState.status}`}>
          <p className="lookup-result__message">{consultationState.message}</p>
          {consultationState.result?.submitted && consultationForm.reference.trim() ? (
            <div className="payment-actions">
              <button
                className="button button--primary"
                type="button"
                onClick={() =>
                  navigate(`/consultation?reference=${encodeURIComponent(consultationForm.reference.trim())}`)
                }
              >
                Open Consultation Room
              </button>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
