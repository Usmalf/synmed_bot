import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import BrandedLoader from "../components/BrandedLoader.jsx";
import SectionCard from "../components/SectionCard.jsx";
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
  });
  const [couponCode, setCouponCode] = useState("");

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
          setConsultationForm({ reference: paymentResult.payment.reference });
          savePatientFlow({
            consultationReference: paymentResult.payment.reference,
          });
          navigate(`/consultation?reference=${encodeURIComponent(paymentResult.payment.reference)}`, { replace: true });
          return;
        }

        if (flow.consultationReference) {
          try {
            const verification = await verifyPayment(flow.consultationReference);
            if (verification.verified) {
              const payment = {
                reference: verification.reference,
                verified_at: new Date().toISOString(),
                amount: verification.amount,
                currency: verification.currency,
                label: configResult?.returning_patient_label || "Consultation Fee",
                patient_type: "returning",
              };
              setPaymentState({
                status: "success",
                message: verification.message,
                payment,
                initiation: null,
              });
              setConsultationForm({ reference: verification.reference });
              savePatientFlow({
                consultationReference: verification.reference,
              });
              navigate(`/consultation?reference=${encodeURIComponent(verification.reference)}`, { replace: true });
              return;
            }
            savePatientFlow({
              consultationReference: "",
            });
          } catch {}
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
        callback_path: "/patient/consultation",
        coupon_code: couponCode.trim(),
      });
      setPaymentState({
        status: "success",
        message: "Redirecting securely to Paystack checkout...",
        payment: null,
        initiation: result,
      });
      setConsultationForm({ reference: result.reference || "" });
      savePatientFlow({
        consultationReference: result.reference || "",
      });
      if (result.authorization_url) {
        window.location.assign(result.authorization_url);
        return;
      }
      if (result.reference) {
        const verification = await verifyPayment(result.reference);
        if (verification.verified) {
          const payment = {
            reference: verification.reference,
            verified_at: new Date().toISOString(),
            amount: verification.amount,
            currency: verification.currency,
            label: paymentConfig?.returning_patient_label || "Consultation Fee",
            patient_type: "returning",
          };
          setPaymentState({
            status: "success",
            message: verification.message,
            payment,
            initiation: null,
          });
          savePatientFlow({
            consultationReference: verification.reference,
          });
          navigate(`/consultation?reference=${encodeURIComponent(verification.reference)}`, { replace: true });
        }
      }
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
        setConsultationForm({ reference: result.reference });
        savePatientFlow({
          consultationReference: result.reference,
        });
        navigate(`/consultation?reference=${encodeURIComponent(result.reference)}`, { replace: true });
      } else {
        setPaymentState({
          status: "error",
          message: result.message,
          payment: null,
          initiation: paymentState.initiation,
        });
        savePatientFlow({
          consultationReference: "",
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

  const hasValidPayment = Boolean(paymentState.payment?.reference);

  return (
    <div className="patient-account-grid patient-consultation-access">
      <SectionCard
        title="Consultation Access"
      >
        <div className="patient-consultation-access__topbar">
          <button className="button button--secondary" type="button" onClick={() => navigate("/patient")}>
            {"\u2190"} Back to dashboard
          </button>
        </div>
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

        {!hasValidPayment && paymentConfig?.consultation_coupons_available ? (
          <label className="form-field patient-consultation-access__coupon">
            <span className="form-field__label">Coupon Code</span>
            <input
              className="form-field__input"
              type="text"
              placeholder="Optional"
              value={couponCode}
              onChange={(event) => setCouponCode(event.target.value.toUpperCase())}
            />
          </label>
        ) : null}

        <div className={`lookup-result lookup-result--${paymentState.status}`}>
          {paymentState.status === "loading" ? (
            <BrandedLoader compact label={paymentState.message} />
          ) : (
            <p className="lookup-result__message">{paymentState.message}</p>
          )}
          {paymentState.payment ? (
            <dl className="lookup-result__details">
              <div><dt>Reference</dt><dd>{paymentState.payment.reference}</dd></div>
              <div><dt>Verified At</dt><dd>{paymentState.payment.verified_at || "Recently verified"}</dd></div>
            </dl>
          ) : null}
          <div className="payment-actions">
            {!hasValidPayment ? (
              <button className="button button--primary" type="button" onClick={handleStartPayment}>
                Pay for Consultation
              </button>
            ) : (
              <button
                className="button button--primary"
                type="button"
                onClick={() =>
                  navigate(`/consultation?reference=${encodeURIComponent(consultationForm.reference.trim())}`)
                }
              >
                Continue to Consultation
              </button>
            )}
            {paymentState.initiation?.reference && !hasValidPayment ? (
              <button className="button button--secondary" type="button" onClick={handleVerifyPayment}>
                I Have Paid
              </button>
            ) : null}
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
