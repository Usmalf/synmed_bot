import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import StatusPill from "../../components/StatusPill.jsx";
import {
  approveDoctorApplication,
  assignAdminMedicalReportRequest,
  clearAdminPaymentAttention,
  createAdminPartner,
  createAdminHealthTip,
  deleteAdminPaymentAttention,
  deleteAdminHealthTip,
  downloadAdminBackup,
  fetchAdminEmailReminders,
  fetchAdminAlerts,
  fetchAdminAuditLogs,
  fetchAdminBackupStatus,
  fetchAdminConsultation,
  fetchAdminConsultations,
  fetchAdminDeliverySettings,
  fetchAdminErrorLogs,
  fetchAdminHealthTips,
  fetchAdminMedicalReportRequests,
  fetchAdminMail,
  fetchAdminPayments,
  fetchAdminPatientDetail,
  fetchAdminPatients,
  fetchAdminPartners,
  fetchAdminRatings,
  fetchAdminSupportTicket,
  fetchAdminSupportTickets,
  fetchAdminSummary,
  reactivateDoctorAccount,
  rejectDoctorApplication,
  sendDoctorLicenseReminder,
  sendAdminReminderTest,
  sendAdminPatientDocument,
  sendAdminMail,
  grantAdminConsultationAccess,
  revokeAdminConsultationAccess,
  searchAdminRecords,
  markAdminMailRead,
  suspendDoctorAccount,
  testAdminDelivery,
  updateAdminEmailBranding,
  updateAdminHealthTip,
  updateAdminPaymentSettings,
  updateAdminPartnerStatus,
  updateAdminSupportTicketStatus,
  verifyAdminPayment,
} from "../../api/admin.js";
import "../../styles/forms.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const PAGE_SIZE = 10;

function PageHeader({ title, description, actions, showSearch = false }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ patients: [], doctors: [] });
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults({ patients: [], doctors: [] });
      setOpen(false);
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      try {
        const result = await searchAdminRecords(query);
        setResults(result);
        setOpen(true);
      } catch {
        setResults({ patients: [], doctors: [] });
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  function openPatient(patientId) {
    setOpen(false);
    setQuery("");
    navigate(`/admin/patients?patient=${encodeURIComponent(patientId)}`);
  }

  return (
    <header className="admin-page-header">
      <div>
        {showSearch ? (
          <div className="admin-global-search">
            <input
              aria-label="Search patient or doctor records"
              placeholder="Search patient or doctor records"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onFocus={() => query.trim().length >= 2 && setOpen(true)}
            />
            {open ? (
              <div className="admin-global-search__results">
                {results.patients.map((patient) => (
                  <button key={`patient-${patient.patient_id}`} type="button" onClick={() => openPatient(patient.patient_id)}>
                    <strong>{patient.name || "Patient"}</strong>
                    <span>Patient / {patient.patient_id}</span>
                  </button>
                ))}
                {results.doctors.map((doctor) => (
                  <button key={`doctor-${doctor.telegram_id}`} type="button" onClick={() => { setOpen(false); navigate(`/admin/doctors?query=${encodeURIComponent(doctor.name)}`); }}>
                    <strong>{doctor.name || "Doctor"}</strong>
                    <span>Doctor / {doctor.specialty || doctor.telegram_id}</span>
                  </button>
                ))}
                {!results.patients.length && !results.doctors.length ? <div className="admin-global-search__empty">No matching records.</div> : null}
              </div>
            ) : null}
          </div>
        ) : null}
        <h1>{title}</h1>
        <span>{description}</span>
      </div>
      {actions ? <div className="admin-page-header__actions">{actions}</div> : null}
    </header>
  );
}

function Notice({ state }) {
  if (!state?.message) return null;
  return <div className={`admin-notice admin-notice--${state.status || "idle"}`}>{state.message}</div>;
}

function EmptyState({ children }) {
  return <div className="admin-empty">{children}</div>;
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

function ClearIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M5 5 19 19M19 5 5 19" />
    </svg>
  );
}

function Pager({ page, total, onChange }) {
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <div className="admin-pager">
      <span>Page {page} of {pages}</span>
      <div>
        <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
        <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</button>
      </div>
    </div>
  );
}

