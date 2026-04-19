import { useEffect, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import StatusPill from "../components/StatusPill.jsx";
import { fetchAdminSummary } from "../api/admin.js";
import { clearAuthToken, fetchDeliveryStatus, requestOtp, restoreSession, verifyOtp } from "../api/auth.js";
import "../styles/admin.css";
import "../styles/forms.css";

export default function AdminDashboardPage() {
  const [adminId, setAdminId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpState, setOtpState] = useState({
    status: "idle",
    message: "Request an admin OTP code.",
    debugCode: "",
  });
  const [authState, setAuthState] = useState({
    status: "idle",
    message: "Sign in with an authorized admin ID.",
    session: null,
  });
  const [summaryState, setSummaryState] = useState({
    status: "idle",
    message: "Admin summary will appear after sign-in.",
    summary: null,
  });
  const [deliveryStatus, setDeliveryStatus] = useState(null);

  async function loadSummary() {
    setSummaryState({
      status: "loading",
      message: "Loading admin summary...",
      summary: null,
    });
    try {
      const summary = await fetchAdminSummary();
      setSummaryState({
        status: "success",
        message: "Admin summary loaded.",
        summary,
      });
    } catch (error) {
      setSummaryState({
        status: "error",
        message: error.message || "Unable to load admin summary.",
        summary: null,
      });
    }
  }

  useEffect(() => {
    async function loadDeliveryStatus() {
      try {
        const result = await fetchDeliveryStatus();
        setDeliveryStatus(result);
      } catch (error) {
        setDeliveryStatus(null);
      }
    }

    loadDeliveryStatus();
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "admin") {
          return;
        }
        setAuthState({
          status: "success",
          message: session.message,
          session,
        });
        loadSummary();
      } catch {}
    }

    bootstrap();
  }, []);

  async function handleRequestCode(event) {
    event.preventDefault();
    try {
      const result = await requestOtp({
        role: "admin",
        user_id: Number(adminId),
      });
      setOtpState({
        status: "success",
        message: `${result.message} Delivery target: ${result.delivery_target}`,
        debugCode: result.debug_code || "",
      });
    } catch (error) {
      setOtpState({
        status: "error",
        message: error.message || "Unable to sign in.",
        debugCode: "",
      });
    }
  }

  async function handleVerifyCode(event) {
    event.preventDefault();
    try {
      const session = await verifyOtp({
        role: "admin",
        user_id: Number(adminId),
        otp_code: otpCode,
      });
      setAuthState({
        status: "success",
        message: session.message,
        session,
      });
      await loadSummary();
    } catch (error) {
      setAuthState({
        status: "error",
        message: error.message || "Unable to verify code.",
        session: null,
      });
    }
  }

  function handleSignOut() {
    clearAuthToken();
    setAuthState({
      status: "idle",
      message: "Signed out.",
      session: null,
    });
    setSummaryState({
      status: "idle",
      message: "Admin summary will appear after sign-in.",
      summary: null,
    });
  }

  return (
    <div className="admin-grid">
      <SectionCard title="Admin Sign-In" subtitle="Protected admin session for web dashboard access.">
        {deliveryStatus?.telegram ? (
          <div className="delivery-status-list">
            <article className={`delivery-status delivery-status--${deliveryStatus.telegram.ready ? "ready" : "pending"}`}>
              <div>
                <h3>{deliveryStatus.telegram.label}</h3>
                <p>{deliveryStatus.telegram.message}</p>
              </div>
              <StatusPill label={deliveryStatus.telegram.ready ? "Ready" : "Setup needed"} tone={deliveryStatus.telegram.ready ? "success" : "warning"} />
            </article>
            {deliveryStatus.dev_debug_code_visible ? (
              <p className="doctor-state__message">
                Dev OTP visibility is on, so the code will also appear here while delivery is being tested.
              </p>
            ) : null}
          </div>
        ) : null}

        <form className="form-panel form-panel--inline" onSubmit={handleRequestCode}>
          <label className="form-field form-field--grow">
            <span className="form-field__label">Admin ID</span>
            <input
              className="form-field__input"
              type="number"
              min="1"
              value={adminId}
              onChange={(event) => setAdminId(event.target.value)}
            />
          </label>
          <button className="button button--primary" type="submit">
            Request Code
          </button>
          {authState.session ? (
            <button className="button button--secondary" type="button" onClick={handleSignOut}>
              Sign Out
            </button>
          ) : null}
        </form>
        <form className="form-panel form-panel--inline" onSubmit={handleVerifyCode}>
          <label className="form-field form-field--grow">
            <span className="form-field__label">OTP Code</span>
            <input
              className="form-field__input"
              type="text"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value)}
            />
          </label>
          <button className="button button--primary" type="submit">
            Verify Code
          </button>
        </form>
        <div className={`doctor-state doctor-state--${otpState.status}`}>
          <p className="doctor-state__message">{otpState.message}</p>
          {otpState.debugCode ? <p className="doctor-state__message">Dev OTP: {otpState.debugCode}</p> : null}
        </div>
        <div className={`doctor-state doctor-state--${authState.status}`}>
          <p className="doctor-state__message">{authState.message}</p>
        </div>
      </SectionCard>

      <SectionCard title="System Overview" subtitle="High-level metrics from the protected admin API.">
        <div className={`doctor-state doctor-state--${summaryState.status}`}>
          <p className="doctor-state__message">{summaryState.message}</p>
          {summaryState.summary ? (
            <div className="metric-grid">
              <article className="metric-card">
                <span className="metric-card__label">Registered Patients</span>
                <strong className="metric-card__value">{summaryState.summary.registered_patients}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-card__label">Verified Doctors</span>
                <strong className="metric-card__value">{summaryState.summary.verified_doctors}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-card__label">Active Consultations</span>
                <strong className="metric-card__value">{summaryState.summary.active_consultations}</strong>
              </article>
              <article className="metric-card">
                <span className="metric-card__label">Due Follow-ups</span>
                <strong className="metric-card__value">{summaryState.summary.due_followups}</strong>
              </article>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard title="Operational Queue" subtitle="Protected admin status markers for the current system.">
        <div className="admin-list">
          <article className="admin-list__item">
            <span>Admin session active</span>
            <StatusPill
              label={authState.session ? "Authenticated" : "Signed out"}
              tone={authState.session ? "success" : "warning"}
            />
          </article>
          <article className="admin-list__item">
            <span>Summary endpoint protection</span>
            <StatusPill label="Enabled" tone="success" />
          </article>
        </div>
      </SectionCard>

      <SectionCard title="Verified Doctors" subtitle="Database-backed verified doctors available to the live SynMed system.">
        <div className={`doctor-state doctor-state--${summaryState.status}`}>
          {summaryState.summary?.verified_doctor_records?.length ? (
            <div className="admin-list">
              {summaryState.summary.verified_doctor_records.map((doctor) => (
                <article className="admin-list__item" key={doctor.telegram_id}>
                  <div>
                    <strong>{doctor.name}</strong>
                    <p className="doctor-state__message">
                      {doctor.specialty} | Telegram ID: {doctor.telegram_id}
                    </p>
                  </div>
                  <StatusPill
                    label={doctor.status}
                    tone={
                      doctor.status === "available"
                        ? "success"
                        : doctor.status === "busy"
                        ? "danger"
                        : "warning"
                    }
                  />
                </article>
              ))}
            </div>
          ) : (
            <p className="doctor-state__message">No verified doctors found in the database.</p>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
