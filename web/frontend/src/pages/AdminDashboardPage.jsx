import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import SectionCard from "../components/SectionCard.jsx";
import StatusPill from "../components/StatusPill.jsx";
import {
  approveDoctorApplication,
  assignAdminMedicalReportRequest,
  createAdminHealthTip,
  fetchAdminConsultation,
  fetchAdminConsultations,
  fetchAdminDeliverySettings,
  fetchAdminMedicalReportRequests,
  fetchAdminPatients,
  deleteAdminHealthTip,
  fetchAdminHealthTips,
  fetchAdminSummary,
  reactivateDoctorAccount,
  rejectDoctorApplication,
  sendDoctorLicenseReminder,
  suspendDoctorAccount,
  testAdminDelivery,
  updateAdminHealthTip,
} from "../api/admin.js";
import {
  bootstrapAdminAccount,
  clearAuthToken,
  fetchDeliveryStatus,
  loginWebUser,
  requestOtp,
  restoreSession,
  verifyWebUserLogin,
  verifyOtp,
} from "../api/auth.js";
import "../styles/admin.css";
import "../styles/forms.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const metricCards = [
  { key: "registered_patients", label: "Registered Patients" },
  { key: "verified_doctors", label: "Verified Doctors" },
  { key: "pending_doctors", label: "Pending Doctors" },
  { key: "suspended_doctors", label: "Suspended Doctors" },
  { key: "active_consultations", label: "Active Consultations" },
  { key: "due_followups", label: "Due Follow-Ups" },
  { key: "medical_report_requests", label: "Medical Report Requests" },
];