function ConfirmDialog({ dialog, busy, onCancel, onConfirm }) {
  if (!dialog) return null;
  return (
    <div className="admin-dialog-backdrop" role="presentation" onMouseDown={onCancel}>
      <div className="admin-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
        <h2 id="admin-dialog-title">{dialog.title}</h2>
        <p>{dialog.message}</p>
        {dialog.requiresReason ? (
          <label className="form-field">
            <span className="form-field__label">Reason</span>
            <textarea
              autoFocus
              className="form-field__input form-field__input--textarea"
              rows="3"
              value={dialog.reason || ""}
              onChange={(event) => dialog.setReason(event.target.value)}
              required
            />
          </label>
        ) : null}
        <div className="admin-dialog__actions">
          <button className="button button--secondary" type="button" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={dialog.danger ? "button admin-button--danger" : "button button--primary"} type="button" onClick={onConfirm} disabled={busy || (dialog.requiresReason && !dialog.reason?.trim())}>
            {busy ? "Working..." : dialog.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function DataPanel({ title, subtitle, children }) {
  return (
    <section className="admin-panel">
      <header className="admin-panel__header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </header>
      {children}
    </section>
  );
}

function formatDate(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatCurrency(amount, currency = "NGN") {
  const numeric = Number(amount || 0);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "NGN",
      maximumFractionDigits: 0,
    }).format(numeric);
  } catch {
    return `${currency || "NGN"} ${numeric.toLocaleString()}`;
  }
}

function formatBytes(value = 0) {
  const bytes = Number(value || 0);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const amount = bytes / 1024 ** index;
  return `${amount.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

function formatAction(value = "") {
  return value.split("_").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

function compactText(value, maxLength = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}...`;
}

function RatingStars({ value }) {
  const numeric = Number(value || 0);
  return (
    <span className="admin-rating-stars" aria-label={`${numeric || 0} out of 5`}>
      {"★".repeat(Math.max(0, Math.min(5, Math.round(numeric))))}
      {"☆".repeat(Math.max(0, 5 - Math.max(0, Math.min(5, Math.round(numeric)))))}
    </span>
  );
}

export function AdminOverviewPage() {
  const [state, setState] = useState({ status: "loading", message: "Loading operations overview...", summary: null, alerts: [], logs: [] });

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Refreshing operations overview..." }));
    try {
      const [summary, alerts, audit] = await Promise.all([
        fetchAdminSummary(),
        fetchAdminAlerts(),
        fetchAdminAuditLogs(8),
      ]);
      setState({ status: "success", message: "", summary, alerts: alerts.alerts || [], logs: audit.logs || [] });
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to load admin overview." }));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const metrics = [
    ["Registered patients", state.summary?.registered_patients],
    ["Verified doctors", state.summary?.verified_doctors],
    ["Pending applications", state.summary?.pending_doctors],
    ["Active consultations", state.summary?.active_consultations],
    ["Medical reports", state.summary?.medical_report_requests],
    ["Partners", state.summary?.partners],
    ["Pending partners", state.summary?.pending_partners],
    ["Verified customer agents", state.summary?.verified_customer_care_agents],
    ["Pending customer agents", state.summary?.pending_customer_care_agents],
    ["Due follow-ups", state.summary?.due_followups],
  ];

  return (
    <>
      <PageHeader showSearch title="Operations overview" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <section className="admin-metric-grid">
        {metrics.map(([label, value]) => (
          <article className="admin-metric" key={label}>
            <span>{label}</span>
            <strong>{value ?? "..."}</strong>
          </article>
        ))}
      </section>

      <div className="admin-two-column">
        <DataPanel title="Operational alerts" subtitle="Items that may need attention now.">
          <div className="admin-alert-list">
            {state.alerts.length ? state.alerts.map((alert) => (
              <Link className={`admin-alert admin-alert--${alert.tone}`} key={alert.id} to={alert.href}>
                <div>
                  <strong>{alert.title}</strong>
                  <p>{alert.message}</p>
                </div>
                <span>Review</span>
              </Link>
            )) : <EmptyState>No current operational alerts.</EmptyState>}
          </div>
        </DataPanel>

        <DataPanel title="Recent activity" subtitle="Latest protected actions completed by administrators.">
          <div className="admin-activity-list">
            {state.logs.length ? state.logs.map((log) => (
              <article key={log.id}>
                <strong>{formatAction(log.action)}</strong>
                <p>{log.target_type} {log.target_id}</p>
                <span>{formatDate(log.created_at)}</span>
              </article>
            )) : <EmptyState>No audit activity has been recorded yet.</EmptyState>}
          </div>
          <Link className="admin-panel__footer-link" to="/admin/activity">View full activity</Link>
        </DataPanel>
      </div>
    </>
  );
}

export function AdminDoctorsPage() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState({ status: "loading", message: "Loading doctors...", summary: null });
  const [query, setQuery] = useState(searchParams.get("query") || "");
  const [filter, setFilter] = useState(searchParams.get("filter") || "all");
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState(null);
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load(message = "") {
    setState((current) => ({ ...current, status: "loading", message: message || "Loading doctors..." }));
    try {
      const summary = await fetchAdminSummary();
      setState({ status: "success", message: "", summary });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load doctors.", summary: null });
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const requestedQuery = searchParams.get("query");
    if (requestedQuery !== null) {
      setQuery(requestedQuery);
      setPage(1);
    }
  }, [searchParams]);

  const doctors = useMemo(() => {
    const pending = (state.summary?.pending_doctor_applications || []).map((doctor) => ({ ...doctor, category: "pending" }));
    const verified = (state.summary?.verified_doctor_records || []).map((doctor) => ({ ...doctor, category: "verified" }));
    const suspended = (state.summary?.suspended_doctor_records || []).map((doctor) => ({ ...doctor, category: "suspended" }));
    const normalized = query.trim().toLowerCase();
    return [...pending, ...verified, ...suspended].filter((doctor) => {
      const matchesQuery = !normalized || [doctor.name, doctor.email, doctor.specialty, doctor.license_id, doctor.telegram_id].some((value) => String(value || "").toLowerCase().includes(normalized));
      const days = doctor.license_status?.days_left;
      const matchesFilter =
        filter === "all" ||
        doctor.category === filter ||
        (filter === "expired" && days !== null && days < 0) ||
        (filter === "expiring" && days !== null && days >= 0 && days <= 14);
      return matchesQuery && matchesFilter;
    });
  }, [state.summary, query, filter]);

  const visibleDoctors = doctors.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function ask(action, doctor) {
    let reason = "";
    const definitions = {
      approve: ["Approve doctor application", `Approve ${doctor.name} and allow access to the doctor workspace?`, "Approve", false, false],
      reject: ["Reject doctor application", `Reject ${doctor.name}'s application and email the reason provided?`, "Reject", true, true],
      suspend: ["Suspend doctor account", `Suspend ${doctor.name} and immediately block doctor access?`, "Suspend", true, true],
      reactivate: ["Reactivate doctor account", `Restore workspace access for ${doctor.name}?`, "Reactivate", false, false],
      reminder: ["Send licence reminder", `Email a licence renewal reminder to ${doctor.name}?`, "Send reminder", false, false],
    };
    const [title, message, confirmLabel, danger, requiresReason] = definitions[action];
    const next = {
      action, doctor, title, message, confirmLabel, danger, requiresReason, reason,
      setReason: (value) => setDialog((current) => ({ ...current, reason: value })),
    };
    setDialog(next);
  }

  async function confirmAction() {
    if (!dialog) return;
    setBusy(true);
    try {
      const id = dialog.doctor.telegram_id;
      if (dialog.action === "approve") await approveDoctorApplication(id);
      if (dialog.action === "reject") await rejectDoctorApplication(id, dialog.reason);
      if (dialog.action === "suspend") await suspendDoctorAccount(id, dialog.reason);
      if (dialog.action === "reactivate") await reactivateDoctorAccount(id);
      if (dialog.action === "reminder") await sendDoctorLicenseReminder(id);
      setDialog(null);
      await load("Refreshing doctors...");
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to complete doctor action." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Doctors" actions={<button className="button button--secondary" type="button" onClick={() => load()}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Doctor directory" subtitle={`${doctors.length} matching record(s)`}>
        <div className="admin-toolbar">
          <input type="search" placeholder="Search name, email, specialty or licence" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
          <select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1); }}>
            <option value="all">All doctors</option>
            <option value="pending">Pending applications</option>
            <option value="verified">Verified doctors</option>
            <option value="suspended">Suspended doctors</option>
            <option value="expiring">Licence expiring soon</option>
            <option value="expired">Licence expired</option>
          </select>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Doctor</th><th>Specialty</th><th>Licence</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {visibleDoctors.map((doctor) => (
                <tr key={`${doctor.category}-${doctor.telegram_id}`}>
                  <td>
                    <button className="admin-record-link" type="button" onClick={() => setSelectedDoctor(doctor)}>
                      <strong>{doctor.name}</strong>
                      <span>{doctor.email || `ID ${doctor.telegram_id}`}</span>
                    </button>
                  </td>
                  <td>{doctor.specialty || "Not recorded"}</td>
                  <td>
                    <strong>{doctor.license_id || "Not recorded"}</strong>
                    <span>{doctor.license_expiry_date || "No expiry date"}</span>
                    {doctor.license_file_url ? <a href={`${API_BASE_URL}${doctor.license_file_url}`} target="_blank" rel="noreferrer">Open licence</a> : null}
                  </td>
                  <td><StatusPill label={doctor.category} tone={doctor.category === "verified" ? "success" : doctor.category === "suspended" ? "danger" : "warning"} /></td>
                  <td>
                    <div className="admin-row-actions">
                      {doctor.category === "pending" ? <>
                        <button type="button" onClick={() => ask("approve", doctor)}>Approve</button>
                        <button type="button" onClick={() => ask("reject", doctor)}>Reject</button>
                      </> : null}
                      {doctor.category === "verified" ? <>
                        <button type="button" onClick={() => ask("reminder", doctor)}>Remind</button>
                        <button type="button" onClick={() => ask("suspend", doctor)}>Suspend</button>
                      </> : null}
                      {doctor.category === "suspended" ? <button type="button" onClick={() => ask("reactivate", doctor)}>Reactivate</button> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!visibleDoctors.length ? <EmptyState>No doctors match this view.</EmptyState> : null}
        </div>
        <Pager page={page} total={doctors.length} onChange={setPage} />
      </DataPanel>
      <ConfirmDialog dialog={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={confirmAction} />
      {selectedDoctor ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedDoctor(null)}>
          <section className="admin-record-card" role="dialog" aria-modal="true" aria-labelledby="doctor-record-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Doctor biodata</span>
                <h2 id="doctor-record-title">{selectedDoctor.name}</h2>
                <p>Doctor ID: {selectedDoctor.telegram_id}</p>
              </div>
              <button type="button" onClick={() => setSelectedDoctor(null)} aria-label="Close doctor biodata">Close</button>
            </header>

            <div className="admin-biodata-grid">
              {[
                ["Specialty", selectedDoctor.specialty],
                ["Experience", selectedDoctor.experience],
                ["Email", selectedDoctor.email],
                ["Phone", selectedDoctor.phone],
                ["Account status", selectedDoctor.category],
                ["Runtime status", selectedDoctor.status],
                ["Licence number", selectedDoctor.license_id],
                ["Licence expiry", selectedDoctor.license_expiry_date],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value || "Not recorded"}</strong>
                </div>
              ))}
            </div>

            <section className="admin-doctor-licence">
              <div>
                <h3>Annual licence</h3>
                <p>{selectedDoctor.license_file_name || "No licence filename recorded."}</p>
                {selectedDoctor.license_status ? (
                  <StatusPill
                    label={selectedDoctor.license_status.label}
                    tone={selectedDoctor.license_status.tone}
                  />
                ) : null}
              </div>
              {selectedDoctor.license_file_url ? (
                <a
                  className="button button--primary"
                  href={`${API_BASE_URL}${selectedDoctor.license_file_url}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Preview licence
                </a>
              ) : (
                <StatusPill label="Licence file unavailable" tone="warning" />
              )}
            </section>
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AdminPatientsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState({ status: "loading", message: "Loading patients...", patients: [] });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [detailState, setDetailState] = useState({ status: "idle", message: "", detail: null });
  const [doctors, setDoctors] = useState([]);
  const [sendForm, setSendForm] = useState(null);

  async function load(search = query) {
    setState((current) => ({ ...current, status: "loading", message: "Loading patient records..." }));
    try {
      const result = await fetchAdminPatients(search);
      setState({ status: "success", message: "", patients: result.patients || [] });
      setPage(1);
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load patients.", patients: [] });
    }
  }

  useEffect(() => {
    load("");
    fetchAdminSummary().then((summary) => setDoctors(summary.verified_doctor_records || [])).catch(() => {});
  }, []);

  useEffect(() => {
    const patientId = searchParams.get("patient");
    if (patientId) openPatient(patientId);
  }, [searchParams]);

  async function openPatient(patientId) {
    setDetailState({
      status: "loading",
      message: "Loading patient biodata...",
      detail: { patient: { name: "Loading patient...", patient_id: patientId }, documents: [] },
    });
    try {
      const detail = await fetchAdminPatientDetail(patientId);
      setDetailState({ status: "success", message: "", detail });
      if (searchParams.get("patient") !== patientId) {
        setSearchParams({ patient: patientId });
      }
    } catch (error) {
      setDetailState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to load patient biodata.",
      }));
    }
  }

  function closePatient() {
    setDetailState({ status: "idle", message: "", detail: null });
    setSendForm(null);
    setSearchParams({});
  }

  async function handleSendDocument(event) {
    event.preventDefault();
    setDetailState((current) => ({ ...current, status: "loading", message: "Sending document..." }));
    try {
      const result = await sendAdminPatientDocument(detailState.detail.patient.patient_id, sendForm);
      setDetailState((current) => ({ ...current, status: "success", message: result.message }));
      setSendForm(null);
    } catch (error) {
      setDetailState((current) => ({ ...current, status: "error", message: error.message || "Unable to send document." }));
    }
  }

  const visible = state.patients.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  return (
    <>
      <PageHeader title="Patients" />
      <Notice state={state} />
      <DataPanel title="Patient directory" subtitle={`${state.patients.length} patient record(s)`}>
        <form className="admin-toolbar admin-toolbar--search" onSubmit={(event) => { event.preventDefault(); load(query); }}>
          <input type="search" placeholder="Search patient ID, name, email or phone" value={query} onChange={(event) => setQuery(event.target.value)} />
          <button className="admin-search-action admin-search-action--submit" type="submit" aria-label="Search" title="Search">
            <SearchIcon />
          </button>
          <button className="admin-search-action" type="button" aria-label="Clear search" title="Clear search" onClick={() => { setQuery(""); load(""); }}>
            <ClearIcon />
          </button>
        </form>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Patient</th><th>Contact</th><th>Profile</th><th>Consultations</th><th>Joined</th></tr></thead>
            <tbody>{visible.map((patient) => (
              <tr key={patient.id}>
                <td>
                  <button className="admin-record-link" type="button" onClick={() => openPatient(patient.patient_id)}>
                    <strong>{patient.name || "Patient"}</strong>
                    <span>{patient.patient_id}</span>
                  </button>
                </td>
                <td>{patient.email || patient.phone || "Not recorded"}<span>{patient.email_verified_at ? "Email verified" : "Email not verified"}</span></td>
                <td>{patient.age || "Age N/A"} / {patient.gender || "Gender N/A"}</td>
                <td><strong>{patient.consultation_count || 0}</strong><span>{patient.last_consultation_at ? `Last: ${formatDate(patient.last_consultation_at)}` : "No consultations"}</span></td>
                <td>{formatDate(patient.created_at)}</td>
              </tr>
            ))}</tbody>
          </table>
          {!visible.length ? <EmptyState>No patient records found.</EmptyState> : null}
        </div>
        <Pager page={page} total={state.patients.length} onChange={setPage} />
      </DataPanel>
      {detailState.detail ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={closePatient}>
          <section className="admin-record-card" role="dialog" aria-modal="true" aria-labelledby="patient-record-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Patient biodata</span>
                <h2 id="patient-record-title">{detailState.detail.patient.name}</h2>
                <p>{detailState.detail.patient.patient_id}</p>
              </div>
              <button type="button" onClick={closePatient} aria-label="Close patient biodata">Close</button>
            </header>
            <Notice state={detailState} />
            <div className="admin-biodata-grid">
              {[
                ["Age", detailState.detail.patient.age],
                ["Gender", detailState.detail.patient.gender],
                ["Phone", detailState.detail.patient.phone],
                ["Email", detailState.detail.patient.email],
                ["Address", detailState.detail.patient.address],
                ["Allergies", detailState.detail.patient.allergy || "None recorded"],
                ["Medical conditions", detailState.detail.patient.medical_conditions || "None recorded"],
                ["Email status", detailState.detail.patient.email_verified_at ? "Verified" : "Not verified"],
              ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value || "Not recorded"}</strong></div>)}
            </div>
            <div className="admin-record-card__documents">
              <h3>Clinical documents</h3>
              {detailState.detail.documents.map((document) => (
                <article key={`${document.kind}-${document.document_id}`}>
                  <div>
                    <strong>{document.title}</strong>
                    <span>{formatDate(document.created_at)}</span>
                  </div>
                  <div className="admin-row-actions">
                    <a href={`${API_BASE_URL}${document.asset_url}`} target="_blank" rel="noreferrer">Preview</a>
                    <button type="button" onClick={() => setSendForm({
                      document_kind: document.kind,
                      document_id: document.document_id,
                      recipient_type: "patient",
                      doctor_id: document.doctor_id || "",
                      message: "",
                    })}>Send</button>
                  </div>
                </article>
              ))}
              {!detailState.detail.documents.length ? <EmptyState>No prescriptions, investigations, or reports found.</EmptyState> : null}
            </div>
            {sendForm ? (
              <form className="admin-document-send" onSubmit={handleSendDocument}>
                <label><span>Send copy to</span><select value={sendForm.recipient_type} onChange={(event) => setSendForm((current) => ({ ...current, recipient_type: event.target.value }))}><option value="patient">Patient email</option><option value="doctor">Doctor inbox</option></select></label>
                {sendForm.recipient_type === "doctor" ? (
                  <label><span>Doctor</span><select required value={sendForm.doctor_id} onChange={(event) => setSendForm((current) => ({ ...current, doctor_id: event.target.value }))}><option value="">Select doctor</option>{doctors.map((doctor) => <option key={doctor.telegram_id} value={doctor.telegram_id}>{doctor.name}</option>)}</select></label>
                ) : null}
                <label><span>Message</span><textarea rows="2" value={sendForm.message} onChange={(event) => setSendForm((current) => ({ ...current, message: event.target.value }))} /></label>
                <div className="admin-form__actions"><button className="button button--primary" type="submit">Send document</button><button className="button button--secondary" type="button" onClick={() => setSendForm(null)}>Cancel</button></div>
              </form>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AdminConsultationsPage() {
  const [state, setState] = useState({ status: "loading", message: "Loading consultations...", consultations: [], selected: null });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [page, setPage] = useState(1);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading consultations..." }));
    try {
      const result = await fetchAdminConsultations();
      setState({ status: "success", message: "", consultations: result.consultations || [], selected: null });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load consultations.", consultations: [], selected: null });
    }
  }
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return state.consultations.filter((item) => {
      const matchesQuery = !normalized || [item.consultation_id, item.patient_name, item.doctor_name, item.patient_id].some((value) => String(value || "").toLowerCase().includes(normalized));
      return matchesQuery && (statusFilter === "all" || item.status === statusFilter);
    });
  }, [state.consultations, query, statusFilter]);
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function inspect(id) {
    setState((current) => ({ ...current, status: "loading", message: "Loading consultation transcript..." }));
    try {
      const selected = await fetchAdminConsultation(id);
      setState((current) => ({ ...current, status: "success", message: "", selected }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to inspect consultation." }));
    }
  }

  return (
    <>
      <PageHeader title="Consultations" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Consultation records" subtitle={`${filtered.length} matching record(s)`}>
        <div className="admin-toolbar">
          <input type="search" placeholder="Search consultation, patient or doctor" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
          <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="closed">Closed</option>
            <option value="queued">Queued</option>
          </select>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Consultation</th><th>Patient</th><th>Doctor</th><th>Status</th><th>Messages</th><th>Action</th></tr></thead>
            <tbody>{visible.map((item) => (
              <tr key={item.consultation_id}>
                <td><strong>{item.consultation_id}</strong><span>{formatDate(item.created_at)}</span></td>
                <td>{item.patient_name}<span>{item.patient_id}</span></td>
                <td>{item.doctor_name || "Unassigned"}</td>
                <td><StatusPill label={item.status} tone={item.status === "active" ? "success" : item.status === "closed" ? "neutral" : "warning"} /></td>
                <td>{item.message_count || 0}</td>
                <td><button type="button" onClick={() => inspect(item.consultation_id)}>Inspect</button></td>
              </tr>
            ))}</tbody>
          </table>
          {!visible.length ? <EmptyState>No consultations match this view.</EmptyState> : null}
        </div>
        <Pager page={page} total={filtered.length} onChange={setPage} />
      </DataPanel>
      {state.selected ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setState((current) => ({ ...current, selected: null }))}>
          <section className="admin-record-card admin-record-card--transcript" role="dialog" aria-modal="true" aria-labelledby="consultation-inspect-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><span>Consultation inspection</span><h2 id="consultation-inspect-title">{state.selected.consultation.consultation_id}</h2><p>{state.selected.consultation.patient_name} with {state.selected.consultation.doctor_name}</p></div>
              <button type="button" onClick={() => setState((current) => ({ ...current, selected: null }))}>Close</button>
            </header>
            <div className="admin-transcript">
            {state.selected.messages.map((message, index) => (
              <article className="admin-transcript__message" key={`${message.created_at}-${index}`}>
                <strong>{formatAction(message.sender_role)}</strong>
                <p>{message.message_text || message.asset_path || "Attachment"}</p>
                <span>{formatDate(message.created_at)}</span>
              </article>
            ))}
            {!state.selected.messages.length ? <EmptyState>No messages recorded.</EmptyState> : null}
          </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AdminPaymentsPage() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState({ status: "loading", message: "Loading payment ledger...", payments: [] });
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(searchParams.get("filter") || "all");
  const [page, setPage] = useState(1);
  const [grantForm, setGrantForm] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);
  const [paymentVerifyState, setPaymentVerifyState] = useState({ status: "idle", message: "", reference: "" });

  async function load(message = "") {
    setState((current) => ({ ...current, status: "loading", message: message || "Loading payment ledger..." }));
    try {
      const result = await fetchAdminPayments();
      setState({ status: "success", message, payments: result.payments || [] });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load payments.", payments: [] });
    }
  }
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const requestedFilter = searchParams.get("filter");
    if (requestedFilter) {
      setFilter(requestedFilter);
      setPage(1);
    }
  }, [searchParams]);

  function paymentGroup(payment) {
    const hasExpiredAccess = payment.status === "verified" && !payment.access_active && Boolean(payment.access_expires_at);
    if (hasExpiredAccess) return "expired";
    if (payment.source === "admin_grant") return "grants";
    if (payment.status === "no_payment") return "no_payment";
    if (payment.status === "verified") return "verified";
    if (["initialized", "pending_verification"].includes(payment.status)) return "pending";
    return "failed";
  }

  function isPaymentToday(payment) {
    const value = payment.verified_at || payment.created_at;
    if (!value) return false;
    const date = new Date(value);
    return !Number.isNaN(date.getTime()) && date.toDateString() === new Date().toDateString();
  }

  function paymentStatusLabel(payment) {
    if (payment.source === "admin_grant") return payment.access_active ? "Manual grant active" : "Manual grant expired";
    if (payment.status === "no_payment") return "No payment";
    if (payment.status === "verified" && !payment.access_active && payment.access_expires_at) return "Verified / access expired";
    if (payment.status === "verified") return "Verified";
    if (payment.status === "amount_mismatch") return "Amount mismatch";
    if (["initialized", "pending_verification"].includes(payment.status)) return "Pending Paystack";
    return formatAction(payment.status || "failed");
  }

  function paymentStatusTone(payment) {
    if (payment.status === "verified" && payment.access_active) return "success";
    if (payment.status === "no_payment") return "neutral";
    if (payment.source === "admin_grant" && payment.access_active) return "success";
    if (["initialized", "pending_verification"].includes(payment.status)) return "warning";
    return payment.status === "verified" ? "warning" : "danger";
  }

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return state.payments.filter((payment) => {
      const matchesQuery = !normalized || [payment.patient_name, payment.patient_id, payment.email, payment.reference].some((value) => String(value || "").toLowerCase().includes(normalized));
      const matchesFilter = filter === "all" || (filter === "today" ? isPaymentToday(payment) : paymentGroup(payment) === filter);
      return matchesQuery && matchesFilter;
    });
  }, [state.payments, query, filter]);
  const visible = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const revenueSummary = useMemo(() => {
    const todayKey = new Date().toDateString();
    const isToday = (value) => {
      if (!value) return false;
      const date = new Date(value);
      return !Number.isNaN(date.getTime()) && date.toDateString() === todayKey;
    };
    const todayPayments = state.payments.filter((payment) => isToday(payment.verified_at || payment.created_at));
    const verifiedRevenueRows = todayPayments.filter((payment) => payment.source === "paystack" && payment.status === "verified");
    const currency = verifiedRevenueRows[0]?.currency || state.payments.find((payment) => payment.currency)?.currency || "NGN";
    const revenue = verifiedRevenueRows.reduce((total, payment) => total + Number(payment.amount || 0), 0);
    const pendingAttention = state.payments.filter((payment) => payment.status !== "verified" && payment.source !== "admin_grant").length;
    const manualGrantsToday = todayPayments.filter((payment) => payment.source === "admin_grant").length;
    return {
      currency,
      revenue,
      completedCount: verifiedRevenueRows.length,
      pendingAttention,
      manualGrantsToday,
    };
  }, [state.payments]);

  async function submitGrant(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await grantAdminConsultationAccess({
        patient_id: grantForm.patient_id,
        reason: grantForm.reason,
        duration_hours: Number(grantForm.duration_hours),
      });
      setGrantForm(null);
      await load(result.message);
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to grant consultation access." }));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(reference) {
    setBusy(true);
    try {
      const result = await revokeAdminConsultationAccess(reference);
      await load(result.message);
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to revoke consultation access." }));
    } finally {
      setBusy(false);
    }
  }

  async function verifyPayment(reference) {
    if (!reference) return;
    setBusy(true);
    setPaymentVerifyState({ status: "loading", message: "Checking Paystack transaction...", reference });
    try {
      const result = await verifyAdminPayment(reference);
      setPaymentVerifyState({
        status: result.verified ? "success" : "warning",
        message: result.message || (result.verified ? "Payment verified." : "Payment is not confirmed yet."),
        reference,
      });
      await load("Refreshing payment records...");
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setPaymentVerifyState({
        status: "error",
        message: error.message || "Unable to verify payment.",
        reference,
      });
    } finally {
      setBusy(false);
    }
  }

  function canDeleteAttention(payment) {
    return payment.status !== "verified" && payment.source !== "admin_grant";
  }

  async function deleteAttention(payment) {
    setBusy(true);
    try {
      const result = await deleteAdminPaymentAttention({
        reference: payment.reference || "",
        patient_id: payment.reference ? "" : payment.patient_id || "",
      });
      await load(result.message);
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to delete payment attention row." }));
    } finally {
      setBusy(false);
    }
  }

  async function clearAttention() {
    setBusy(true);
    try {
      const result = await clearAdminPaymentAttention();
      setDialog(null);
      await load(result.message);
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to clear payment attention rows." }));
    } finally {
      setBusy(false);
    }
  }

  function exportPaymentsCsv() {
    if (!filtered.length) return;
    const headers = [
      "Patient name",
      "Hospital number",
      "Email",
      "Reference",
      "Amount",
      "Currency",
      "Source",
      "Status",
      "Access",
      "Created at",
      "Verified at",
      "Access expires at",
      "Patient type",
      "Payment label",
      "Grant reason",
    ];
    const rows = filtered.map((payment) => [
      payment.patient_name,
      payment.patient_id,
      payment.email,
      payment.reference || "No payment record",
      payment.amount ?? "",
      payment.currency || "",
      payment.source === "admin_grant" ? "Manual access grant" : payment.source === "none" ? "No payment" : "Paystack",
      paymentStatusLabel(payment),
      payment.access_active ? "Can consult" : payment.access_expires_at ? "Expired" : "No access",
      payment.created_at || "",
      payment.verified_at || "",
      payment.access_expires_at || "",
      payment.patient_type || "",
      payment.label || "",
      payment.grant_reason || "",
    ]);
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const dateStamp = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `synmed-payments-${filter}-${dateStamp}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader title="Payments" actions={<><button className="button button--secondary" type="button" onClick={() => load()}>Refresh</button><button className="button button--secondary" type="button" onClick={exportPaymentsCsv} disabled={!filtered.length}>Export CSV</button><button className="button admin-button--danger" type="button" onClick={() => setDialog({ title: "Clear payment attention", message: "Clear all pending, failed, and no-payment attention rows? Verified payments and active grants will be kept.", confirmLabel: "Clear attention", danger: true })}>Clear attention</button></>} />
      <Notice state={state} />
      <section className="admin-metric-grid admin-payment-summary" aria-label="Daily payment summary">
        <article className="admin-metric">
          <span>Today revenue</span>
          <strong>{formatCurrency(revenueSummary.revenue, revenueSummary.currency)}</strong>
        </article>
        <article className="admin-metric">
          <span>Completed today</span>
          <strong>{revenueSummary.completedCount}</strong>
        </article>
        <article className="admin-metric">
          <span>Needs attention</span>
          <strong>{revenueSummary.pendingAttention}</strong>
        </article>
        <article className="admin-metric">
          <span>Manual grants today</span>
          <strong>{revenueSummary.manualGrantsToday}</strong>
        </article>
      </section>
      <DataPanel title="Payment ledger" subtitle={`${filtered.length} matching record(s)`}>
        <div className="admin-toolbar">
          <input type="search" placeholder="Search patient, hospital number, email or reference" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
          <select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1); }}>
            <option value="all">All records</option>
            <option value="today">Today</option>
            <option value="verified">Verified payments</option>
            <option value="pending">Pending Paystack</option>
            <option value="failed">Failed / mismatch</option>
            <option value="no_payment">No payment</option>
            <option value="grants">Manual access grants</option>
            <option value="expired">Expired access</option>
          </select>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Patient</th><th>Reference</th><th>Amount</th><th>Status</th><th>Access</th><th>Action</th></tr></thead>
            <tbody>{visible.map((payment, index) => (
              <tr key={payment.reference || `${payment.patient_id}-none-${index}`}>
                <td><strong>{payment.patient_name}</strong><span>{payment.patient_id || payment.email}</span></td>
                <td>{payment.reference || "No payment record"}<span>{formatDate(payment.created_at)}</span></td>
                <td>{payment.amount === null ? "N/A" : formatCurrency(payment.amount, payment.currency)}<span>{payment.source === "admin_grant" ? "Admin grant" : "Paystack"}</span></td>
                <td><StatusPill label={paymentStatusLabel(payment)} tone={paymentStatusTone(payment)} /></td>
                <td>{payment.access_active ? <StatusPill label="Can consult" tone="success" /> : <StatusPill label={payment.access_expires_at ? "Expired" : "No access"} tone="warning" />}<span>{payment.access_expires_at ? `Until ${formatDate(payment.access_expires_at)}` : ""}</span></td>
                <td>
                  <div className="admin-row-actions">
                    {payment.reference && payment.source === "paystack" ? (
                      <button type="button" disabled={busy} onClick={() => verifyPayment(payment.reference)}>
                        {paymentVerifyState.status === "loading" && paymentVerifyState.reference === payment.reference ? "Verifying..." : "Verify"}
                      </button>
                    ) : null}
                    {!payment.access_active && payment.patient_id ? <button type="button" onClick={() => setGrantForm({ patient_id: payment.patient_id, patient_name: payment.patient_name, reason: "", duration_hours: 24 })}>Grant access</button> : null}
                    {payment.source === "admin_grant" && payment.access_active ? <button type="button" disabled={busy} onClick={() => revoke(payment.reference)}>Revoke</button> : null}
                    {canDeleteAttention(payment) ? <button type="button" disabled={busy} onClick={() => deleteAttention(payment)}>Delete</button> : null}
                  </div>
                  {paymentVerifyState.reference === payment.reference && paymentVerifyState.message ? (
                    <span className={`admin-payment-verify admin-payment-verify--${paymentVerifyState.status}`}>
                      {paymentVerifyState.message}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}</tbody>
          </table>
          {!visible.length ? <EmptyState>No payment records match this view.</EmptyState> : null}
        </div>
        <Pager page={page} total={filtered.length} onChange={setPage} />
      </DataPanel>
      {grantForm ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setGrantForm(null)}>
          <form className="admin-dialog admin-form" role="dialog" aria-modal="true" onSubmit={submitGrant} onMouseDown={(event) => event.stopPropagation()}>
            <h2>Grant consultation access</h2>
            <p>Allow {grantForm.patient_name} ({grantForm.patient_id}) to proceed without a completed payment.</p>
            <label><span>Access duration</span><select value={grantForm.duration_hours} onChange={(event) => setGrantForm((current) => ({ ...current, duration_hours: event.target.value }))}><option value="1">1 hour</option><option value="6">6 hours</option><option value="12">12 hours</option><option value="24">24 hours</option><option value="48">48 hours</option><option value="168">7 days</option></select></label>
            <label><span>Reason</span><textarea required rows="3" value={grantForm.reason} onChange={(event) => setGrantForm((current) => ({ ...current, reason: event.target.value }))} /></label>
            <div className="admin-dialog__actions"><button className="button button--secondary" type="button" onClick={() => setGrantForm(null)}>Cancel</button><button className="button button--primary" type="submit" disabled={busy}>{busy ? "Granting..." : "Grant access"}</button></div>
          </form>
        </div>
      ) : null}
      <ConfirmDialog dialog={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={clearAttention} />
    </>
  );
}

export function AdminReportsPage() {
  const [searchParams] = useSearchParams();
  const [state, setState] = useState({ status: "loading", message: "Loading medical reports...", requests: [], doctors: [] });
  const [filter, setFilter] = useState(searchParams.get("filter") || "all");
  const [assignments, setAssignments] = useState({});
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading medical report requests..." }));
    try {
      const [reports, summary] = await Promise.all([fetchAdminMedicalReportRequests(), fetchAdminSummary()]);
      setState({ status: "success", message: "", requests: reports.requests || [], doctors: summary.verified_doctor_records || [] });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load medical reports.", requests: [], doctors: [] });
    }
  }
  useEffect(() => { load(); }, []);

  const requests = state.requests.filter((request) =>
    filter === "all" || (filter === "unassigned" ? !request.doctor_id : request.payment_status === filter || request.status === filter)
  );

  function getDoctorLabel(doctorId) {
    if (!doctorId) return "Unassigned";
    const doctor = state.doctors.find((item) => String(item.telegram_id) === String(doctorId));
    return doctor?.name ? `${doctor.name} (${doctorId})` : `Doctor ${doctorId}`;
  }

  async function confirmAssignment() {
    setBusy(true);
    try {
      await assignAdminMedicalReportRequest(dialog.request.request_id, dialog.doctorId);
      setDialog(null);
      await load();
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to assign report." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Medical reports" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Report requests" subtitle={`${requests.length} matching request(s)`}>
        <div className="admin-toolbar">
          <select value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All requests</option>
            <option value="unassigned">Unassigned</option>
            <option value="paid">Paid</option>
            <option value="unpaid">Unpaid</option>
            <option value="fulfilled">Fulfilled</option>
          </select>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Request</th><th>Patient</th><th>Payment</th><th>Status</th><th>Doctor assignment</th></tr></thead>
            <tbody>{requests.map((request) => (
              <tr key={request.request_id}>
                <td><strong>{request.request_id}</strong><span>{formatDate(request.created_at)}</span></td>
                <td>{request.patient_id}<span>{request.request_note || "No note"}</span></td>
                <td><StatusPill label={request.payment_status} tone={request.payment_status === "paid" ? "success" : "warning"} /></td>
                <td>{request.status}</td>
                <td>
                  {request.doctor_id ? (
                    <div className="admin-assignment admin-assignment--readonly">
                      <strong>{getDoctorLabel(request.doctor_id)}</strong>
                      <span>Auto-assigned from latest consultation</span>
                    </div>
                  ) : (
                    <div className="admin-assignment">
                      <select value={assignments[request.request_id] ?? ""} onChange={(event) => setAssignments((current) => ({ ...current, [request.request_id]: event.target.value }))}>
                        <option value="">Select doctor</option>
                        {state.doctors.map((doctor) => <option key={doctor.telegram_id} value={doctor.telegram_id}>{doctor.name}</option>)}
                      </select>
                      <button type="button" disabled={!assignments[request.request_id]} onClick={() => {
                        const doctorId = assignments[request.request_id];
                        const doctor = state.doctors.find((item) => String(item.telegram_id) === String(doctorId));
                        setDialog({
                          request,
                          doctorId,
                          title: "Assign medical report",
                          message: `Assign ${request.request_id} to ${doctor?.name || `doctor ${doctorId}`}?`,
                          confirmLabel: "Assign",
                        });
                      }}>Assign</button>
                    </div>
                  )}
                </td>
              </tr>
            ))}</tbody>
          </table>
          {!requests.length ? <EmptyState>No medical report requests match this view.</EmptyState> : null}
        </div>
      </DataPanel>
      <ConfirmDialog dialog={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={confirmAssignment} />
    </>
  );
}

export function AdminPartnersPage() {
  const blankForm = {
    name: "",
    partner_type: "pharmacy",
    email: "",
    phone: "",
    address: "",
    contact_person: "",
    status: "pending",
    notes: "",
  };
  const [state, setState] = useState({ status: "loading", message: "Loading partners...", partners: [], summary: null });
  const [form, setForm] = useState(blankForm);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState("");

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading partner facilities..." }));
    try {
      const result = await fetchAdminPartners();
      setState({ status: "success", message: "", partners: result.partners || [], summary: result.summary || null });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load partners.", partners: [], summary: null });
    }
  }

  useEffect(() => { load(); }, []);

  const filteredPartners = state.partners.filter((partner) => {
    const matchesFilter =
      filter === "all" || partner.partner_type === filter || partner.status === filter;
    const haystack = `${partner.name} ${partner.email} ${partner.phone} ${partner.address} ${partner.contact_person}`.toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  });

  async function save(event) {
    event.preventDefault();
    setBusy("create");
    try {
      await createAdminPartner(form);
      setForm(blankForm);
      await load();
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to create partner." }));
    } finally {
      setBusy("");
    }
  }

  async function changeStatus(partner, status) {
    setBusy(`${partner.partner_id}:${status}`);
    try {
      await updateAdminPartnerStatus(partner.partner_id, status);
      await load();
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to update partner status." }));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageHeader title="Partners" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <div className="admin-metric-grid">
        <article className="admin-metric"><span>Total partners</span><strong>{state.summary?.total || 0}</strong></article>
        <article className="admin-metric"><span>Active</span><strong>{state.summary?.active || 0}</strong></article>
        <article className="admin-metric"><span>Pending</span><strong>{state.summary?.pending || 0}</strong></article>
        <article className="admin-metric"><span>Suspended</span><strong>{state.summary?.suspended || 0}</strong></article>
      </div>
      <div className="admin-two-column admin-two-column--content">
        <DataPanel title="New partner facility">
          <form className="admin-form" onSubmit={save}>
            <label><span>Name</span><input required value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} /></label>
            <div className="admin-form__row">
              <label><span>Partner type</span><select value={form.partner_type} onChange={(event) => setForm((current) => ({ ...current, partner_type: event.target.value }))}><option value="pharmacy">Pharmacy</option><option value="laboratory">Laboratory</option></select></label>
              <label><span>Status</span><select value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value }))}><option value="pending">Pending</option><option value="active">Active</option><option value="suspended">Suspended</option></select></label>
            </div>
            <div className="admin-form__row">
              <label><span>Email</span><input type="email" value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} /></label>
              <label><span>Phone</span><input value={form.phone} onChange={(event) => setForm((current) => ({ ...current, phone: event.target.value }))} /></label>
            </div>
            <label><span>Contact person</span><input value={form.contact_person} onChange={(event) => setForm((current) => ({ ...current, contact_person: event.target.value }))} /></label>
            <label><span>Address</span><textarea rows="2" value={form.address} onChange={(event) => setForm((current) => ({ ...current, address: event.target.value }))} /></label>
            <label><span>Notes</span><textarea rows="3" value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} /></label>
            <button className="button button--primary" type="submit" disabled={busy === "create"}>{busy === "create" ? "Saving..." : "Add partner"}</button>
          </form>
        </DataPanel>
        <DataPanel title="Partner directory" subtitle={`${filteredPartners.length} matching partner(s)`}>
          <div className="admin-toolbar">
            <input type="search" placeholder="Search partner, contact, phone, email, or address" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">All</option>
              <option value="pharmacy">Pharmacies</option>
              <option value="laboratory">Laboratories</option>
              <option value="active">Active</option>
              <option value="pending">Pending</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead><tr><th>Partner</th><th>Type</th><th>Contact</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>{filteredPartners.map((partner) => (
                <tr key={partner.partner_id}>
                  <td><strong>{partner.name}</strong><span>{partner.address || partner.partner_id}</span></td>
                  <td>{formatAction(partner.partner_type)}</td>
                  <td>{partner.contact_person || "N/A"}<span>{partner.email || partner.phone || "No contact saved"}</span></td>
                  <td><StatusPill label={partner.status} tone={partner.status === "active" ? "success" : partner.status === "suspended" ? "danger" : "warning"} /></td>
                  <td>
                    <div className="admin-row-actions">
                      {partner.status !== "active" ? <button type="button" disabled={Boolean(busy)} onClick={() => changeStatus(partner, "active")}>Activate</button> : null}
                      {partner.status !== "suspended" ? <button type="button" disabled={Boolean(busy)} onClick={() => changeStatus(partner, "suspended")}>Suspend</button> : null}
                      {partner.status !== "pending" ? <button type="button" disabled={Boolean(busy)} onClick={() => changeStatus(partner, "pending")}>Mark pending</button> : null}
                    </div>
                  </td>
                </tr>
              ))}</tbody>
            </table>
            {!filteredPartners.length ? <EmptyState>No partner facilities match this view.</EmptyState> : null}
          </div>
        </DataPanel>
      </div>
    </>
  );
}

