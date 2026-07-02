import { useEffect, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import {
  createMedicalReportRequest,
  fetchCurrentPatient,
  fetchMedicalReportRequests,
  initializeMedicalReportPayment,
  verifyMedicalReportPayment,
} from "../api/patients.js";
import "../styles/forms.css";
import "../styles/patient-portal.css";

const PAYMENT_STATE_KEY = "synmed-medical-report-payment";

export default function PatientMedicalReportRequestPage() {
  const [email, setEmail] = useState("");
  const [requestNote, setRequestNote] = useState("");
  const [requestState, setRequestState] = useState({
    status: "loading",
    message: "Loading medical report requests...",
    requests: [],
    feeAmount: 5000,
  });
  const [paymentState, setPaymentState] = useState({
    status: "idle",
    message: "",
  });

  async function loadRequests() {
    try {
      const [patientResult, requestsResult] = await Promise.all([
        fetchCurrentPatient(),
        fetchMedicalReportRequests(),
      ]);
      setEmail(patientResult.patient?.email || "");
      const requests = requestsResult.requests || [];
      setRequestState({
        status: "success",
        message: "",
        requests,
        feeAmount: requestsResult.fee_amount || 5000,
      });
    } catch (error) {
      setRequestState({
        status: "error",
        message: error.message || "Unable to load medical report requests.",
        requests: [],
        feeAmount: 5000,
      });
    }
  }

  useEffect(() => {
    loadRequests();
  }, []);

  useEffect(() => {
    async function resumeVerification() {
      const saved = window.localStorage.getItem(PAYMENT_STATE_KEY);
      if (!saved) {
        return;
      }

      try {
        const parsed = JSON.parse(saved);
        if (!parsed?.requestId || !parsed?.paymentReference) {
          return;
        }

        setPaymentState({
          status: "loading",
          message: "Checking your medical report payment...",
        });
        const result = await verifyMedicalReportPayment(parsed.requestId, parsed.paymentReference);
        if (result.verified) {
          window.localStorage.removeItem(PAYMENT_STATE_KEY);
          setPaymentState({
            status: "idle",
            message: "",
          });
        } else {
          setPaymentState({
            status: "warning",
            message: result.message,
          });
        }
        await loadRequests();
      } catch (error) {
        setPaymentState({
          status: "warning",
          message:
            error.message ||
            "Payment could not be confirmed yet. You can verify again from the request row below.",
        });
      }
    }

    resumeVerification();
  }, []);

  async function handleCreateRequest(event) {
    event.preventDefault();
    const pendingPaidRequest = requestState.requests.find(
      (item) =>
        item.payment_status === "paid" &&
        item.status !== "fulfilled" &&
        !item.fulfilled_letter_id,
    );
    if (pendingPaidRequest) {
      setRequestState((current) => ({
        ...current,
        status: "warning",
        message:
          "You already have a paid medical report request waiting for your doctor. Please wait until it is completed before making another payment.",
      }));
      return;
    }

    setRequestState((current) => ({
      ...current,
      status: "loading",
      message: "Creating medical report request...",
    }));

    try {
      const result = await createMedicalReportRequest({
        request_note: requestNote,
        delivery_email: email,
      });
      if (!result.created) {
        setRequestState((current) => ({
          ...current,
          status: "warning",
          message: result.message,
          requests: result.request ? [result.request, ...current.requests] : current.requests,
          feeAmount: result.fee_amount || current.feeAmount,
        }));
        return;
      }

      setRequestNote("");
      setRequestState((current) => ({
        status: "success",
        message: "",
        requests: result.request ? [result.request, ...current.requests] : current.requests,
        feeAmount: result.fee_amount || current.feeAmount,
      }));
      if (result.request?.request_id) {
        await handlePayNow(result.request.request_id, email);
      }
    } catch (error) {
      setRequestState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to create medical report request.",
      }));
    }
  }

  async function handlePayNow(requestId, paymentEmail = email) {
    setPaymentState({
      status: "loading",
      message: "Initializing medical report payment...",
    });

    try {
      const result = await initializeMedicalReportPayment(requestId, {
        email: paymentEmail,
        callback_path: "/patient/medical-report-request",
      });
      window.localStorage.setItem(
        PAYMENT_STATE_KEY,
        JSON.stringify({
          requestId,
          paymentReference: result.reference,
        }),
      );
      setPaymentState({
        status: "success",
        message: "Redirecting securely to payment...",
      });
      window.location.href = result.authorization_url;
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to initialize payment right now.",
      });
    }
  }

  async function handleVerifyPayment(requestId, paymentReference) {
    if (!paymentReference) {
      setPaymentState({
        status: "warning",
        message: "No payment reference is available for this request yet.",
      });
      return;
    }

    setPaymentState({
      status: "loading",
      message: "Verifying medical report payment...",
    });

    try {
      const result = await verifyMedicalReportPayment(requestId, paymentReference);
      if (result.verified) {
        window.localStorage.removeItem(PAYMENT_STATE_KEY);
        setPaymentState({
          status: "idle",
          message: "",
        });
      } else {
        setPaymentState({
          status: "warning",
          message: result.message,
        });
      }
      await loadRequests();
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to verify payment right now.",
      });
    }
  }

  const pendingPaidRequest = requestState.requests.find(
    (item) =>
      item.payment_status === "paid" &&
      item.status !== "fulfilled" &&
      !item.fulfilled_letter_id,
  );

  const shouldShowRequestStatus =
    ["loading", "error"].includes(requestState.status) ||
    (requestState.status === "warning" && !pendingPaidRequest);
  const shouldShowPaymentStatus =
    Boolean(paymentState.message) && ["loading", "error", "warning"].includes(paymentState.status);

  return (
    <div className="patient-account-grid patient-medical-report-access">
      <SectionCard
        title="Request Medical Report"
        subtitle={`Medical reports are prepared after payment of NGN ${requestState.feeAmount.toLocaleString()} and assigned to the last doctor when available.`}
      >
      {shouldShowRequestStatus ? (
        <div className={`lookup-result lookup-result--${requestState.status}`}>
          <p className="lookup-result__message">{requestState.message}</p>
        </div>
      ) : null}

      <form className="form-panel" onSubmit={handleCreateRequest}>
        <label className="form-field">
          <span className="form-field__label">Report Delivery Email</span>
          <input
            className="form-field__input"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="your@email.com"
            required
          />
        </label>
        <label className="form-field">
          <span className="form-field__label">Note for the Doctor or Admin</span>
          <textarea
            className="form-field__input form-field__input--textarea"
            rows="4"
            value={requestNote}
            onChange={(event) => setRequestNote(event.target.value)}
            placeholder="Mention what the report is for, for example embassy use, school, employer, insurance, or personal copy."
          />
        </label>
        <button className="button button--primary" disabled={Boolean(pendingPaidRequest) || requestState.status === "loading"} type="submit">
          {requestState.status === "loading" ? "Preparing Payment..." : "Request Medical Report"}
        </button>
      </form>

      {pendingPaidRequest ? (
        <div className="lookup-result lookup-result--warning">
          <p className="lookup-result__message">
            You already have a paid medical report request waiting for your doctor. You will receive it by email and in your Documents once completed.
          </p>
        </div>
      ) : null}

      {shouldShowPaymentStatus ? (
        <div className={`lookup-result lookup-result--${paymentState.status}`}>
          <p className="lookup-result__message">{paymentState.message}</p>
        </div>
      ) : null}
      </SectionCard>
    </div>
  );
}
