import { useEffect, useMemo, useRef, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import StatusPill from "../components/StatusPill.jsx";
import {
  clearCustomerCarePaymentAttention,
  createCustomerCareAccount,
  deleteCustomerCarePaymentAttention,
  fetchCustomerCareMail,
  fetchCustomerCareAccounts,
  fetchCustomerCareDesk,
  fetchCustomerCarePatientDetail,
  fetchCustomerCareSupportTicket,
  fetchCustomerCareSupportTickets,
  grantCustomerCareConsultationAccess,
  markCustomerCareMailRead,
  revokeCustomerCareConsultationAccess,
  searchCustomerCareRecords,
  sendCustomerCarePatientDocument,
  sendCustomerCareMail,
  sendCustomerCareSupportTicketMessage,
  updateCustomerCareAccountStatus,
  updateCustomerCareSupportTicketStatus,
  verifyCustomerCarePayment,
} from "../api/customerCare.js";
import "../styles/customer-care.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const PAGE_SIZE = 8;
const PAYMENT_PAGE_SIZE = 5;
const PANEL_META = {
  overview: {
    title: "Customer care desk",
    description: "",
  },
  tickets: {
    title: "Support tickets",
    description: "",
  },
  messages: {
    title: "Internal messages",
    description: "",
  },
  payments: {
    title: "Payment access",
    description: "",
  },
  consultations: {
    title: "Consultations",
    description: "",
  },
  accounts: {
    title: "Customer care accounts",
    description: "Create and manage customer-care logins.",
  },
};

function formatDate(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function normalizeStatus(value = "") {
  return value.replaceAll("_", " ");
}

function Notice({ state }) {
  if (!state?.message) return null;
  return <div className={`admin-notice admin-notice--${state.status || "idle"}`}>{state.message}</div>;
}

function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

function PaymentTone({ status, active }) {
  if (active) return <StatusPill label="access active" tone="success" />;
  if (status === "verified") return <StatusPill label="paid" tone="success" />;
  if (status === "no_payment") return <StatusPill label="no payment" tone="warning" />;
  return <StatusPill label={normalizeStatus(status || "pending")} tone="warning" />;
}

export default function CustomerCareDashboardPage() {
  const { user } = useOutletContext();
  const canManageAccounts = user?.role === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState({
    status: "loading",
    message: "Loading customer care desk...",
    payments: [],
    consultations: [],
    accounts: [],
    supportTickets: [],
    mail: { messages: [], admins: [], customer_care: [] },
  });
  const [recordQuery, setRecordQuery] = useState("");
  const [results, setResults] = useState({ patients: [], doctors: [] });
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [documentSendState, setDocumentSendState] = useState({ status: "idle", message: "", documentKey: "" });
  const [selectedPayment, setSelectedPayment] = useState(null);
  const [paymentVerifyState, setPaymentVerifyState] = useState({ status: "idle", message: "", reference: "" });
  const [clearPaymentDialogOpen, setClearPaymentDialogOpen] = useState(false);
  const [grantForm, setGrantForm] = useState({ reason: "", duration_hours: 24 });
  const [grantDialogState, setGrantDialogState] = useState({ status: "idle", message: "" });
  const [filter, setFilter] = useState("attention");
  const [page, setPage] = useState(1);
  const [consultationPage, setConsultationPage] = useState(1);
  const [accountPage, setAccountPage] = useState(1);
  const [ticketPage, setTicketPage] = useState(1);
  const [ticketFilter, setTicketFilter] = useState("open");
  const [selectedTicket, setSelectedTicket] = useState(null);
  const [ticketReply, setTicketReply] = useState("");
  const [mailForm, setMailForm] = useState({ recipient: "", subject: "", body: "" });
  const [mailOpen, setMailOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ticketThreadRef = useRef(null);
  const [accountForm, setAccountForm] = useState({
    display_name: "",
    email: "",
    password: "",
  });

  async function load(message = "") {
    setState((current) => ({ ...current, status: "loading", message: message || "Loading customer care desk..." }));
    try {
      const [desk, accounts, mail] = await Promise.all([
        fetchCustomerCareDesk(),
        canManageAccounts ? fetchCustomerCareAccounts() : Promise.resolve({ accounts: [] }),
        fetchCustomerCareMail(),
      ]);
      setState({
        status: "success",
        message: "",
        payments: desk.payments || [],
        consultations: desk.consultations || [],
        accounts: accounts.accounts || [],
        supportTickets: desk.support_tickets || [],
        mail,
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to load customer care desk.",
      }));
    }
  }

  useEffect(() => {
    load();
  }, [canManageAccounts]);

  useEffect(() => {
    if (!selectedTicket?.ticket_id) return undefined;
    let ignore = false;
    async function refreshSelectedTicket() {
      try {
        const ticket = await fetchCustomerCareSupportTicket(selectedTicket.ticket_id);
        if (!ignore) {
          setSelectedTicket(ticket);
          const result = await fetchCustomerCareSupportTickets("all");
          setState((current) => ({ ...current, supportTickets: result.tickets || [] }));
        }
      } catch {}
    }
    const intervalId = window.setInterval(refreshSelectedTicket, 5000);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
    };
  }, [selectedTicket?.ticket_id]);

  useEffect(() => {
    ticketThreadRef.current?.scrollTo({
      top: ticketThreadRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [selectedTicket?.ticket_id, selectedTicket?.messages?.length]);

  useEffect(() => {
    if (recordQuery.trim().length < 2) {
      setResults({ patients: [], doctors: [] });
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      try {
        setResults(await searchCustomerCareRecords(recordQuery));
      } catch {
        setResults({ patients: [], doctors: [] });
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [recordQuery]);

  const metrics = useMemo(() => {
    const activeAccess = state.payments.filter((payment) => payment.access_active).length;
    const pending = state.payments.filter((payment) => payment.status && !["verified", "no_payment"].includes(payment.status)).length;
    const noPayment = state.payments.filter((payment) => payment.status === "no_payment").length;
    const openConsultations = state.consultations.filter((consultation) => consultation.status !== "closed").length;
    return [
      ["Needs payment help", pending + noPayment],
      ["Manual access active", activeAccess],
      ["Open consultations", openConsultations],
      ["Recent consultations", state.consultations.length],
    ];
  }, [state.payments, state.consultations]);

  const visiblePayments = useMemo(() => {
    return state.payments.filter((payment) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "attention" && (!payment.access_active && payment.status !== "verified")) ||
        (filter === "active_access" && payment.access_active) ||
        payment.status === filter;
      return matchesFilter;
    });
  }, [state.payments, filter]);

  const pagedPayments = visiblePayments.slice((page - 1) * PAYMENT_PAGE_SIZE, page * PAYMENT_PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(visiblePayments.length / PAYMENT_PAGE_SIZE));
  const consultationPages = Math.max(1, Math.ceil(state.consultations.length / PAGE_SIZE));
  const pagedConsultations = state.consultations.slice(
    (consultationPage - 1) * PAGE_SIZE,
    consultationPage * PAGE_SIZE,
  );
  const accountPages = Math.max(1, Math.ceil(state.accounts.length / PAGE_SIZE));
  const pagedAccounts = state.accounts.slice((accountPage - 1) * PAGE_SIZE, accountPage * PAGE_SIZE);
  const filteredTickets = state.supportTickets.filter((ticket) => ticketFilter === "all" || ticket.status === ticketFilter);
  const ticketPages = Math.max(1, Math.ceil(filteredTickets.length / PAGE_SIZE));
  const pagedTickets = filteredTickets.slice((ticketPage - 1) * PAGE_SIZE, ticketPage * PAGE_SIZE);
  const unreadMailCount = state.mail.messages.filter((message) => !message.read_at).length;
  const requestedPanel = searchParams.get("panel") || "overview";
  const normalizedPanel = PANEL_META[requestedPanel] ? requestedPanel : "overview";
  const activePanel = normalizedPanel === "accounts" && !canManageAccounts ? "overview" : normalizedPanel;
  const panelMeta = PANEL_META[activePanel] || PANEL_META.overview;
  const overviewCards = [
    { label: "Needs payment help", value: metrics[0]?.[1] ?? 0, panel: "payments" },
    { label: "Manual access active", value: metrics[1]?.[1] ?? 0, panel: "payments" },
    { label: "Open support tickets", value: state.supportTickets.filter((ticket) => ticket.status === "open").length, panel: "tickets" },
    { label: "Unread internal messages", value: unreadMailCount, panel: "messages" },
    { label: "Open consultations", value: metrics[2]?.[1] ?? 0, panel: "consultations" },
    { label: "Recent consultations", value: metrics[3]?.[1] ?? 0, panel: "consultations" },
    ...(canManageAccounts ? [{ label: "Customer-care accounts", value: state.accounts.length, panel: "accounts" }] : []),
  ];

  function openPanel(panel) {
    setSearchParams({ panel });
  }

  async function openPatient(patientId) {
    if (!patientId) return;
    setBusy(true);
    setDocumentSendState({ status: "idle", message: "", documentKey: "" });
    try {
      setSelectedPatient(await fetchCustomerCarePatientDetail(patientId));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to open patient record." }));
    } finally {
      setBusy(false);
    }
  }

  async function sendDocumentToPatient(document) {
    if (!selectedPatient?.patient?.patient_id) return;
    const documentKey = `${document.kind}-${document.document_id}`;
    setDocumentSendState({ status: "loading", message: "Sending document to patient email...", documentKey });
    try {
      const result = await sendCustomerCarePatientDocument(selectedPatient.patient.patient_id, {
        document_kind: document.kind,
        document_id: document.document_id,
        message: "Please find your SynMed clinical document attached.",
      });
      setDocumentSendState({
        status: "success",
        message: result.message || "Document sent to patient.",
        documentKey,
      });
    } catch (error) {
      setDocumentSendState({
        status: "error",
        message: error.message || "Unable to send document.",
        documentKey,
      });
    }
  }

  async function submitGrant(event) {
    event.preventDefault();
    if (!selectedPayment?.patient_id) {
      setGrantDialogState({
        status: "error",
        message: "This payment row is not linked to a patient record, so access cannot be granted from here.",
      });
      return;
    }
    if (!grantForm.reason.trim()) {
      setGrantDialogState({ status: "error", message: "Enter a reason before granting access." });
      return;
    }
    setBusy(true);
    setGrantDialogState({ status: "loading", message: "Granting consultation access..." });
    try {
      const result = await grantCustomerCareConsultationAccess({
        patient_id: selectedPayment.patient_id,
        reason: grantForm.reason,
        duration_hours: Number(grantForm.duration_hours) || 24,
      });
      setSelectedPayment(null);
      setGrantDialogState({ status: "idle", message: "" });
      setGrantForm({ reason: "", duration_hours: 24 });
      setState((current) => ({
        ...current,
        status: "success",
        message: result.message || "Consultation access granted.",
      }));
      await load("Refreshing payment access...");
    } catch (error) {
      setGrantDialogState({ status: "error", message: error.message || "Unable to grant access." });
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to grant access." }));
    } finally {
      setBusy(false);
    }
  }

  async function revokeAccess(reference) {
    setBusy(true);
    try {
      await revokeCustomerCareConsultationAccess(reference);
      await load("Refreshing payment access...");
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to revoke access." }));
    } finally {
      setBusy(false);
    }
  }

  async function verifyPayment(reference) {
    if (!reference || reference.startsWith("none-")) return;
    setBusy(true);
    setPaymentVerifyState({ status: "loading", message: "Checking Paystack transaction...", reference });
    try {
      const result = await verifyCustomerCarePayment(reference);
      setPaymentVerifyState({
        status: result.verified ? "success" : "warning",
        message: result.message || (result.verified ? "Payment verified." : "Payment is not confirmed yet."),
        reference,
      });
      await load("Refreshing payment records...");
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

  function canDeletePaymentAttention(payment) {
    return payment.status !== "verified" && payment.source !== "admin_grant";
  }

  async function deletePaymentAttention(payment) {
    setBusy(true);
    try {
      const result = await deleteCustomerCarePaymentAttention({
        reference: payment.reference || "",
        patient_id: payment.reference ? "" : payment.patient_id || "",
      });
      await load(result.message);
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to delete payment attention row." }));
    } finally {
      setBusy(false);
    }
  }

  async function clearPaymentAttention() {
    setBusy(true);
    try {
      const result = await clearCustomerCarePaymentAttention();
      setClearPaymentDialogOpen(false);
      await load(result.message);
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to clear payment attention rows." }));
    } finally {
      setBusy(false);
    }
  }

  async function submitAccount(event) {
    event.preventDefault();
    if (!canManageAccounts) return;
    setBusy(true);
    try {
      await createCustomerCareAccount(accountForm);
      setAccountForm({ display_name: "", email: "", password: "" });
      await load("Refreshing customer care accounts...");
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to create account." }));
    } finally {
      setBusy(false);
    }
  }

  async function toggleAccount(account) {
    if (!canManageAccounts) return;
    setBusy(true);
    try {
      const nextStatus = account.status === "active" ? "suspended" : "active";
      await updateCustomerCareAccountStatus(account.account_id, nextStatus);
      await load("Refreshing customer care accounts...");
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to update account." }));
    } finally {
      setBusy(false);
    }
  }

  async function updateAccountStatus(account, status) {
    if (!canManageAccounts) return;
    setBusy(true);
    try {
      await updateCustomerCareAccountStatus(account.account_id, status);
      await load("Refreshing customer care accounts...");
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to update account." }));
    } finally {
      setBusy(false);
    }
  }

  async function openTicket(ticketId) {
    setBusy(true);
    try {
      setSelectedTicket(await fetchCustomerCareSupportTicket(ticketId));
      window.dispatchEvent(new Event("synmed:customer-care-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to open support ticket." }));
    } finally {
      setBusy(false);
    }
  }

  async function changeTicketStatus(ticketId, status) {
    setBusy(true);
    try {
      await updateCustomerCareSupportTicketStatus(ticketId, { status });
      const result = await fetchCustomerCareSupportTickets("all");
      setState((current) => ({ ...current, supportTickets: result.tickets || [] }));
      window.dispatchEvent(new Event("synmed:customer-care-notifications-updated"));
      if (selectedTicket?.ticket_id === ticketId) {
        setSelectedTicket(await fetchCustomerCareSupportTicket(ticketId));
      }
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to update support ticket." }));
    } finally {
      setBusy(false);
    }
  }

  async function submitTicketReply(event) {
    event.preventDefault();
    if (!selectedTicket || !ticketReply.trim()) return;
    setBusy(true);
    try {
      await sendCustomerCareSupportTicketMessage(selectedTicket.ticket_id, ticketReply.trim());
      setTicketReply("");
      setSelectedTicket(await fetchCustomerCareSupportTicket(selectedTicket.ticket_id));
      const result = await fetchCustomerCareSupportTickets("all");
      setState((current) => ({ ...current, supportTickets: result.tickets || [] }));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to send ticket reply." }));
    } finally {
      setBusy(false);
    }
  }

  function handleTicketReplyKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function submitMail(event) {
    event.preventDefault();
    const [recipientRole, recipientId] = mailForm.recipient.split(":");
    setBusy(true);
    try {
      await sendCustomerCareMail({
        recipient_role: recipientRole,
        recipient_id: recipientId,
        subject: mailForm.subject,
        body: mailForm.body,
      });
      setMailForm({ recipient: "", subject: "", body: "" });
      setMailOpen(false);
      const mail = await fetchCustomerCareMail();
      setState((current) => ({ ...current, mail }));
      window.dispatchEvent(new Event("synmed:customer-care-notifications-updated"));
    } catch (error) {
      setState((current) => ({ ...current, status: "error", message: error.message || "Unable to send internal message." }));
    } finally {
      setBusy(false);
    }
  }

  async function openMail(message) {
    if (message.read_at) return;
    try {
      await markCustomerCareMailRead(message.id);
      setState((current) => ({
        ...current,
        mail: {
          ...current.mail,
          messages: current.mail.messages.map((item) =>
            item.id === message.id ? { ...item, read_at: new Date().toISOString() } : item,
          ),
        },
      }));
      window.dispatchEvent(new Event("synmed:customer-care-notifications-updated"));
    } catch {}
  }

  return (
    <>
      <header className="admin-page-header customer-care-header">
        <div>
          <h1>{panelMeta.title}</h1>
          {panelMeta.description ? <span>{panelMeta.description}</span> : null}
        </div>
        <div className="customer-care-header__actions">
          <button className="button button--secondary" type="button" onClick={() => load()} disabled={state.status === "loading"}>
            Refresh
          </button>
        </div>
      </header>

      <Notice state={state} />

      {activePanel === "overview" ? (
        <>
          <div className="admin-global-search customer-care-overview-search">
            <div className="customer-care-overview-search__control">
              <input
                type="search"
                aria-label="Search patient or doctor records"
                placeholder="Search patient or doctor records"
                value={recordQuery}
                onChange={(event) => {
                  setRecordQuery(event.target.value);
                  setPage(1);
                }}
              />
              <button className="admin-search-action admin-search-action--submit" type="button" aria-label="Search" title="Search">
                <SearchIcon />
              </button>
            </div>
            {recordQuery.trim().length >= 2 ? (
              <div className="admin-global-search__results customer-care-overview-search__results">
                {[...(results.patients || [])].map((patient) => (
                  <button key={`patient-${patient.patient_id}`} type="button" onClick={() => openPatient(patient.patient_id)}>
                    <strong>{patient.name || "Patient"}</strong>
                    <span>Patient / {patient.patient_id}</span>
                  </button>
                ))}
                {[...(results.doctors || [])].map((doctor) => (
                  <article key={`doctor-${doctor.telegram_id}`}>
                    <strong>{doctor.name || "Doctor"}</strong>
                    <span>Doctor / {doctor.specialty || doctor.telegram_id}</span>
                  </article>
                ))}
                {!results.patients?.length && !results.doctors?.length ? <div className="admin-global-search__empty">No matching records.</div> : null}
              </div>
            ) : null}
          </div>

          <section className="customer-care-overview-grid customer-care-overview-grid--standalone">
            {overviewCards.map((card) => (
              <button type="button" key={`${card.panel}-${card.label}`} onClick={() => openPanel(card.panel)}>
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <em>Open</em>
              </button>
            ))}
          </section>
        </>
      ) : null}

      {activePanel === "tickets" ? (
      <section className="admin-panel customer-care-ticket-panel">
        <header className="admin-panel__header">
          <div>
            <h2>Support tickets</h2>
          </div>
          <select value={ticketFilter} onChange={(event) => { setTicketFilter(event.target.value); setTicketPage(1); }}>
            <option value="open">Open</option>
            <option value="resolved">Closed</option>
            <option value="all">All tickets</option>
          </select>
        </header>
        <div className="customer-care-ticket-workspace">
          <div className="customer-care-ticket-list">
            {pagedTickets.map((ticket) => {
              const unreadCount = Number(ticket.unread_patient_messages || 0);
              const rowClassName = [
                "customer-care-ticket-list__item",
                selectedTicket?.ticket_id === ticket.ticket_id ? "customer-care-ticket-list__item--active" : "",
                unreadCount ? "customer-care-ticket-list__item--unread" : "",
              ].filter(Boolean).join(" ");
              return (
                <article key={ticket.ticket_id} className={rowClassName}>
                  <button type="button" onClick={() => openTicket(ticket.ticket_id)}>
                    <strong>{ticket.ticket_id} / {ticket.patient_name || "Patient"}</strong>
                    <span className="customer-care-ticket-list__meta">
                      {ticket.topic} / {formatDate(ticket.updated_at || ticket.created_at)}
                      {unreadCount ? <em className="customer-care-ticket-list__new">{unreadCount > 1 ? `${unreadCount} new` : "New"}</em> : null}
                    </span>
                    <p>{ticket.summary}</p>
                    <StatusPill label={ticket.status} tone={ticket.status === "open" ? "warning" : "success"} />
                  </button>
                </article>
              );
            })}
            {!filteredTickets.length ? <div className="admin-empty">No support tickets match this view.</div> : null}
          </div>
          <aside className="customer-care-ticket-detail">
            {selectedTicket ? (
              <>
                <header>
                  <div>
                    <span>{selectedTicket.ticket_id}</span>
                    <h3>{selectedTicket.patient_name || "Patient"}</h3>
                    <p>{selectedTicket.topic} / {formatDate(selectedTicket.created_at)}</p>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => changeTicketStatus(selectedTicket.ticket_id, selectedTicket.status === "open" ? "resolved" : "open")}
                  >
                    {selectedTicket.status === "open" ? "Close ticket" : "Reopen"}
                  </button>
                </header>
                <div className="customer-care-ticket-thread" ref={ticketThreadRef}>
                  {(selectedTicket.messages || []).map((entry) => (
                    <article className={entry.sender_role === "patient" ? "customer-care-ticket-message customer-care-ticket-message--patient" : "customer-care-ticket-message"} key={entry.id}>
                      <span>{normalizeStatus(entry.sender_role)} / {formatDate(entry.created_at)}</span>
                      <p>{entry.message_text}</p>
                    </article>
                  ))}
                </div>
                <form className="customer-care-ticket-reply" onSubmit={submitTicketReply}>
                  <textarea
                    rows="3"
                    value={ticketReply}
                    onChange={(event) => setTicketReply(event.target.value)}
                    onKeyDown={handleTicketReplyKeyDown}
                    placeholder={selectedTicket.status === "open" ? "Reply to patient" : "Reopen the ticket before replying"}
                    disabled={selectedTicket.status !== "open"}
                  />
                  <button className="button button--primary" type="submit" disabled={busy || selectedTicket.status !== "open" || !ticketReply.trim()}>
                    Send reply
                  </button>
                </form>
                <div className="customer-care-ticket-logs">
                  <h4>Ticket log</h4>
                  {(selectedTicket.logs || []).map((log) => (
                    <p key={log.id}>
                      <strong>{normalizeStatus(log.action)}</strong> by {normalizeStatus(log.actor_role)} {log.actor_id || ""} / {formatDate(log.created_at)}
                    </p>
                  ))}
                </div>
              </>
            ) : (
              <div className="admin-empty">Select a ticket to view conversation and logs.</div>
            )}
          </aside>
        </div>
        {ticketPages > 1 ? (
          <div className="admin-pager">
            <span>Page {ticketPage} of {ticketPages}</span>
            <div>
              <button type="button" disabled={ticketPage <= 1} onClick={() => setTicketPage((current) => current - 1)}>Previous</button>
              <button type="button" disabled={ticketPage >= ticketPages} onClick={() => setTicketPage((current) => current + 1)}>Next</button>
            </div>
          </div>
        ) : null}
      </section>
      ) : null}

      {activePanel === "messages" ? (
      <section className="admin-panel customer-care-mail-panel">
        <header className="admin-panel__header">
          <div>
            <h2>Internal messages</h2>
          </div>
          <div className="customer-care-mail-actions">
            <span>{unreadMailCount} unread</span>
            <button className="button button--primary" type="button" onClick={() => setMailOpen((current) => !current)}>
              {mailOpen ? "Close" : "New message"}
            </button>
          </div>
        </header>
        {mailOpen ? (
          <form className="admin-form customer-care-mail-compose" onSubmit={submitMail}>
            <label>
              <span>Recipient</span>
              <select required value={mailForm.recipient} onChange={(event) => setMailForm((current) => ({ ...current, recipient: event.target.value }))}>
                <option value="">Select recipient</option>
                <optgroup label="Administrators">
                  {(state.mail.admins || []).map((admin) => (
                    <option key={`admin-${admin.admin_id}`} value={`admin:${admin.admin_id}`}>
                      {admin.display_name || `Admin ${admin.admin_id}`}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Customer care">
                  {(state.mail.customer_care || []).map((account) => (
                    <option key={`support-${account.account_id}`} value={`customer_care:${account.account_id}`}>
                      {account.display_name}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            <label><span>Subject</span><input required value={mailForm.subject} onChange={(event) => setMailForm((current) => ({ ...current, subject: event.target.value }))} /></label>
            <label><span>Message</span><textarea rows="3" value={mailForm.body} onChange={(event) => setMailForm((current) => ({ ...current, body: event.target.value }))} /></label>
            <button className="button button--primary" type="submit" disabled={busy}>Send message</button>
          </form>
        ) : null}
        <div className="customer-care-mail-list">
          {(state.mail.messages || []).map((message) => (
            <details className={message.read_at ? "customer-care-mail-row" : "customer-care-mail-row customer-care-mail-row--unread"} key={message.id} onToggle={(event) => event.currentTarget.open && openMail(message)}>
              <summary>
                <div>
                  <strong>{message.subject}</strong>
                  <span>From {normalizeStatus(message.sender_role)} {message.sender_id}</span>
                </div>
                <time>{formatDate(message.created_at)}</time>
              </summary>
              {message.body ? <p>{message.body}</p> : null}
            </details>
          ))}
          {!state.mail.messages?.length ? <div className="admin-empty">No internal messages yet.</div> : null}
        </div>
      </section>
      ) : null}

      {activePanel === "payments" ? (
        <section className="admin-panel customer-care-payment-panel">
          <header className="admin-panel__header">
            <h2>Payment and access support</h2>
          </header>
          <div className="admin-toolbar">
            <select value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1); }}>
              <option value="attention">Needs attention</option>
              <option value="all">All payment records</option>
              <option value="verified">Completed payments</option>
              <option value="no_payment">No payment</option>
              <option value="active_access">Manual access active</option>
            </select>
            <button className="button admin-button--danger" type="button" onClick={() => setClearPaymentDialogOpen(true)} disabled={busy}>
              Clear attention
            </button>
          </div>
          <div className="admin-table-wrap customer-care-payment-table-wrap">
            <table className="admin-table customer-care-table">
              <thead>
                <tr><th>Patient</th><th>Payment</th><th>Access</th><th>Action</th></tr>
              </thead>
              <tbody>
                {pagedPayments.map((payment) => (
                  <tr key={payment.reference || `none-${payment.patient_id}`}>
                    <td>
                      <button className="admin-record-link" type="button" onClick={() => openPatient(payment.patient_id)}>
                        <strong>{payment.patient_id || "Unknown patient"}</strong>
                        <span>{payment.email || payment.patient_type || "No contact recorded"}</span>
                      </button>
                    </td>
                    <td>
                      <PaymentTone status={payment.status} active={payment.access_active} />
                      <span>{payment.reference || payment.label || "No reference"}</span>
                    </td>
                    <td>
                      <strong>{payment.access_active ? "Can proceed" : "Not active"}</strong>
                      <span>{payment.access_expires_at ? `Until ${formatDate(payment.access_expires_at)}` : "No access window"}</span>
                    </td>
                    <td>
                      <div className="admin-row-actions">
                        {payment.reference && payment.source === "paystack" ? (
                          <button type="button" onClick={() => verifyPayment(payment.reference)} disabled={busy}>
                            {paymentVerifyState.status === "loading" && paymentVerifyState.reference === payment.reference ? "Verifying..." : "Verify"}
                          </button>
                        ) : null}
                        {!payment.access_active ? (
                          <button
                            type="button"
                            onClick={() => {
                              setGrantDialogState({ status: "idle", message: "" });
                              setSelectedPayment(payment);
                            }}
                          >
                            Grant access
                          </button>
                        ) : null}
                        {payment.access_active && payment.reference ? (
                          <button type="button" onClick={() => revokeAccess(payment.reference)} disabled={busy}>Revoke</button>
                        ) : null}
                        {canDeletePaymentAttention(payment) ? (
                          <button type="button" onClick={() => deletePaymentAttention(payment)} disabled={busy}>Delete</button>
                        ) : null}
                      </div>
                      {paymentVerifyState.reference === payment.reference && paymentVerifyState.message ? (
                        <span className={`customer-care-payment-verify customer-care-payment-verify--${paymentVerifyState.status}`}>
                          {paymentVerifyState.message}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!pagedPayments.length ? <div className="admin-empty">No payment records match this view.</div> : null}
          </div>
          {totalPages > 1 ? (
            <div className="admin-pager">
              <span>Page {page} of {totalPages}</span>
              <div>
                <button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}>Previous</button>
                <button type="button" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)}>Next</button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {activePanel === "consultations" ? (
        <section className="admin-panel">
          <header className="admin-panel__header">
            <h2>Recent consultation state</h2>
          </header>
          <div className="customer-care-consultations">
            {pagedConsultations.map((consultation) => (
              <article key={consultation.consultation_id}>
                <div>
                  <strong>{consultation.patient_name || consultation.patient_id || "Patient"}</strong>
                  <span>Doctor: {consultation.doctor_name || consultation.doctor_id || "Not assigned"}</span>
                </div>
                <div>
                  <StatusPill label={normalizeStatus(consultation.status || "unknown")} tone={consultation.status === "closed" ? "success" : "warning"} />
                  <span>{formatDate(consultation.created_at)}</span>
                </div>
              </article>
            ))}
            {!state.consultations.length ? <div className="admin-empty">No consultations recorded yet.</div> : null}
          </div>
          {consultationPages > 1 ? (
            <div className="admin-pager">
              <span>Page {consultationPage} of {consultationPages}</span>
              <div>
                <button type="button" disabled={consultationPage <= 1} onClick={() => setConsultationPage((current) => current - 1)}>Previous</button>
                <button type="button" disabled={consultationPage >= consultationPages} onClick={() => setConsultationPage((current) => current + 1)}>Next</button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {canManageAccounts && activePanel === "accounts" ? (
        <section className="admin-panel customer-care-accounts">
          <header className="admin-panel__header">
            <h2>Customer care accounts</h2>
            <p>Create customer-care requests, then approve only agents cleared for desk access.</p>
          </header>
          <div className="customer-care-account-grid">
            <form className="admin-form" onSubmit={submitAccount}>
              <label>
                <span>Display name</span>
                <input
                  required
                  value={accountForm.display_name}
                  onChange={(event) => setAccountForm((current) => ({ ...current, display_name: event.target.value }))}
                />
              </label>
              <label>
                <span>Email</span>
                <input
                  required
                  type="email"
                  value={accountForm.email}
                  onChange={(event) => setAccountForm((current) => ({ ...current, email: event.target.value }))}
                />
              </label>
              <label>
                <span>Temporary password</span>
                <input
                  required
                  type="password"
                  value={accountForm.password}
                  onChange={(event) => setAccountForm((current) => ({ ...current, password: event.target.value }))}
                />
              </label>
              <button className="button button--primary" type="submit" disabled={busy}>
                Create request
              </button>
            </form>
            <div className="customer-care-account-list">
              {pagedAccounts.map((account) => (
                <article key={account.account_id}>
                  <div>
                    <strong>{account.display_name}</strong>
                    <span>{account.email}</span>
                    <span>Last login: {formatDate(account.last_login_at)}</span>
                  </div>
                  <div>
                    <StatusPill
                      label={account.status}
                      tone={account.status === "active" ? "success" : account.status === "pending" ? "warning" : "danger"}
                    />
                    {account.status === "pending" ? (
                      <>
                        <button type="button" onClick={() => updateAccountStatus(account, "active")} disabled={busy}>Approve</button>
                        <button type="button" onClick={() => updateAccountStatus(account, "rejected")} disabled={busy}>Reject</button>
                      </>
                    ) : null}
                    {account.status === "active" ? (
                      <button type="button" onClick={() => toggleAccount(account)} disabled={busy}>Suspend</button>
                    ) : null}
                    {["suspended", "rejected"].includes(account.status) ? (
                      <button type="button" onClick={() => updateAccountStatus(account, "active")} disabled={busy}>Reactivate</button>
                    ) : null}
                  </div>
                </article>
              ))}
              {!state.accounts.length ? <div className="admin-empty">No customer care accounts created yet.</div> : null}
            </div>
            {accountPages > 1 ? (
              <div className="admin-pager customer-care-account-pager">
                <span>Page {accountPage} of {accountPages}</span>
                <div>
                  <button type="button" disabled={accountPage <= 1} onClick={() => setAccountPage((current) => current - 1)}>Previous</button>
                  <button type="button" disabled={accountPage >= accountPages} onClick={() => setAccountPage((current) => current + 1)}>Next</button>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {selectedPatient ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedPatient(null)}>
          <section className="admin-record-card" role="dialog" aria-modal="true" aria-labelledby="support-patient-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span>Patient support record</span>
                <h2 id="support-patient-title">{selectedPatient.patient?.name || "Patient"}</h2>
                <p>{selectedPatient.patient?.patient_id}</p>
              </div>
              <button type="button" onClick={() => setSelectedPatient(null)}>Close</button>
            </header>
            <div className="admin-biodata-grid">
              {[
                ["Hospital number", selectedPatient.patient?.patient_id],
                ["Phone", selectedPatient.patient?.phone],
                ["Email", selectedPatient.patient?.email],
                ["Email verified", selectedPatient.patient?.email_verified_at ? "Yes" : "No"],
                ["Age", selectedPatient.patient?.age],
                ["Gender", selectedPatient.patient?.gender],
                ["Allergy", selectedPatient.patient?.allergy],
                ["Created", formatDate(selectedPatient.patient?.created_at)],
              ].map(([label, value]) => (
                <div key={label}>
                  <span>{label}</span>
                  <strong>{value || "Not recorded"}</strong>
                </div>
              ))}
            </div>
            <section className="customer-care-documents">
              <h3>Support-visible documents</h3>
              {(selectedPatient.documents || []).slice(0, 8).map((document) => (
                <article key={`${document.kind}-${document.document_id}`}>
                  <div>
                    <strong>{document.kind}</strong>
                    <span>{document.document_id} / {formatDate(document.created_at)}</span>
                    {documentSendState.documentKey === `${document.kind}-${document.document_id}` && documentSendState.message ? (
                      <span className={`customer-care-documents__notice customer-care-documents__notice--${documentSendState.status}`}>
                        {documentSendState.message}
                      </span>
                    ) : null}
                  </div>
                  <div className="customer-care-documents__actions">
                    {document.asset_url ? <a href={`${API_BASE_URL}${document.asset_url}`} target="_blank" rel="noreferrer">Open</a> : null}
                    <button
                      type="button"
                      disabled={documentSendState.status === "loading"}
                      onClick={() => sendDocumentToPatient(document)}
                    >
                      {documentSendState.status === "loading" && documentSendState.documentKey === `${document.kind}-${document.document_id}`
                        ? "Sending..."
                        : "Send to patient"}
                    </button>
                  </div>
                </article>
              ))}
              {!selectedPatient.documents?.length ? <p>No clinical documents are attached yet.</p> : null}
            </section>
          </section>
        </div>
      ) : null}

      {clearPaymentDialogOpen ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setClearPaymentDialogOpen(false)}>
          <div className="admin-dialog" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
            <h2>Clear payment attention</h2>
            <p>Clear all pending, failed, and no-payment attention rows? Verified payments and active grants will be kept.</p>
            <div className="admin-dialog__actions">
              <button className="button button--secondary" type="button" onClick={() => setClearPaymentDialogOpen(false)} disabled={busy}>Cancel</button>
              <button className="button admin-button--danger" type="button" onClick={clearPaymentAttention} disabled={busy}>
                {busy ? "Clearing..." : "Clear attention"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {selectedPayment ? (
        <div className="admin-dialog-backdrop" role="presentation" onMouseDown={() => setSelectedPayment(null)}>
          <form className="admin-dialog customer-care-grant-dialog" onSubmit={submitGrant} onMouseDown={(event) => event.stopPropagation()}>
            <h2>Grant consultation access</h2>
            <p>Patient {selectedPayment.patient_id || "not linked"} will be allowed to proceed without a completed payment for the selected time.</p>
            <label>
              <span>Reason</span>
              <textarea required rows="3" value={grantForm.reason} onChange={(event) => setGrantForm((current) => ({ ...current, reason: event.target.value }))} />
            </label>
            <label>
              <span>Duration</span>
              <select value={grantForm.duration_hours} onChange={(event) => setGrantForm((current) => ({ ...current, duration_hours: event.target.value }))}>
                <option value="2">2 hours</option>
                <option value="12">12 hours</option>
                <option value="24">24 hours</option>
                <option value="48">48 hours</option>
              </select>
            </label>
            {grantDialogState.message ? (
              <div className={`customer-care-dialog-notice customer-care-dialog-notice--${grantDialogState.status}`}>
                {grantDialogState.message}
              </div>
            ) : null}
            <div className="admin-dialog__actions">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  setSelectedPayment(null);
                  setGrantDialogState({ status: "idle", message: "" });
                }}
                disabled={busy}
              >
                Cancel
              </button>
              <button className="button button--primary" type="submit" disabled={busy}>{busy ? "Granting..." : "Grant access"}</button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