export function AdminContentPage() {
  const blankForm = { id: null, eyebrow: "Health Tip", title: "", body: "", sort_order: 0, is_active: true, audience: "landing" };
  const [state, setState] = useState({ status: "loading", message: "Loading content...", tips: [] });
  const [form, setForm] = useState(blankForm);
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading health tips..." }));
    try {
      const result = await fetchAdminHealthTips();
      setState({ status: "success", message: "", tips: result.tips || [] });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load health tips.", tips: [] });
    }
  }
  useEffect(() => { load(); }, []);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    try {
      if (form.id) await updateAdminHealthTip(form.id, form);
      else await createAdminHealthTip(form);
      setForm(blankForm);
      await load();
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to save health tip." }));
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    setBusy(true);
    try {
      await deleteAdminHealthTip(dialog.tip.id);
      if (form.id === dialog.tip.id) setForm(blankForm);
      setDialog(null);
      await load();
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to delete health tip." }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Content" />
      <Notice state={state} />
      <div className="admin-two-column admin-two-column--content">
        <DataPanel title={form.id ? "Edit health tip" : "New health tip"}>
          <form className="admin-form" onSubmit={save}>
            <label><span>Eyebrow</span><input required value={form.eyebrow} onChange={(event) => setForm((current) => ({ ...current, eyebrow: event.target.value }))} /></label>
            <label><span>Title</span><input required value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} /></label>
            <label><span>Body</span><textarea required rows="5" value={form.body} onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))} /></label>
            <label><span>Audience</span><select value={form.audience} onChange={(event) => setForm((current) => ({ ...current, audience: event.target.value }))}><option value="landing">Landing page</option><option value="patient">Patient dashboard</option><option value="both">Both</option></select></label>
            <div className="admin-form__row">
              <label><span>Sort order</span><input type="number" value={form.sort_order} onChange={(event) => setForm((current) => ({ ...current, sort_order: Number(event.target.value) }))} /></label>
              <label><span>Visibility</span><select value={form.is_active ? "active" : "hidden"} onChange={(event) => setForm((current) => ({ ...current, is_active: event.target.value === "active" }))}><option value="active">Active</option><option value="hidden">Hidden</option></select></label>
            </div>
            <div className="admin-form__actions">
              <button className="button button--primary" type="submit" disabled={busy}>{form.id ? "Update tip" : "Add tip"}</button>
              {form.id ? <button className="button button--secondary" type="button" onClick={() => setForm(blankForm)}>Cancel</button> : null}
            </div>
          </form>
        </DataPanel>
        <DataPanel title="Published tips" subtitle={`${state.tips.length} total tip(s)`}>
          <div className="admin-content-list">
            {state.tips.map((tip) => (
              <article key={tip.id}>
                <div>
                  <strong>{tip.title}</strong>
                  <p>{tip.body}</p>
                  <span>{formatAction(tip.audience || "landing")} / Order {tip.sort_order} / {tip.is_active ? "Active" : "Hidden"}</span>
                </div>
                <div className="admin-row-actions">
                  <button type="button" onClick={() => setForm({ ...tip })}>Edit</button>
                  <button type="button" onClick={() => setDialog({ tip, title: "Delete health tip", message: `Permanently delete "${tip.title}"?`, confirmLabel: "Delete", danger: true })}>Delete</button>
                </div>
              </article>
            ))}
            {!state.tips.length ? <EmptyState>No health tips created yet.</EmptyState> : null}
          </div>
        </DataPanel>
      </div>
      <ConfirmDialog dialog={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={confirmDelete} />
    </>
  );
}

