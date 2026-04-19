import { useEffect, useMemo, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import {
  bookFollowup,
  fetchPatientFollowups,
  initializeFollowupPayment,
  markFollowupPayLater,
  redeemFollowupPaymentCode,
  verifyFollowupPayment,
} from "../api/followups.js";
import { fetchCurrentPatient } from "../api/patients.js";
import { loadPatientFlow, savePatientFlow } from "../lib/patientFlowStorage.js";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

function createDefaultForm() {
  const now = new Date();
  const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  return {
    scheduled_date: tomorrow.toISOString().slice(0, 10),
    scheduled_time: "09:00",
    notes: "",
  };
}

export default function PatientAppointmentsPage() {
  const flow = loadPatientFlow();
  const [patientState, setPatientState] = useState({
    status: "loading",
    patient: null,
  });
  const [appointmentsState, setAppointmentsState] = useState({
    status: "loading",
    message: "Loading appointments...",
    appointments: [],
  });
  const [bookingForm, setBookingForm] = useState(createDefaultForm);
  const [bookingState, setBookingState] = useState({
    status: "idle",
    message: "Choose a date and time to book an appointment.",
    appointment: null,
  });
  const [selectedReference, setSelectedReference] = useState(flow.selectedAppointmentReference || "");
  const [paymentState, setPaymentState] = useState({
    status: "idle",
    message: "Choose an appointment to handle payment.",
    result: null,
  });
  const [paymentCode, setPaymentCode] = useState("");
  const [paymentEmail, setPaymentEmail] = useState("");

  async function refreshAppointments() {
    try {
      const result = await fetchPatientFollowups();
      setAppointmentsState({
        status: result.found ? "success" : "empty",
        message: result.message,
        appointments: result.appointments || [],
      });
      if (!selectedReference && result.appointments?.length) {
        const nextReference = result.appointments[0].short_reference;
        setSelectedReference(nextReference);
        savePatientFlow({ selectedAppointmentReference: nextReference });
      }
    } catch {
      setAppointmentsState({
        status: "error",
        message: "Unable to load appointments right now.",
        appointments: [],
      });
    }
  }

  useEffect(() => {
    let ignore = false;

    async function bootstrap() {
      try {
        const currentPatient = await fetchCurrentPatient();
        if (!ignore) {
          setPatientState({
            status: "success",
            patient: currentPatient.patient,
          });
          setPaymentEmail(currentPatient.patient?.email || "");
        }
      } catch {
        if (!ignore) {
          setPatientState({
            status: "error",
            patient: null,
          });
        }
      }

      if (!ignore) {
        refreshAppointments();
      }
    }

    bootstrap();
    return () => {
      ignore = true;
    };
  }, []);

  const selectedAppointment = useMemo(
    () =>
      appointmentsState.appointments.find(
        (item) => item.short_reference === selectedReference || item.appointment_id === selectedReference,
      ) || null,
    [appointmentsState.appointments, selectedReference],
  );

  async function handleBookAppointment(event) {
    event.preventDefault();
    setBookingState({
      status: "loading",
      message: "Creating appointment...",
      appointment: null,
    });

    try {
      const result = await bookFollowup(bookingForm);
      setBookingState({
        status: result.created ? "success" : "error",
        message: result.message,
        appointment: result.appointment,
      });
      if (result.created && result.appointment) {
        setSelectedReference(result.appointment.short_reference);
        savePatientFlow({ selectedAppointmentReference: result.appointment.short_reference });
        setBookingForm(createDefaultForm());
        await refreshAppointments();
      }
    } catch (error) {
      setBookingState({
        status: "error",
        message: error.message || "Unable to create appointment.",
        appointment: null,
      });
    }
  }

  async function handleInitializePayment() {
    if (!selectedAppointment) {
      setPaymentState({
        status: "error",
        message: "Choose an appointment first.",
        result: null,
      });
      return;
    }

    setPaymentState({
      status: "loading",
      message: "Initializing appointment payment...",
      result: null,
    });

    try {
      const result = await initializeFollowupPayment(selectedAppointment.short_reference, {
        email: paymentEmail.trim() || undefined,
      });
      setPaymentState({
        status: result.initialized ? "success" : "error",
        message: result.message,
        result,
      });
      await refreshAppointments();
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to initialize appointment payment.",
        result: null,
      });
    }
  }

  async function handleVerifyPayment() {
    if (!selectedAppointment || !paymentState.result?.reference) {
      return;
    }

    setPaymentState({
      status: "loading",
      message: "Verifying appointment payment...",
      result: paymentState.result,
    });

    try {
      const result = await verifyFollowupPayment(
        selectedAppointment.short_reference,
        paymentState.result.reference,
      );
      setPaymentState({
        status: result.verified ? "success" : "error",
        message: result.message,
        result,
      });
      await refreshAppointments();
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to verify appointment payment.",
        result: null,
      });
    }
  }

  async function handlePayLater() {
    if (!selectedAppointment) {
      return;
    }

    try {
      const result = await markFollowupPayLater(selectedAppointment.short_reference);
      setPaymentState({
        status: result.success ? "success" : "error",
        message: result.message,
        result,
      });
      await refreshAppointments();
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to mark appointment as pay later.",
        result: null,
      });
    }
  }

  async function handleRedeemPaymentCode() {
    if (!selectedAppointment || !paymentCode.trim()) {
      setPaymentState({
        status: "error",
        message: "Choose an appointment and enter a payment code first.",
        result: null,
      });
      return;
    }

    try {
      const result = await redeemFollowupPaymentCode(selectedAppointment.short_reference, paymentCode.trim());
      setPaymentState({
        status: result.success ? "success" : "error",
        message: result.message,
        result,
      });
      if (result.success) {
        setPaymentCode("");
      }
      await refreshAppointments();
    } catch (error) {
      setPaymentState({
        status: "error",
        message: error.message || "Unable to apply payment code.",
        result: null,
      });
    }
  }

  return (
    <div className="patient-account-grid">
      <SectionCard
        title="Book Appointment"
        subtitle="Patients can self-book on the web without going back into a crowded chat flow."
      >
        <form className="form-panel" onSubmit={handleBookAppointment}>
          <label className="form-field">
            <span className="form-field__label">Appointment Date</span>
            <input
              className="form-field__input"
              type="date"
              value={bookingForm.scheduled_date}
              onChange={(event) =>
                setBookingForm((current) => ({ ...current, scheduled_date: event.target.value }))
              }
            />
          </label>
          <label className="form-field">
            <span className="form-field__label">Time</span>
            <select
              className="form-field__input"
              value={bookingForm.scheduled_time}
              onChange={(event) =>
                setBookingForm((current) => ({ ...current, scheduled_time: event.target.value }))
              }
            >
              {["09:00", "10:30", "12:00", "14:00", "15:30", "17:00"].map((slot) => (
                <option key={slot} value={slot}>
                  {slot}
                </option>
              ))}
            </select>
          </label>
          <label className="form-field">
            <span className="form-field__label">Notes</span>
            <textarea
              className="form-field__input form-field__input--textarea"
              rows="3"
              placeholder="Result review, routine review, follow-up discussion..."
              value={bookingForm.notes}
              onChange={(event) =>
                setBookingForm((current) => ({ ...current, notes: event.target.value }))
              }
            />
          </label>
          <button className="button button--primary" type="submit">
            Book Appointment
          </button>
        </form>

        <div className={`lookup-result lookup-result--${bookingState.status}`}>
          <p className="lookup-result__message">{bookingState.message}</p>
          {bookingState.appointment ? (
            <dl className="lookup-result__details">
              <div>
                <dt>Reference</dt>
                <dd>{bookingState.appointment.short_reference}</dd>
              </div>
              <div>
                <dt>When</dt>
                <dd>{bookingState.appointment.scheduled_for}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{bookingState.appointment.payment_status}</dd>
              </div>
            </dl>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Appointment Payment"
        subtitle="Choose an appointment, then pay now, pay later, or apply a valid 24-hour payment code."
      >
        {patientState.patient ? (
          <label className="form-field">
            <span className="form-field__label">Patient Email</span>
            <input
              className="form-field__input"
              type="email"
              value={paymentEmail}
              onChange={(event) => setPaymentEmail(event.target.value)}
            />
          </label>
        ) : null}

        {appointmentsState.appointments.length ? (
          <div className="appointment-list">
            {appointmentsState.appointments.map((item) => (
              <button
                key={item.appointment_id}
                type="button"
                className={
                  selectedAppointment?.appointment_id === item.appointment_id
                    ? "appointment-card appointment-card--active"
                    : "appointment-card"
                }
                onClick={() => {
                  setSelectedReference(item.short_reference);
                  savePatientFlow({ selectedAppointmentReference: item.short_reference });
                }}
              >
                <div className="appointment-card__meta">
                  <span className="workspace-pill">{item.payment_status}</span>
                  <span>{item.short_reference}</span>
                </div>
                <h3>{item.scheduled_for}</h3>
                <p>{item.notes || "No extra notes recorded."}</p>
              </button>
            ))}
          </div>
        ) : (
          <div className={`lookup-result lookup-result--${appointmentsState.status}`}>
            <p className="lookup-result__message">{appointmentsState.message}</p>
          </div>
        )}

        <div className="patient-action-links">
          <button className="button button--primary" type="button" onClick={handleInitializePayment}>
            Pay Now
          </button>
          <button className="button button--secondary" type="button" onClick={handlePayLater}>
            Pay Later
          </button>
        </div>

        <div className="payment-code-panel">
          <label className="form-field form-field--grow">
            <span className="form-field__label">I Have Paid Before</span>
            <input
              className="form-field__input"
              type="text"
              placeholder="SMP-..."
              value={paymentCode}
              onChange={(event) => setPaymentCode(event.target.value)}
            />
          </label>
          <button className="button button--secondary" type="button" onClick={handleRedeemPaymentCode}>
            Apply Payment Code
          </button>
        </div>

        <div className={`lookup-result lookup-result--${paymentState.status}`}>
          <p className="lookup-result__message">{paymentState.message}</p>
          {paymentState.result?.reference ? (
            <div className="payment-actions">
              {paymentState.result.authorization_url ? (
                <a
                  className="button button--secondary"
                  href={paymentState.result.authorization_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Paystack Checkout
                </a>
              ) : null}
              <button className="button button--primary" type="button" onClick={handleVerifyPayment}>
                Verify Payment
              </button>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