function formatFileSize(bytes) {
  const size = Number(bytes || 0);
  if (!size) {
    return "";
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function AdminDashboardPage() {
  const [adminId, setAdminId] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpState, setOtpState] = useState({
    status: "idle",
    message: "Request an admin OTP code.",
    debugCode: "",
  });
  const [authState, setAuthState] = useState({
    status: "loading",
    message: "Checking admin session...",
    session: null,
  });
  const [adminCredentialForm, setAdminCredentialForm] = useState({
    identifier: "",
    password: "",
  });
  const [adminCredentialOtpCode, setAdminCredentialOtpCode] = useState("");
  const [adminCredentialOtpState, setAdminCredentialOtpState] = useState({
    status: "idle",
    message: "Sign in with your saved admin email and password.",
    debugCode: "",
    identifier: "",
  });
  const [summaryState, setSummaryState] = useState({
    status: "idle",
    message: "Admin summary will appear after sign-in.",
    summary: null,
  });
  const [deliveryStatus, setDeliveryStatus] = useState(null);
  const [tipsState, setTipsState] = useState({
    status: "idle",
    message: "Health tips will appear here after sign-in.",
    tips: [],
  });
  const [medicalReportState, setMedicalReportState] = useState({
    status: "idle",
    message: "Medical report requests will appear here after sign-in.",
    requests: [],
  });
  const [patientState, setPatientState] = useState({
    status: "idle",
    message: "Patient records will appear here after sign-in.",
    patients: [],
  });
  const [patientQuery, setPatientQuery] = useState("");
  const [consultationState, setConsultationState] = useState({
    status: "idle",
    message: "Consultations will appear here after sign-in.",
    consultations: [],
    selected: null,
  });
  const [deliveryAdminState, setDeliveryAdminState] = useState({
    status: "idle",
    message: "Delivery settings will appear here after sign-in.",
    settings: null,
  });
  const [deliveryTestForm, setDeliveryTestForm] = useState({
    channel: "email",
    target: "",
  });
  const [tipForm, setTipForm] = useState({
    id: null,
    eyebrow: "Health Tip",
    title: "",
    body: "",
    sort_order: 0,
    is_active: true,
  });
  const [adminSetupForm, setAdminSetupForm] = useState({
    adminId: "",
    email: "",
    displayName: "",
    password: "",
  });
  const [adminSetupState, setAdminSetupState] = useState({
    status: "idle",
    message: "Create the admin email/password once, then use the normal sign-in flow.",
  });
  const [doctorApplicationReasons, setDoctorApplicationReasons] = useState({});
  const [doctorAccountReasons, setDoctorAccountReasons] = useState({});

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

  async function loadHealthTips() {
    setTipsState((current) => ({
      ...current,
      status: "loading",
      message: "Loading health tips...",
    }));
    try {
      const result = await fetchAdminHealthTips();
      setTipsState({
        status: "success",
        message: "Health tips loaded.",
        tips: result.tips || [],
      });
    } catch (error) {
      setTipsState({
        status: "error",
        message: error.message || "Unable to load health tips.",
        tips: [],
      });
    }
  }

  async function loadMedicalReportRequests() {
    setMedicalReportState((current) => ({
      ...current,
      status: "loading",
      message: "Loading medical report requests...",
    }));
    try {
      const result = await fetchAdminMedicalReportRequests();
      setMedicalReportState({
        status: "success",
        message: result.message,
        requests: result.requests || [],
      });
    } catch (error) {
      setMedicalReportState({
        status: "error",
        message: error.message || "Unable to load medical report requests.",
        requests: [],
      });
    }
  }

  async function loadPatients(query = patientQuery) {
    setPatientState((current) => ({
      ...current,
      status: "loading",
      message: "Loading patient records...",
    }));
    try {
      const result = await fetchAdminPatients(query);
      setPatientState({
        status: "success",
        message: `${result.patients?.length || 0} patient record(s) loaded.`,
        patients: result.patients || [],
      });
    } catch (error) {
      setPatientState({
        status: "error",
        message: error.message || "Unable to load patient records.",
        patients: [],
      });
    }
  }

  async function loadConsultations() {
    setConsultationState((current) => ({
      ...current,
      status: "loading",
      message: "Loading consultations...",
    }));
    try {
      const result = await fetchAdminConsultations();
      setConsultationState({
        status: "success",
        message: `${result.consultations?.length || 0} consultation record(s) loaded.`,
        consultations: result.consultations || [],
        selected: null,
      });
    } catch (error) {
      setConsultationState({
        status: "error",
        message: error.message || "Unable to load consultations.",
        consultations: [],
        selected: null,
      });
    }
  }

  async function loadDeliverySettings() {
    setDeliveryAdminState((current) => ({
      ...current,
      status: "loading",
      message: "Checking OTP and email delivery...",
    }));
    try {
      const result = await fetchAdminDeliverySettings();
      setDeliveryAdminState({
        status: "success",
        message: "Delivery settings loaded.",
        settings: result,
      });
    } catch (error) {
      setDeliveryAdminState({
        status: "error",
        message: error.message || "Unable to load delivery settings.",
        settings: null,
      });
    }
  }

  useEffect(() => {
    async function loadDelivery() {
      try {
        const result = await fetchDeliveryStatus();
        setDeliveryStatus(result);
      } catch {
        setDeliveryStatus(null);
      }
    }

    loadDelivery();
  }, []);

  useEffect(() => {
    async function bootstrap() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "admin") {
          setAuthState({
            status: "unauthenticated",
            message: "Sign in to continue.",
            session: null,
          });
          return;
        }
        setAuthState({
          status: "success",
          message: session.message,
          session,
        });
        loadSummary();
        loadHealthTips();
        loadMedicalReportRequests();
        loadPatients("");
        loadConsultations();
        loadDeliverySettings();
      } catch {
        setAuthState({
          status: "unauthenticated",
          message: "Sign in to continue.",
          session: null,
        });
      }
    }

    bootstrap();
  }, []);

  if (authState.status === "loading") {
    return null;
  }

  if (authState.status === "unauthenticated" && !authState.session) {
    return <Navigate to="/signin" replace />;
  }

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
      await loadHealthTips();
      await loadMedicalReportRequests();
      await loadPatients("");
      await loadConsultations();
      await loadDeliverySettings();
    } catch (error) {
      setAuthState({
        status: "error",
        message: error.message || "Unable to verify code.",
        session: null,
      });
    }
  }

  async function handleAdminCredentialSignIn(event) {
    event.preventDefault();
    setAdminCredentialOtpState({
      status: "loading",
      message: "Checking admin credentials and sending OTP...",
      debugCode: "",
      identifier: adminCredentialForm.identifier,
    });

    try {
      const result = await loginWebUser(adminCredentialForm.identifier, adminCredentialForm.password);
      setAdminCredentialOtpState({
        status: "success",
        message: `${result.message} Delivery target: ${result.delivery_target || "telegram"}`,
        debugCode: result.debug_code || "",
        identifier: adminCredentialForm.identifier,
      });
    } catch (error) {
      setAdminCredentialOtpState({
        status: "error",
        message: error.message || "Unable to begin admin sign-in.",
        debugCode: "",
        identifier: adminCredentialForm.identifier,
      });
    }
  }

  async function handleAdminCredentialOtpVerify(event) {
    event.preventDefault();
    try {
      const session = await verifyWebUserLogin(
        adminCredentialOtpState.identifier || adminCredentialForm.identifier,
        adminCredentialOtpCode,
      );
      setAuthState({
        status: "success",
        message: session.message,
        session,
      });
      await loadSummary();
      await loadHealthTips();
      await loadMedicalReportRequests();
      await loadPatients("");
      await loadConsultations();
      await loadDeliverySettings();
    } catch (error) {
      setAuthState({
        status: "error",
        message: error.message || "Unable to verify admin OTP.",
        session: null,
      });
    }
  }

  async function handleAdminSetup(event) {
    event.preventDefault();
    setAdminSetupState({
      status: "loading",
      message: "Saving admin web credentials...",
    });

    try {
      const result = await bootstrapAdminAccount(
        adminSetupForm.adminId,
        adminSetupForm.email,
        adminSetupForm.displayName,
        adminSetupForm.password,
      );
      setAdminSetupState({
        status: "success",
        message: result.message,
      });
      setAdminId(String(adminSetupForm.adminId || ""));
      setAdminSetupForm((current) => ({
        ...current,
        password: "",
      }));
    } catch (error) {
      setAdminSetupState({
        status: "error",
        message: error.message || "Unable to save admin web credentials.",
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
    setTipsState({
      status: "idle",
      message: "Health tips will appear here after sign-in.",
      tips: [],
    });
    setMedicalReportState({
      status: "idle",
      message: "Medical report requests will appear here after sign-in.",
      requests: [],
    });
  }

  async function handleAssignLastDoctor(requestId, doctorId) {
    if (!doctorId) {
      setMedicalReportState((current) => ({
        ...current,
        status: "warning",
        message: "There is no previous doctor to assign for this request yet.",
      }));
      return;
    }

    try {
      await assignAdminMedicalReportRequest(requestId, doctorId);
      await loadMedicalReportRequests();
    } catch (error) {
      setMedicalReportState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to assign medical report request.",
      }));
    }
  }

  async function handleDoctorApplicationDecision(doctorId, action) {
    setSummaryState((current) => ({
      ...current,
      status: "loading",
      message: action === "approve" ? "Approving doctor application..." : "Rejecting doctor application...",
    }));

    try {
      if (action === "approve") {
        await approveDoctorApplication(doctorId);
      } else {
        await rejectDoctorApplication(doctorId, doctorApplicationReasons[doctorId] || "");
        setDoctorApplicationReasons((current) => {
          const next = { ...current };
          delete next[doctorId];
          return next;
        });
      }
      await loadSummary();
    } catch (error) {
      setSummaryState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to update doctor application.",
      }));
    }
  }

  async function handleDoctorAccountAction(doctorId, action) {
    setSummaryState((current) => ({
      ...current,
      status: "loading",
      message: action === "suspend" ? "Suspending doctor account..." : "Reactivating doctor account...",
    }));

    try {
      if (action === "suspend") {
        await suspendDoctorAccount(doctorId, doctorAccountReasons[doctorId] || "");
        setDoctorAccountReasons((current) => {
          const next = { ...current };
          delete next[doctorId];
          return next;
        });
      } else {
        await reactivateDoctorAccount(doctorId);
      }
      await loadSummary();
    } catch (error) {
      setSummaryState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to update doctor account.",
      }));
    }
  }

  async function handlePatientSearch(event) {
    event.preventDefault();
    await loadPatients(patientQuery);
  }

  async function handleConsultationInspect(consultationId) {
    setConsultationState((current) => ({
      ...current,
      status: "loading",
      message: "Loading consultation transcript...",
    }));
    try {
      const selected = await fetchAdminConsultation(consultationId);
      setConsultationState((current) => ({
        ...current,
        status: "success",
        message: "Consultation transcript loaded.",
        selected,
      }));
    } catch (error) {
      setConsultationState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to inspect consultation.",
      }));
    }
  }

  async function handleLicenseReminder(doctorId) {
    setSummaryState((current) => ({
      ...current,
      status: "loading",
      message: "Sending licence reminder...",
    }));
    try {
      const result = await sendDoctorLicenseReminder(doctorId);
      setSummaryState((current) => ({
        ...current,
        status: "success",
        message: result.message,
      }));
    } catch (error) {
      setSummaryState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to send licence reminder.",
      }));
    }
  }

  async function handleDeliveryTest(event) {
    event.preventDefault();
    setDeliveryAdminState((current) => ({
      ...current,
      status: "loading",
      message: "Sending delivery test...",
    }));
    try {
      const result = await testAdminDelivery(deliveryTestForm.channel, deliveryTestForm.target);
      setDeliveryAdminState((current) => ({
        ...current,
        status: "success",
        message: result.message,
      }));
    } catch (error) {
      setDeliveryAdminState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Delivery test failed.",
      }));
    }
  }

  async function handleTipSubmit(event) {
    event.preventDefault();
    try {
      if (tipForm.id) {
        await updateAdminHealthTip(tipForm.id, tipForm);
      } else {
        await createAdminHealthTip(tipForm);
      }
      setTipForm({
        id: null,
        eyebrow: "Health Tip",
        title: "",
        body: "",
        sort_order: 0,
        is_active: true,
      });
      await loadHealthTips();
    } catch (error) {
      setTipsState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to save health tip.",
      }));
    }
  }

  async function handleDeleteTip(tipId) {
    try {
      await deleteAdminHealthTip(tipId);
      if (tipForm.id === tipId) {
        setTipForm({
          id: null,
          eyebrow: "Health Tip",
          title: "",
          body: "",
          sort_order: 0,
          is_active: true,
        });
      }
      await loadHealthTips();
    } catch (error) {
      setTipsState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to delete health tip.",
      }));
    }
  }

  function handleEditTip(tip) {
    setTipForm({
      id: tip.id,
      eyebrow: tip.eyebrow,
      title: tip.title,
      body: tip.body,
      sort_order: tip.sort_order,
      is_active: tip.is_active,
    });
  }

  function resetTipForm() {
    setTipForm({
      id: null,
      eyebrow: "Health Tip",
      title: "",
      body: "",
      sort_order: 0,
      is_active: true,
    });
  }

  return (
    <div className="admin-dashboard">
      <section className="admin-dashboard__hero">
        <div className="admin-dashboard__intro">
          <span className="workspace-pill">Operations Console</span>
          <h1>Admin visibility for the whole SynMed care system.</h1>
          <p>
            This is the control surface for sign-in, high-level system health, and oversight of the verified
            doctor layer behind patient care.
          </p>
        </div>

        <aside className="admin-dashboard__session-card">
          <div>
            <span className="landing-kicker">Session Status</span>
            <h2>{authState.session ? "Admin authenticated" : "Admin sign-in required"}</h2>
            <p>{authState.message}</p>
          </div>
          <div className="admin-dashboard__session-actions">
            <StatusPill
              label={authState.session ? "Authenticated" : "Awaiting sign-in"}
              tone={authState.session ? "success" : "warning"}
            />
            {authState.session ? (
              <>
                <button className="button button--secondary" type="button" onClick={loadSummary}>
                  Refresh Summary
                </button>
                <button className="button button--secondary" type="button" onClick={handleSignOut}>
                  Sign Out
                </button>
              </>
            ) : null}
          </div>
        </aside>
      </section>

      <div className="admin-dashboard__layout">
        <div className="admin-dashboard__main">
          {!authState.session ? (
            <SectionCard
              title="Admin Access"
              subtitle="Create admin web credentials once, then sign in with protected OTP."
            >
              <form className="form-panel" onSubmit={handleAdminCredentialSignIn}>
                <label className="form-field">
                  <span className="form-field__label">Admin Email</span>
                  <input
                    className="form-field__input"
                    type="email"
                    value={adminCredentialForm.identifier}
                    onChange={(event) =>
                      setAdminCredentialForm((current) => ({ ...current, identifier: event.target.value }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Password</span>
                  <PasswordInput
                    value={adminCredentialForm.password}
                    onChange={(event) =>
                      setAdminCredentialForm((current) => ({ ...current, password: event.target.value }))
                    }
                  />
                </label>
                <div className="hero-card__actions">
                  <button className="button button--primary" type="submit">
                    Sign In
                  </button>
                </div>
              </form>

              <form className="form-panel form-panel--inline" onSubmit={handleAdminCredentialOtpVerify}>
                <label className="form-field form-field--grow">
                  <span className="form-field__label">OTP Code</span>
                  <input
                    className="form-field__input"
                    type="text"
                    value={adminCredentialOtpCode}
                    onChange={(event) => setAdminCredentialOtpCode(event.target.value)}
                  />
                </label>
                <button className="button button--primary" type="submit">
                  Verify Sign-In
                </button>
              </form>

              <div className={`admin-state admin-state--${adminCredentialOtpState.status}`}>
                <p className="doctor-state__message">{adminCredentialOtpState.message}</p>
                {adminCredentialOtpState.debugCode ? (
                  <p className="doctor-state__message">Dev OTP: {adminCredentialOtpState.debugCode}</p>
                ) : null}
              </div>

              <form className="form-panel" onSubmit={handleAdminSetup}>
                <label className="form-field">
                  <span className="form-field__label">Admin Telegram ID</span>
                  <input
                    className="form-field__input"
                    type="number"
                    min="1"
                    value={adminSetupForm.adminId}
                    onChange={(event) =>
                      setAdminSetupForm((current) => ({ ...current, adminId: event.target.value }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Admin Email</span>
                  <input
                    className="form-field__input"
                    type="email"
                    value={adminSetupForm.email}
                    onChange={(event) =>
                      setAdminSetupForm((current) => ({ ...current, email: event.target.value }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Display Name</span>
                  <input
                    className="form-field__input"
                    type="text"
                    value={adminSetupForm.displayName}
                    onChange={(event) =>
                      setAdminSetupForm((current) => ({ ...current, displayName: event.target.value }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span className="form-field__label">Password</span>
                  <PasswordInput
                    value={adminSetupForm.password}
                    onChange={(event) =>
                      setAdminSetupForm((current) => ({ ...current, password: event.target.value }))
                    }
                  />
                </label>
                <div className="hero-card__actions">
                  <button className="button button--primary" type="submit">
                    Save Admin Access
                  </button>
                </div>
              </form>

              <div className={`admin-state admin-state--${adminSetupState.status}`}>
                <p className="doctor-state__message">{adminSetupState.message}</p>
              </div>

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

              <div className="admin-state admin-state--idle">
                <p className="doctor-state__message">
                  After saving admin access once, you can sign in right here with your admin email and password,
                  then complete OTP on Telegram.
                </p>
              </div>

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

              <div className={`admin-state admin-state--${otpState.status}`}>
                <p className="doctor-state__message">{otpState.message}</p>
                {otpState.debugCode ? <p className="doctor-state__message">Dev OTP: {otpState.debugCode}</p> : null}
              </div>

              <div className={`admin-state admin-state--${authState.status}`}>
                <p className="doctor-state__message">{authState.message}</p>
              </div>
            </SectionCard>
          ) : null}

          <SectionCard
            id="admin-overview"
            title="System Overview"
            subtitle="High-level operational signals from the protected admin API."
          >
            <div className={`admin-state admin-state--${summaryState.status}`}>
              <p className="doctor-state__message">{summaryState.message}</p>
              {summaryState.summary ? (
                <div className="metric-grid">
                  {metricCards.map((item) => (
                    <article className="metric-card" key={item.key}>
                      <span className="metric-card__label">{item.label}</span>
                      <strong className="metric-card__value">{summaryState.summary[item.key]}</strong>
                    </article>
                  ))}
                </div>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard
            id="patients"
            title="Patient Management"
            subtitle="Search registered patients and review consultation activity."
          >
            <form className="form-panel form-panel--inline" onSubmit={handlePatientSearch}>
              <label className="form-field form-field--grow">
                <span className="form-field__label">Name, hospital number, email, or phone</span>
                <input
                  className="form-field__input"
                  type="search"
                  value={patientQuery}
                  onChange={(event) => setPatientQuery(event.target.value)}
                />
              </label>
              <button className="button button--primary" type="submit">Search</button>
              <button className="button button--secondary" type="button" onClick={() => loadPatients("")}>
                Show All
              </button>
            </form>
            <div className={`admin-state admin-state--${patientState.status}`}>
              <p className="doctor-state__message">{patientState.message}</p>
            </div>
            <div className="admin-list">
              {patientState.patients.map((patient) => (
                <article className="admin-list__item admin-list__item--doctor" key={patient.id}>
                  <div>
                    <strong>{patient.name || "Patient"}</strong>
                    <p className="doctor-state__message">
                      {patient.patient_id} | {patient.email || "No email"} | {patient.phone || "No phone"}
                    </p>
                    <p className="doctor-state__message">
                      Consultations: {patient.consultation_count || 0} | Email: {patient.email_verified_at ? "verified" : "not verified"}
                    </p>
                  </div>
                  <StatusPill
                    label={patient.email_verified_at ? "Verified" : "Pending email"}
                    tone={patient.email_verified_at ? "success" : "warning"}
                  />
                </article>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            id="consultations"
            title="Consultation Inspector"
            subtitle="Review consultation assignments, outcomes, and message transcripts."
          >
            <div className="admin-dashboard__session-actions">
              <button className="button button--secondary" type="button" onClick={loadConsultations}>
                Refresh Consultations
              </button>
            </div>
            <div className={`admin-state admin-state--${consultationState.status}`}>
              <p className="doctor-state__message">{consultationState.message}</p>
            </div>
            <div className="admin-list">
              {consultationState.consultations.map((consultation) => (
                <article className="admin-list__item admin-list__item--doctor" key={consultation.consultation_id}>
                  <div>
                    <strong>{consultation.patient_name} with Dr. {consultation.doctor_name}</strong>
                    <p className="doctor-state__message">
                      {consultation.consultation_id} | {consultation.message_count || 0} messages
                    </p>
                    <p className="doctor-state__message">
                      {consultation.created_at || "Unknown date"} | {consultation.diagnosis || "No diagnosis recorded"}
                    </p>
                  </div>
                  <div className="admin-list__actions">
                    <StatusPill
                      label={consultation.status || "unknown"}
                      tone={consultation.status === "active" ? "success" : "warning"}
                    />
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={() => handleConsultationInspect(consultation.consultation_id)}
                    >
                      Inspect
                    </button>
                  </div>
                </article>
              ))}
            </div>
            {consultationState.selected ? (
              <div className="admin-transcript">
                <div className="admin-transcript__header">
                  <strong>{consultationState.selected.consultation.consultation_id}</strong>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => setConsultationState((current) => ({ ...current, selected: null }))}
                  >
                    Close
                  </button>
                </div>
                {consultationState.selected.messages.map((message, index) => (
                  <article className="admin-transcript__message" key={`${message.created_at}-${index}`}>
                    <strong>{message.sender_role}</strong>
                    <p>{message.message_text || "Attachment"}</p>
                    <span>{message.created_at}</span>
                  </article>
                ))}
              </div>
            ) : null}
          </SectionCard>

          <SectionCard
            id="delivery-settings"
            title="OTP & Email Delivery"
            subtitle="Check delivery readiness and send safe test OTP messages."
          >
            <div className={`admin-state admin-state--${deliveryAdminState.status}`}>
              <p className="doctor-state__message">{deliveryAdminState.message}</p>
            </div>
            {deliveryAdminState.settings ? (
              <div className="delivery-status-list">
                {["email", "telegram"].map((channel) => (
                  <article
                    className={`delivery-status delivery-status--${deliveryAdminState.settings[channel]?.ready ? "ready" : "pending"}`}
                    key={channel}
                  >
                    <div>
                      <h3>{deliveryAdminState.settings[channel]?.label}</h3>
                      <p>{deliveryAdminState.settings[channel]?.message}</p>
                    </div>
                    <StatusPill
                      label={deliveryAdminState.settings[channel]?.ready ? "Ready" : "Setup needed"}
                      tone={deliveryAdminState.settings[channel]?.ready ? "success" : "warning"}
                    />
                  </article>
                ))}
              </div>
            ) : null}
            <form className="form-panel form-panel--inline" onSubmit={handleDeliveryTest}>
              <label className="form-field">
                <span className="form-field__label">Channel</span>
                <select
                  className="form-field__input"
                  value={deliveryTestForm.channel}
                  onChange={(event) =>
                    setDeliveryTestForm((current) => ({ ...current, channel: event.target.value }))
                  }
                >
                  <option value="email">Email</option>
                  <option value="telegram">Telegram</option>
                </select>
              </label>
              <label className="form-field form-field--grow">
                <span className="form-field__label">
                  {deliveryTestForm.channel === "email" ? "Email Address" : "Telegram ID"}
                </span>
                <input
                  className="form-field__input"
                  type={deliveryTestForm.channel === "email" ? "email" : "text"}
                  value={deliveryTestForm.target}
                  onChange={(event) =>
                    setDeliveryTestForm((current) => ({ ...current, target: event.target.value }))
                  }
                  required
                />
              </label>
              <button className="button button--primary" type="submit">Send Test</button>
              <button className="button button--secondary" type="button" onClick={loadDeliverySettings}>
                Refresh Status
              </button>
            </form>
          </SectionCard>

          <SectionCard
            id="medical-reports"
            title="Medical Report Requests"
            subtitle="Review patient medical report requests, payment status, and doctor assignment."
          >
            <div className={`admin-state admin-state--${medicalReportState.status}`}>
              <p className="doctor-state__message">{medicalReportState.message}</p>
            </div>

            <div className="admin-list">
              {medicalReportState.requests.map((request) => (
                <article className="admin-list__item admin-list__item--doctor" key={request.request_id}>
                  <div>
                    <strong>{request.request_id}</strong>
                    <p className="doctor-state__message">
                      Patient: {request.patient_id} | Doctor: {request.doctor_id || "Unassigned"}
                    </p>
                    <p className="doctor-state__message">
                      Payment: {request.payment_status} | Status: {request.status}
                    </p>
                    {request.request_note ? (
                      <p className="doctor-state__message">{request.request_note}</p>
                    ) : null}
                  </div>
                  <div className="hero-card__actions">
                    {request.doctor_id ? (
                      <button
                        className="button button--secondary"
                        type="button"
                        onClick={() => handleAssignLastDoctor(request.request_id, request.doctor_id)}
                      >
                        Reassign Last Doctor
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            id="health-tips"
            title="Landing Health Tips"
            subtitle="Add, update, remove, and reorder the rotating tips shown on the homepage."
          >
            <form className="form-panel" onSubmit={handleTipSubmit}>
              <label className="form-field">
                <span className="form-field__label">Eyebrow</span>
                <input
                  className="form-field__input"
                  type="text"
                  value={tipForm.eyebrow}
                  onChange={(event) => setTipForm((current) => ({ ...current, eyebrow: event.target.value }))}
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Title</span>
                <input
                  className="form-field__input"
                  type="text"
                  value={tipForm.title}
                  onChange={(event) => setTipForm((current) => ({ ...current, title: event.target.value }))}
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Body</span>
                <textarea
                  className="form-field__input form-field__input--textarea"
                  rows="4"
                  value={tipForm.body}
                  onChange={(event) => setTipForm((current) => ({ ...current, body: event.target.value }))}
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Sort Order</span>
                <input
                  className="form-field__input"
                  type="number"
                  value={tipForm.sort_order}
                  onChange={(event) => setTipForm((current) => ({ ...current, sort_order: Number(event.target.value) }))}
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Visibility</span>
                <select
                  className="form-field__input"
                  value={tipForm.is_active ? "active" : "hidden"}
                  onChange={(event) =>
                    setTipForm((current) => ({ ...current, is_active: event.target.value === "active" }))
                  }
                >
                  <option value="active">Active</option>
                  <option value="hidden">Hidden</option>
                </select>
              </label>
              <div className="hero-card__actions">
                <button className="button button--primary" type="submit">
                  {tipForm.id ? "Update Tip" : "Add Tip"}
                </button>
                {tipForm.id ? (
                  <button className="button button--secondary" type="button" onClick={resetTipForm}>
                    Cancel Edit
                  </button>
                ) : null}
              </div>
            </form>

            <div className={`admin-state admin-state--${tipsState.status}`}>
              <p className="doctor-state__message">{tipsState.message}</p>
            </div>

            <div className="admin-list">
              {tipsState.tips.map((tip) => (
                <article className="admin-list__item admin-list__item--doctor" key={tip.id}>
                  <div>
                    <strong>{tip.title}</strong>
                    <p className="doctor-state__message">
                      {tip.eyebrow} | Order: {tip.sort_order} | {tip.is_active ? "Active" : "Hidden"}
                    </p>
                    <p className="doctor-state__message">{tip.body}</p>
                  </div>
                  <div className="hero-card__actions">
                    <button className="button button--secondary" type="button" onClick={() => handleEditTip(tip)}>
                      Edit
                    </button>
                    <button className="button button--secondary" type="button" onClick={() => handleDeleteTip(tip.id)}>
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </SectionCard>
        </div>

        <aside className="admin-dashboard__rail">
          {!authState.session ? (
            <SectionCard
              title="Operational Markers"
              subtitle="A quick read on what is currently protected and available."
            >
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
          ) : null}

          <SectionCard
            id="doctor-applications"
            title="Doctor Applications"
            subtitle="Approve verified email applications before doctors can sign in or go online."
          >
            <div className={`admin-state admin-state--${summaryState.status}`}>
              {summaryState.summary?.pending_doctor_applications?.length ? (
                <div className="admin-list">
                  {summaryState.summary.pending_doctor_applications.map((doctor) => (
                    <article className="admin-list__item admin-list__item--doctor" key={doctor.telegram_id}>
                      <div>
                        <strong>{doctor.name}</strong>
                        <p className="doctor-state__message">
                          {doctor.specialty} | {doctor.experience} years | License: {doctor.license_id || "N/A"}
                        </p>
                        <p className="doctor-state__message">
                          {doctor.email || "No email"} {doctor.phone ? `| ${doctor.phone}` : ""}
                        </p>
                        {doctor.license_file_url ? (
                          <p className="doctor-state__message">
                            Licence:{" "}
                            <a
                              href={`${API_BASE_URL}${doctor.license_file_url}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {doctor.license_file_name || "Open annual licence"}
                            </a>
                            {doctor.license_file_size ? ` | ${formatFileSize(doctor.license_file_size)}` : ""}
                          </p>
                        ) : (
                          <p className="doctor-state__message">Licence upload missing</p>
                        )}
                        <label className="form-field admin-list__reason">
                          <span className="form-field__label">Rejection reason</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="2"
                            value={doctorApplicationReasons[doctor.telegram_id] || ""}
                            onChange={(event) =>
                              setDoctorApplicationReasons((current) => ({
                                ...current,
                                [doctor.telegram_id]: event.target.value,
                              }))
                            }
                          />
                        </label>
                      </div>
                      <div className="admin-list__actions">
                        <button
                          className="button button--primary"
                          type="button"
                          onClick={() => handleDoctorApplicationDecision(doctor.telegram_id, "approve")}
                        >
                          Approve
                        </button>
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => handleDoctorApplicationDecision(doctor.telegram_id, "reject")}
                        >
                          Reject
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="doctor-state__message">No pending doctor applications.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard
            id="verified-doctors"
            title="Verified Doctors"
            subtitle="Database-backed doctors visible to the current live system."
          >
            <div className={`admin-state admin-state--${summaryState.status}`}>
              {summaryState.summary?.verified_doctor_records?.length ? (
                <div className="admin-list">
                  {summaryState.summary.verified_doctor_records.map((doctor) => (
                    <article className="admin-list__item admin-list__item--doctor" key={doctor.telegram_id}>
                      <div>
                        <strong>{doctor.name}</strong>
                        <p className="doctor-state__message">
                          {doctor.specialty} | Doctor ID: {doctor.telegram_id}
                        </p>
                        <p className="doctor-state__message">
                          Licence: {doctor.license_id || "N/A"} | {doctor.license_expiry_date || "No expiry"}
                        </p>
                        <StatusPill
                          label={doctor.license_status?.label || "Licence status unknown"}
                          tone={doctor.license_status?.tone || "warning"}
                        />
                        {doctor.license_file_url ? (
                          <p className="doctor-state__message">
                            <a href={`${API_BASE_URL}${doctor.license_file_url}`} target="_blank" rel="noreferrer">
                              {doctor.license_file_name || "Open licence"}
                            </a>
                            {doctor.license_file_size ? ` | ${formatFileSize(doctor.license_file_size)}` : ""}
                          </p>
                        ) : null}
                        <label className="form-field admin-list__reason">
                          <span className="form-field__label">Suspension reason</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="2"
                            value={doctorAccountReasons[doctor.telegram_id] || ""}
                            onChange={(event) =>
                              setDoctorAccountReasons((current) => ({
                                ...current,
                                [doctor.telegram_id]: event.target.value,
                              }))
                            }
                          />
                        </label>
                      </div>
                      <div className="admin-list__actions">
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
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => handleLicenseReminder(doctor.telegram_id)}
                        >
                          Send Reminder
                        </button>
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => handleDoctorAccountAction(doctor.telegram_id, "suspend")}
                        >
                          Suspend
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="doctor-state__message">No verified doctors found in the database.</p>
              )}
            </div>
          </SectionCard>

          <SectionCard
            id="suspended-doctors"
            title="Suspended Doctors"
            subtitle="Doctors blocked from sign-in, going online, and connecting to patients."
          >
            <div className={`admin-state admin-state--${summaryState.status}`}>
              {summaryState.summary?.suspended_doctor_records?.length ? (
                <div className="admin-list">
                  {summaryState.summary.suspended_doctor_records.map((doctor) => (
                    <article className="admin-list__item admin-list__item--doctor" key={doctor.telegram_id}>
                      <div>
                        <strong>{doctor.name}</strong>
                        <p className="doctor-state__message">
                          {doctor.specialty} | Doctor ID: {doctor.telegram_id}
                        </p>
                        <p className="doctor-state__message">
                          Licence: {doctor.license_id || "N/A"} | {doctor.license_expiry_date || "No expiry"}
                        </p>
                      </div>
                      <div className="admin-list__actions">
                        <StatusPill label="suspended" tone="danger" />
                        <button
                          className="button button--primary"
                          type="button"
                          onClick={() => handleDoctorAccountAction(doctor.telegram_id, "reactivate")}
                        >
                          Reactivate
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="doctor-state__message">No suspended doctors.</p>
              )}
            </div>
          </SectionCard>
        </aside>
      </div>
    </div>
  );
}