export function AdminRatingsPage() {
  const [state, setState] = useState({
    status: "loading",
    message: "Loading ratings...",
    summary: null,
    doctorSummaries: [],
    doctorRatings: [],
    supportAgentSummaries: [],
    supportFeedback: [],
  });
  const [ratingQuery, setRatingQuery] = useState("");
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading ratings..." }));
    try {
      const result = await fetchAdminRatings();
      setState({
        status: "success",
        message: "",
        summary: result.summary || {},
        doctorSummaries: result.doctor_summaries || [],
        doctorRatings: result.doctor_ratings || [],
        supportAgentSummaries: result.support_agent_summaries || [],
        supportFeedback: result.support_feedback || [],
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to load ratings.",
      }));
    }
  }

  useEffect(() => { load(); }, []);

  const filteredDoctorSummaries = useMemo(() => {
    const normalized = ratingQuery.trim().toLowerCase();
    return state.doctorSummaries.filter((item) => {
      if (!normalized) return true;
      return [item.doctor_name, item.specialty, item.doctor_id]
        .some((value) => String(value || "").toLowerCase().includes(normalized));
    });
  }, [ratingQuery, state.doctorSummaries]);

  const filteredAgentSummaries = useMemo(() => {
    const normalized = ratingQuery.trim().toLowerCase();
    return state.supportAgentSummaries.filter((item) => {
      if (!normalized) return true;
      return [item.agent_name, item.agent_id]
        .some((value) => String(value || "").toLowerCase().includes(normalized));
    });
  }, [ratingQuery, state.supportAgentSummaries]);

  const selectedDoctorRatings = selectedDoctor
    ? state.doctorRatings.filter((rating) => String(rating.doctor_id) === String(selectedDoctor.doctor_id))
    : [];
  const selectedAgentFeedback = selectedAgent
    ? state.supportFeedback.filter((feedback) => String(feedback.agent_id || "unassigned") === String(selectedAgent.agent_id))
    : [];

  const metrics = [
    ["Doctor average", state.summary?.doctor_average ? `${state.summary.doctor_average}/5` : "0/5"],
    ["Doctor ratings", state.summary?.doctor_rating_count ?? 0],
    ["Rated doctors", state.summary?.rated_doctors ?? 0],
    ["Support average", state.summary?.support_average ? `${state.summary.support_average}/5` : "0/5"],
    ["Support ratings", state.summary?.support_feedback_count ?? 0],
    ["Skipped support reviews", state.summary?.support_skipped_count ?? 0],
  ];

  return (
    <>
      <PageHeader title="Ratings" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <section className="admin-metric-grid">
        {metrics.map(([label, value]) => (
          <article className="admin-metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </section>

      <DataPanel title="Search ratings" subtitle="Find a doctor or customer-care agent quickly.">
        <div className="admin-toolbar">
          <input
            type="search"
            placeholder="Search doctor, specialty, customer-care agent, or ID"
            value={ratingQuery}
            onChange={(event) => setRatingQuery(event.target.value)}
          />
        </div>
      </DataPanel>

      <div className="admin-two-column">
        <DataPanel title="Doctors rating summary" subtitle={`${filteredDoctorSummaries.length} matching doctor(s)`}>
          <div className="admin-content-list">
            {filteredDoctorSummaries.map((doctor) => (
              <button className="admin-rating-summary-button" key={doctor.doctor_id} type="button" onClick={() => setSelectedDoctor(doctor)}>
                <div>
                  <strong>{doctor.doctor_name}</strong>
                  <p>{doctor.specialty || "N/A"}</p>
                  <span>Last rating: {formatDate(doctor.last_rating_at)}</span>
                </div>
                <div>
                  <RatingStars value={doctor.average_rating} />
                  <strong>{Number(doctor.average_rating || 0).toFixed(2)} / 5</strong>
                  <span>{doctor.rating_count} rating(s)</span>
                </div>
              </button>
            ))}
            {!filteredDoctorSummaries.length ? <EmptyState>No doctor ratings match this search.</EmptyState> : null}
          </div>
        </DataPanel>

        <DataPanel title="Customer-care rating summary" subtitle={`${filteredAgentSummaries.length} matching agent(s)`}>
          <div className="admin-content-list">
            {filteredAgentSummaries.map((agent) => (
              <button className="admin-rating-summary-button" key={agent.agent_id} type="button" onClick={() => setSelectedAgent(agent)}>
                <div>
                  <strong>{agent.agent_name}</strong>
                  <p>Customer-care agent</p>
                  <span>Last feedback: {formatDate(agent.last_feedback_at)}</span>
                </div>
                <div>
                  <RatingStars value={agent.average_rating} />
                  <strong>{Number(agent.average_rating || 0).toFixed(2)} / 5</strong>
                  <span>{agent.rating_count} rating(s) / {agent.skipped_count} skipped</span>
                </div>
              </button>
            ))}
            {!filteredAgentSummaries.length ? <EmptyState>No customer-care agent ratings match this search.</EmptyState> : null}
          </div>
        </DataPanel>
      </div>

      {selectedDoctor ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedDoctor(null)}>
          <section className="admin-record-card admin-rating-detail-card" role="dialog" aria-modal="true" aria-labelledby="doctor-rating-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Doctor rating details</span>
                <h2 id="doctor-rating-title">{selectedDoctor.doctor_name}</h2>
                <p>{selectedDoctor.specialty || "N/A"} / {Number(selectedDoctor.average_rating || 0).toFixed(2)} out of 5</p>
              </div>
              <button type="button" onClick={() => setSelectedDoctor(null)}>Close</button>
            </header>
            <div className="admin-rating-detail-list">
              {selectedDoctorRatings.map((rating) => (
                <article key={rating.id}>
                  <div>
                    <strong>{rating.patient_name}</strong>
                    <span>{rating.consultation_id} / {formatDate(rating.created_at)}</span>
                  </div>
                  <div>
                    <RatingStars value={rating.rating} />
                    <span>{rating.rating}/5</span>
                  </div>
                  <p>{rating.review || "No written review"}</p>
                </article>
              ))}
              {!selectedDoctorRatings.length ? <EmptyState>No detail records are available for this doctor.</EmptyState> : null}
            </div>
          </section>
        </div>
      ) : null}

      {selectedAgent ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedAgent(null)}>
          <section className="admin-record-card admin-rating-detail-card" role="dialog" aria-modal="true" aria-labelledby="support-rating-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Customer-care rating details</span>
                <h2 id="support-rating-title">{selectedAgent.agent_name}</h2>
                <p>{Number(selectedAgent.average_rating || 0).toFixed(2)} out of 5 / {selectedAgent.rating_count} rating(s)</p>
              </div>
              <button type="button" onClick={() => setSelectedAgent(null)}>Close</button>
            </header>
            <div className="admin-rating-detail-list">
              {selectedAgentFeedback.map((feedback) => (
                <article key={feedback.id}>
                  <div>
                    <strong>{feedback.patient_name || feedback.contact_email || "Patient"}</strong>
                    <span>{feedback.ticket_id} / {feedback.topic || "Support ticket"} / {formatDate(feedback.created_at)}</span>
                  </div>
                  <div>
                    {feedback.skipped ? <StatusPill label="skipped" tone="warning" /> : <RatingStars value={feedback.rating} />}
                    {!feedback.skipped ? <span>{feedback.rating}/5</span> : null}
                  </div>
                  <p>{feedback.review || (feedback.skipped ? "Patient skipped review" : "No written review")}</p>
                </article>
              ))}
              {!selectedAgentFeedback.length ? <EmptyState>No detail records are available for this agent.</EmptyState> : null}
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

export function AdminSettingsPage() {
  const [state, setState] = useState({ status: "loading", message: "Checking delivery settings...", settings: null });
  const [activeSettingsPanel, setActiveSettingsPanel] = useState("payments");
  const [form, setForm] = useState({ channel: "email", target: "" });
  const [paymentForm, setPaymentForm] = useState({
    new_patient_fee: 3000,
    returning_patient_fee: 2000,
    followup_fee: 2000,
    medical_report_fee: 5000,
    new_patient_label: "",
    returning_patient_label: "",
    followup_label: "",
    medical_report_label: "",
  });
  const [emailBrandingForm, setEmailBrandingForm] = useState({
    brand_name: "SynMed Telehealth",
    logo_url: "",
    support_address: "",
    footer_text: "",
  });
  const [dialog, setDialog] = useState(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Checking delivery settings..." }));
    try {
      const [settings, backupStatus, reminderStatus] = await Promise.all([
        fetchAdminDeliverySettings(),
        fetchAdminBackupStatus(),
        fetchAdminEmailReminders(),
      ]);
      settings.backups = backupStatus;
      settings.reminders = reminderStatus.reminders || [];
      setState({ status: "success", message: "", settings });
      if (settings.payments) {
        setPaymentForm({
          new_patient_fee: settings.payments.new_patient_fee || 3000,
          returning_patient_fee: settings.payments.returning_patient_fee || 2000,
          followup_fee: settings.payments.followup_fee || 2000,
          medical_report_fee: settings.payments.medical_report_fee || 5000,
          new_patient_label: settings.payments.new_patient_label || "",
          returning_patient_label: settings.payments.returning_patient_label || "",
          followup_label: settings.payments.followup_label || "",
          medical_report_label: settings.payments.medical_report_label || "",
        });
      }
      if (settings.email_branding) {
        setEmailBrandingForm({
          brand_name: settings.email_branding.brand_name || "SynMed Telehealth",
          logo_url: settings.email_branding.logo_url || "",
          support_address: settings.email_branding.support_address || "",
          footer_text: settings.email_branding.footer_text || "",
        });
      }
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load delivery settings.", settings: null });
    }
  }
  useEffect(() => { load(); }, []);

  async function confirmTest() {
    setBusy(true);
    try {
      const result = await testAdminDelivery(form.channel, form.target);
      setDialog(null);
      setState((current) => ({ ...current, status: "success", message: result.message }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Delivery test failed." }));
    } finally {
      setBusy(false);
    }
  }

  async function savePaymentSettings(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await updateAdminPaymentSettings({
        new_patient_fee: Number(paymentForm.new_patient_fee),
        returning_patient_fee: Number(paymentForm.returning_patient_fee),
        followup_fee: Number(paymentForm.followup_fee),
        medical_report_fee: Number(paymentForm.medical_report_fee),
        new_patient_label: paymentForm.new_patient_label,
        returning_patient_label: paymentForm.returning_patient_label,
        followup_label: paymentForm.followup_label,
        medical_report_label: paymentForm.medical_report_label,
      });
      setState((current) => ({
        ...current,
        status: "success",
        message: result.message || "Payment settings updated.",
        settings: {
          ...(current.settings || {}),
          payments: result.payments,
        },
      }));
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to save payment settings." }));
    } finally {
      setBusy(false);
    }
  }

  async function saveEmailBranding(event) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await updateAdminEmailBranding(emailBrandingForm);
      setState((current) => ({
        ...current,
        status: "success",
        message: result.message || "Email branding settings updated.",
        settings: {
          ...(current.settings || {}),
          email_branding: result.email_branding,
        },
      }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to save email branding." }));
    } finally {
      setBusy(false);
    }
  }

  async function downloadBackup(kind) {
    setBusy(true);
    try {
      const result = await downloadAdminBackup(kind);
      const backupStatus = await fetchAdminBackupStatus();
      setState((current) => ({
        ...current,
        status: "success",
        message: `${result.filename} downloaded.`,
        settings: {
          ...(current.settings || {}),
          backups: backupStatus,
        },
      }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to create backup." }));
    } finally {
      setBusy(false);
    }
  }

  async function sendReminderTest() {
    setBusy(true);
    try {
      const result = await sendAdminReminderTest();
      const reminderStatus = await fetchAdminEmailReminders();
      setState((current) => ({
        ...current,
        status: "success",
        message: `${result.message} Delivery target: ${result.delivery_target}`,
        settings: {
          ...(current.settings || {}),
          reminders: reminderStatus.reminders || [],
        },
      }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to send reminder test." }));
    } finally {
      setBusy(false);
    }
  }

  const settingsPanels = [
    { id: "payments", label: "Payment values" },
    { id: "readiness", label: "System readiness" },
    { id: "backups", label: "Backups" },
    { id: "reminders", label: "Reminders" },
    { id: "email", label: "Email branding" },
    { id: "test", label: "Delivery test" },
  ];

  return (
    <>
      <PageHeader title="Settings" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh status</button>} />
      <Notice state={state} />
      <nav className="admin-settings-nav" aria-label="Settings sections">
        {settingsPanels.map((panel) => (
          <button
            className={activeSettingsPanel === panel.id ? "admin-settings-nav__link admin-settings-nav__link--active" : "admin-settings-nav__link"}
            key={panel.id}
            type="button"
            onClick={() => setActiveSettingsPanel(panel.id)}
          >
            {panel.label}
          </button>
        ))}
      </nav>
      <div className="admin-settings-panel">
        {activeSettingsPanel === "payments" ? (
        <DataPanel title="Consultation payment">
          <form className="admin-form admin-settings-payment-form" onSubmit={savePaymentSettings}>
            <label><span>New patient fee ({state.settings?.payments?.currency || "NGN"})</span><input required min="1" type="number" value={paymentForm.new_patient_fee} onChange={(event) => setPaymentForm((current) => ({ ...current, new_patient_fee: event.target.value }))} /></label>
            <label><span>Returning patient fee ({state.settings?.payments?.currency || "NGN"})</span><input required min="1" type="number" value={paymentForm.returning_patient_fee} onChange={(event) => setPaymentForm((current) => ({ ...current, returning_patient_fee: event.target.value }))} /></label>
            <label><span>Follow-up booking fee ({state.settings?.payments?.currency || "NGN"})</span><input required min="1" type="number" value={paymentForm.followup_fee} onChange={(event) => setPaymentForm((current) => ({ ...current, followup_fee: event.target.value }))} /></label>
            <label><span>Medical report fee ({state.settings?.payments?.currency || "NGN"})</span><input required min="1" type="number" value={paymentForm.medical_report_fee} onChange={(event) => setPaymentForm((current) => ({ ...current, medical_report_fee: event.target.value }))} /></label>
            <label><span>New patient payment label</span><input required value={paymentForm.new_patient_label} onChange={(event) => setPaymentForm((current) => ({ ...current, new_patient_label: event.target.value }))} /></label>
            <label><span>Returning patient payment label</span><input required value={paymentForm.returning_patient_label} onChange={(event) => setPaymentForm((current) => ({ ...current, returning_patient_label: event.target.value }))} /></label>
            <label><span>Follow-up payment label</span><input required value={paymentForm.followup_label} onChange={(event) => setPaymentForm((current) => ({ ...current, followup_label: event.target.value }))} /></label>
            <label><span>Medical report payment label</span><input required value={paymentForm.medical_report_label} onChange={(event) => setPaymentForm((current) => ({ ...current, medical_report_label: event.target.value }))} /></label>
            <button className="button button--primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save payment settings"}</button>
          </form>
        </DataPanel>
        ) : null}
        {activeSettingsPanel === "readiness" ? (
        <DataPanel title="Delivery readiness">
          <div className="admin-delivery-list">
            {["email", "telegram"].map((channel) => (
              <article key={channel}>
                <div><strong>{state.settings?.[channel]?.label || formatAction(channel)}</strong><p>{state.settings?.[channel]?.message || "Checking configuration..."}</p></div>
                <StatusPill label={state.settings?.[channel]?.ready ? "Ready" : "Setup needed"} tone={state.settings?.[channel]?.ready ? "success" : "warning"} />
              </article>
            ))}
            <article>
              <div><strong>{state.settings?.paystack?.label || "Paystack"}</strong><p>{state.settings?.paystack?.message || "Checking payment gateway..."}</p></div>
              <StatusPill label={state.settings?.paystack?.ready ? "Ready" : "Setup needed"} tone={state.settings?.paystack?.ready ? "success" : "warning"} />
            </article>
          </div>
        </DataPanel>
        ) : null}
        {activeSettingsPanel === "backups" ? (
        <DataPanel title="Backups" subtitle="Download the production database or a full archive that also includes generated documents, chat uploads, and licence files.">
          <div className="admin-delivery-list">
            <article>
              <div>
                <strong>Database</strong>
                <p>
                  {state.settings?.backups?.database_provider === "postgresql"
                    ? "PostgreSQL connection is active. Database downloads export SynMed table data as JSON."
                    : state.settings?.backups?.database_exists ? `${formatBytes(state.settings.backups.database_size)} at ${state.settings.backups.database_path}` : "Database file not found."}
                </p>
              </div>
              <StatusPill label={state.settings?.backups?.database_provider === "postgresql" ? "PostgreSQL" : state.settings?.backups?.database_exists ? "Ready" : "Missing"} tone={state.settings?.backups?.database_exists ? "success" : "warning"} />
            </article>
            <article>
              <div>
                <strong>Stored files</strong>
                <p>{state.settings?.backups?.storage_exists ? `${state.settings.backups.storage_file_count || 0} file(s), ${formatBytes(state.settings.backups.storage_total_size)} at ${state.settings.backups.storage_root}` : "Storage folder not found."}</p>
              </div>
              <StatusPill label={state.settings?.backups?.storage_exists ? "Ready" : "Missing"} tone={state.settings?.backups?.storage_exists ? "success" : "warning"} />
            </article>
            <article>
              <div>
                <strong>Latest backup</strong>
                <p>{state.settings?.backups?.latest_backup ? `${state.settings.backups.latest_backup.filename} / ${formatBytes(state.settings.backups.latest_backup.size)} / ${formatDate(state.settings.backups.latest_backup.created_at)}` : "No backup created yet."}</p>
              </div>
              <StatusPill label={state.settings?.backups?.latest_backup ? "Available" : "None"} tone={state.settings?.backups?.latest_backup ? "success" : "warning"} />
            </article>
          </div>
          <div className="admin-settings-actions">
            <button className="button button--secondary" type="button" disabled={busy || state.settings?.backups?.database_backup_supported === false} onClick={() => downloadBackup("database")}>
              {busy ? "Preparing..." : state.settings?.backups?.database_provider === "postgresql" ? "Download database JSON" : "Download database"}
            </button>
            <button className="button button--primary" type="button" disabled={busy || state.settings?.backups?.database_backup_supported === false} onClick={() => downloadBackup("full")}>
              {busy ? "Preparing..." : "Download full backup"}
            </button>
          </div>
        </DataPanel>
        ) : null}
        {activeSettingsPanel === "reminders" ? (
        <DataPanel title="Admin email reminders">
          <div className="admin-settings-actions admin-settings-actions--top">
            <button className="button button--primary" type="button" disabled={busy} onClick={sendReminderTest}>
              {busy ? "Sending..." : "Send reminder test"}
            </button>
            <button className="button button--secondary" type="button" disabled={busy} onClick={async () => {
              setBusy(true);
              try {
                const reminderStatus = await fetchAdminEmailReminders();
                setState((current) => ({
                  ...current,
                  status: "success",
                  message: "Reminder history refreshed.",
                  settings: {
                    ...(current.settings || {}),
                    reminders: reminderStatus.reminders || [],
                  },
                }));
              } catch (error) {
                setState((current) => ({ ...current, status: "error", message: error.message || "Unable to refresh reminder history." }));
              } finally {
                setBusy(false);
              }
            }}>
              Refresh reminders
            </button>
          </div>
          <div className="admin-delivery-list">
            {(state.settings?.reminders || []).map((reminder) => (
              <article key={reminder.reminder_key}>
                <div>
                  <strong>{formatAction(reminder.reminder_key.replace(/^admin-alert-/, "").replace(/^manual-test-admin-/, "manual test "))}</strong>
                  <p>Last sent: {formatDate(reminder.sent_at)}</p>
                  {reminder.details?.sent_count ? <p>Delivered to {reminder.details.sent_count} admin email(s).</p> : null}
                  {reminder.details?.failed?.length ? <p>Failed: {reminder.details.failed.join(", ")}</p> : null}
                </div>
                <StatusPill label={reminder.reminder_key.includes("test") ? "Test" : "Active"} tone={reminder.reminder_key.includes("test") ? "neutral" : "success"} />
              </article>
            ))}
            {!state.settings?.reminders?.length ? (
              <article>
                <div>
                  <strong>No reminder emails sent yet</strong>
                  <p>Use the test button to confirm delivery or wait for a real admin alert.</p>
                </div>
                <StatusPill label="Empty" tone="warning" />
              </article>
            ) : null}
          </div>
        </DataPanel>
        ) : null}
        {activeSettingsPanel === "email" ? (
        <DataPanel title="Email branding">
          <form className="admin-form admin-settings-payment-form" onSubmit={saveEmailBranding}>
            <label><span>Brand name</span><input required value={emailBrandingForm.brand_name} onChange={(event) => setEmailBrandingForm((current) => ({ ...current, brand_name: event.target.value }))} /></label>
            <label><span>Logo URL</span><input type="url" placeholder="https://..." value={emailBrandingForm.logo_url} onChange={(event) => setEmailBrandingForm((current) => ({ ...current, logo_url: event.target.value }))} /></label>
            <label><span>Support email</span><input type="email" value={emailBrandingForm.support_address} onChange={(event) => setEmailBrandingForm((current) => ({ ...current, support_address: event.target.value }))} /></label>
            <label><span>Footer text</span><textarea rows="3" value={emailBrandingForm.footer_text} onChange={(event) => setEmailBrandingForm((current) => ({ ...current, footer_text: event.target.value }))} /></label>
            <button className="button button--primary" type="submit" disabled={busy}>{busy ? "Saving..." : "Save email branding"}</button>
          </form>
        </DataPanel>
        ) : null}
        {activeSettingsPanel === "test" ? (
        <DataPanel title="Send delivery test" subtitle="The test sends OTP code 123456 to the selected destination.">
          <form className="admin-form" onSubmit={(event) => {
            event.preventDefault();
            setDialog({ title: "Send delivery test", message: `Send a test OTP via ${form.channel} to ${form.target}?`, confirmLabel: "Send test" });
          }}>
            <label><span>Channel</span><select value={form.channel} onChange={(event) => setForm((current) => ({ ...current, channel: event.target.value, target: "" }))}><option value="email">Email</option><option value="telegram">Telegram</option></select></label>
            <label><span>{form.channel === "email" ? "Email address" : "Telegram ID"}</span><input required type={form.channel === "email" ? "email" : "text"} value={form.target} onChange={(event) => setForm((current) => ({ ...current, target: event.target.value }))} /></label>
            <button className="button button--primary" type="submit">Send test</button>
          </form>
        </DataPanel>
        ) : null}
      </div>
      <ConfirmDialog dialog={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={confirmTest} />
    </>
  );
}

export function AdminInboxPage() {
  const [state, setState] = useState({ status: "loading", message: "Loading inbox...", messages: [], doctors: [], customerCare: [] });
  const [form, setForm] = useState({ recipient: "", subject: "", body: "" });
  const [composerOpen, setComposerOpen] = useState(false);

  async function load(message = "") {
    setState((current) => ({ ...current, status: "loading", message: message || "Loading inbox..." }));
    try {
      const result = await fetchAdminMail();
      setState({ status: "success", message: "", messages: result.messages || [], doctors: result.doctors || [], customerCare: result.customer_care || [] });
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to load admin inbox." }));
    }
  }
  useEffect(() => { load(); }, []);

  async function send(event) {
    event.preventDefault();
    try {
      const [recipientRole, recipientId] = form.recipient.split(":");
      await sendAdminMail({
        recipient_role: recipientRole,
        recipient_id: recipientId,
        recipient_doctor_id: recipientRole === "doctor" ? Number(recipientId) : undefined,
        subject: form.subject,
        body: form.body,
      });
      setForm({ recipient: "", subject: "", body: "" });
      setComposerOpen(false);
      await load();
      window.dispatchEvent(new Event("synmed:admin-mail-updated"));
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to send message." }));
    }
  }

  async function markRead(message) {
    if (message.read_at) return;
    try {
      await markAdminMailRead(message.id);
      setState((current) => ({ ...current, messages: current.messages.map((item) => item.id === message.id ? { ...item, read_at: new Date().toISOString() } : item) }));
      window.dispatchEvent(new Event("synmed:admin-mail-updated"));
    } catch {}
  }

  return (
    <>
      <PageHeader title="Inbox" actions={<button className="button button--primary" type="button" onClick={() => setComposerOpen((current) => !current)}>New message</button>} />
      <Notice state={state} />
      {composerOpen ? (
        <DataPanel title="Message a doctor or customer-care agent">
          <form className="admin-form" onSubmit={send}>
            <label><span>Recipient</span><select required value={form.recipient} onChange={(event) => setForm((current) => ({ ...current, recipient: event.target.value }))}>
              <option value="">Select recipient</option>
              <optgroup label="Doctors">{state.doctors.map((doctor) => <option key={`doctor-${doctor.telegram_id}`} value={`doctor:${doctor.telegram_id}`}>{doctor.name} / {doctor.specialty}</option>)}</optgroup>
              <optgroup label="Customer care">{state.customerCare.map((account) => <option key={`support-${account.account_id}`} value={`customer_care:${account.account_id}`}>{account.display_name}</option>)}</optgroup>
            </select></label>
            <label><span>Subject</span><input required value={form.subject} onChange={(event) => setForm((current) => ({ ...current, subject: event.target.value }))} /></label>
            <label><span>Message</span><textarea rows="4" value={form.body} onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))} /></label>
            <button className="button button--primary" type="submit">Send message</button>
          </form>
        </DataPanel>
      ) : null}
      <DataPanel title="Messages" subtitle={`${state.messages.filter((message) => !message.read_at).length} unread`}>
        <div className="admin-inbox">
          {state.messages.map((message) => (
            <details className={message.read_at ? "admin-inbox__message" : "admin-inbox__message admin-inbox__message--unread"} key={message.id} onToggle={(event) => event.currentTarget.open && markRead(message)}>
              <summary><div><strong>{message.subject}</strong><span>From {message.sender_role === "doctor" ? `Doctor ${message.sender_id}` : formatAction(message.sender_role)}</span></div><time>{formatDate(message.created_at)}</time></summary>
              {message.body ? <p>{message.body}</p> : null}
              {message.attachment_url ? <a href={`${API_BASE_URL}${message.attachment_url}`} target="_blank" rel="noreferrer">{message.attachment_name || "Open attachment"}</a> : null}
            </details>
          ))}
          {!state.messages.length ? <EmptyState>No inbox messages yet.</EmptyState> : null}
        </div>
      </DataPanel>
    </>
  );
}

export function AdminTicketLogPage() {
  const [state, setState] = useState({ status: "loading", message: "Loading support ticket log...", tickets: [], selected: null });
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading support ticket log..." }));
    try {
      const result = await fetchAdminSupportTickets(filter);
      setState((current) => ({ ...current, status: "success", message: "", tickets: result.tickets || [] }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to load support ticket log." }));
    }
  }

  useEffect(() => { load(); }, [filter]);

  const visibleTickets = state.tickets.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function openTicket(ticketId) {
    try {
      const selected = await fetchAdminSupportTicket(ticketId);
      setState((current) => ({ ...current, selected }));
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to open support ticket." }));
    }
  }

  async function changeTicketStatus(ticket) {
    const status = ticket.status === "open" ? "resolved" : "open";
    try {
      await updateAdminSupportTicketStatus(ticket.ticket_id, { status });
      const refreshed = await fetchAdminSupportTicket(ticket.ticket_id);
      const list = await fetchAdminSupportTickets(filter);
      setState((current) => ({ ...current, tickets: list.tickets || [], selected: refreshed }));
      window.dispatchEvent(new Event("synmed:admin-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to update support ticket." }));
    }
  }

  return (
    <>
      <PageHeader title="Ticket Log" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Support tickets" subtitle={`${state.tickets.length} ticket(s)`}>
        <div className="admin-toolbar">
          <select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1); setState((current) => ({ ...current, selected: null })); }}>
            <option value="all">All tickets</option>
            <option value="open">Open</option>
            <option value="resolved">Closed</option>
          </select>
        </div>
        <div className="admin-two-column">
          <div className="admin-inbox">
            {visibleTickets.map((ticket) => (
              <button className="admin-alert" type="button" key={ticket.ticket_id} onClick={() => openTicket(ticket.ticket_id)}>
                <div>
                  <strong>{ticket.ticket_id} / {ticket.patient_name || "Patient"}</strong>
                  <p>{ticket.topic} / {formatDate(ticket.updated_at)}</p>
                </div>
                <StatusPill label={ticket.status} tone={ticket.status === "open" ? "warning" : "success"} />
              </button>
            ))}
            {!visibleTickets.length ? <EmptyState>No support tickets match this view.</EmptyState> : null}
          </div>
          <div className="admin-inbox">
            {state.selected ? (
              <>
                <div className="admin-inbox__message">
                  <div className="admin-inbox__message-heading"><div><strong>{state.selected.ticket_id}</strong><span>{state.selected.patient_name || "Patient"}</span></div><time>{formatDate(state.selected.created_at)}</time></div>
                  <p>{state.selected.summary}</p>
                  <button className="button button--secondary" type="button" onClick={() => changeTicketStatus(state.selected)}>
                    {state.selected.status === "open" ? "Close ticket" : "Reopen ticket"}
                  </button>
                </div>
                {(state.selected.logs || []).map((log) => (
                  <article className="admin-inbox__message" key={log.id}>
                    <div className="admin-inbox__message-heading"><div><strong>{formatAction(log.action)}</strong><span>{formatAction(log.actor_role)} {log.actor_id}</span></div><time>{formatDate(log.created_at)}</time></div>
                    {log.note ? <p>{log.note}</p> : null}
                  </article>
                ))}
              </>
            ) : <EmptyState>Select a ticket to inspect its log.</EmptyState>}
          </div>
        </div>
        <Pager page={page} total={state.tickets.length} onChange={setPage} />
      </DataPanel>
    </>
  );
}

export function AdminErrorsPage() {
  const [state, setState] = useState({
    status: "loading",
    message: "Loading backend error logs...",
    logs: [],
    summary: null,
  });
  const [severity, setSeverity] = useState("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading backend error logs..." }));
    try {
      const result = await fetchAdminErrorLogs(250, severity);
      setState({
        status: "success",
        message: "",
        logs: result.logs || [],
        summary: result.summary || null,
      });
    } catch (error) {
      setState({
        status: "error",
        message: error.message || "Unable to load backend error logs.",
        logs: [],
        summary: null,
      });
    }
  }
  useEffect(() => { load(); }, [severity]);

  const logs = state.logs.filter((log) => !query.trim() || [
    log.source,
    log.severity,
    log.message,
    log.path,
    log.method,
    log.status_code,
    log.user_role,
    log.user_id,
    log.details,
  ].some((value) => String(value || "").toLowerCase().includes(query.toLowerCase().trim())));
  const visible = logs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <PageHeader title="Errors" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Error summary">
        <div className="admin-stats">
          <article><span>Total</span><strong>{state.summary?.total || 0}</strong></article>
          <article><span>Errors</span><strong>{state.summary?.by_severity?.error || 0}</strong></article>
          <article><span>Errors 24h</span><strong>{state.summary?.last_24h?.error || 0}</strong></article>
          <article><span>Warnings</span><strong>{state.summary?.by_severity?.warning || 0}</strong></article>
          <article><span>Latest</span><strong>{state.summary?.latest ? formatDate(state.summary.latest.created_at) : "None"}</strong></article>
        </div>
      </DataPanel>
      <DataPanel title="Backend error log" subtitle={`${logs.length} matching event(s)`}>
        <div className="admin-toolbar">
          <input placeholder="Search source, path, message, user..." value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} />
          <select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
            <option value="all">All severities</option>
            <option value="error">Errors</option>
            <option value="warning">Warnings</option>
            <option value="info">Info</option>
          </select>
        </div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Time</th><th>Source</th><th>Request</th><th>Message</th><th>User</th></tr></thead>
            <tbody>{visible.map((log) => (
              <tr key={log.id}>
                <td>{formatDate(log.created_at)}</td>
                <td><strong>{formatAction(log.source || "system")}</strong><span>{log.severity || "error"}</span></td>
                <td>{log.method || "N/A"}<span>{log.path || "No path"}{log.status_code ? ` / ${log.status_code}` : ""}</span></td>
                <td className="admin-error-message">
                  <strong title={log.message || ""}>{compactText(log.message, 160)}</strong>
                  {log.details ? <span title={log.details}>{compactText(log.details, 220)}</span> : null}
                </td>
                <td>{log.user_role || "N/A"}<span>{log.user_id || "No user"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        {!visible.length ? <EmptyState>No backend errors match this view.</EmptyState> : null}
        <Pager page={page} total={logs.length} onChange={setPage} />
      </DataPanel>
    </>
  );
}

export function AdminActivityPage() {
  const [state, setState] = useState({ status: "loading", message: "Loading admin activity...", logs: [] });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  async function load() {
    setState((current) => ({ ...current, status: "loading", message: "Loading admin activity..." }));
    try {
      const result = await fetchAdminAuditLogs(250);
      setState({ status: "success", message: "", logs: result.logs || [] });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to load admin activity.", logs: [] });
    }
  }
  useEffect(() => { load(); }, []);

  const logs = state.logs.filter((log) => !query.trim() || [log.action, log.target_type, log.target_id, log.admin_id].some((value) => String(value || "").toLowerCase().includes(query.toLowerCase().trim())));
  const visible = logs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <PageHeader title="Activity" actions={<button className="button button--secondary" type="button" onClick={load}>Refresh</button>} />
      <Notice state={state} />
      <DataPanel title="Audit history" subtitle={`${logs.length} matching event(s)`}>
        <div className="admin-toolbar"><input type="search" placeholder="Search action, target or admin ID" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} /></div>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead><tr><th>Time</th><th>Administrator</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
            <tbody>{visible.map((log) => (
              <tr key={log.id}>
                <td>{formatDate(log.created_at)}</td>
                <td>Admin {log.admin_id}</td>
                <td><strong>{formatAction(log.action)}</strong></td>
                <td>{formatAction(log.target_type)}<span>{log.target_id}</span></td>
                <td>{typeof log.details === "string" ? log.details || "None" : Object.entries(log.details || {}).map(([key, value]) => `${formatAction(key)}: ${value}`).join(", ") || "None"}</td>
              </tr>
            ))}</tbody>
          </table>
          {!visible.length ? <EmptyState>No activity records match this view.</EmptyState> : null}
        </div>
        <Pager page={page} total={logs.length} onChange={setPage} />
      </DataPanel>
    </>
  );
}
