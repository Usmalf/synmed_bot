import { useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";
import { restoreSession } from "../api/auth.js";
import {
  fetchDoctorMail,
  markDoctorMailRead,
  sendDoctorMail,
} from "../api/doctors.js";
import "../styles/doctor.css";
import "../styles/forms.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function emptyMailForm() {
  return {
    recipient: "",
    subject: "",
    body: "",
  };
}

function formatMessageDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function DoctorMessagesPage() {
  const [authStatus, setAuthStatus] = useState("loading");
  const [mailState, setMailState] = useState({
    status: "loading",
    message: "Loading messages...",
    messages: [],
    doctors: [],
    admins: [],
  });
  const [mailForm, setMailForm] = useState(emptyMailForm);
  const [composerOpen, setComposerOpen] = useState(false);

  const unreadCount = useMemo(
    () => mailState.messages.filter((message) => !message.read_at).length,
    [mailState.messages],
  );

  async function loadMail(options = {}) {
    const { silent = false } = options;
    if (!silent) {
      setMailState((current) => ({
        ...current,
        status: "loading",
        message: "Loading messages...",
      }));
    }
    try {
      const result = await fetchDoctorMail();
      setMailState({
        status: "success",
        message: "",
        messages: result.messages || [],
        doctors: result.doctors || [],
        admins: result.admins || [],
      });
    } catch (error) {
      setMailState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to load doctor messages.",
      }));
    }
  }

  useEffect(() => {
    let ignore = false;
    async function startPage() {
      try {
        const session = await restoreSession();
        if (ignore) return;
        if (session.user?.role !== "doctor") {
          setAuthStatus("denied");
          return;
        }
        setAuthStatus("ready");
        await loadMail();
      } catch {
        if (!ignore) setAuthStatus("denied");
      }
    }
    startPage();
    const intervalId = window.setInterval(() => {
      if (!ignore) loadMail({ silent: true });
    }, 30000);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    const [recipientRole, recipientId] = mailForm.recipient.split(":");
    setMailState((current) => ({
      ...current,
      status: "loading",
      message: "Sending message...",
    }));
    try {
      await sendDoctorMail({
        recipient_role: recipientRole,
        recipient_id: Number(recipientId),
        subject: mailForm.subject,
        body: mailForm.body,
      });
      setMailForm(emptyMailForm());
      setComposerOpen(false);
      await loadMail();
      window.dispatchEvent(new Event("synmed:doctor-mail-updated"));
    } catch (error) {
      setMailState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to send message.",
      }));
    }
  }

  async function handleOpen(message) {
    if (message.read_at) return;
    try {
      await markDoctorMailRead(message.id);
      setMailState((current) => ({
        ...current,
        messages: current.messages.map((item) =>
          item.id === message.id ? { ...item, read_at: new Date().toISOString() } : item,
        ),
      }));
      window.dispatchEvent(new Event("synmed:doctor-mail-updated"));
    } catch {}
  }

  if (authStatus === "loading") {
    return <div className="doctor-message-page__loading">Checking doctor session...</div>;
  }
  if (authStatus !== "ready") {
    return <Navigate to="/signin" replace />;
  }

  return (
    <div className="doctor-message-page">
      <header className="doctor-page-header">
        <div>
          <p>Doctor Workspace</p>
          <h1>Messages</h1>
          <span>Communicate with SynMed administration and other doctors.</span>
        </div>
        <div className="doctor-page-header__actions">
          <span className={unreadCount ? "doctor-unread-count doctor-unread-count--active" : "doctor-unread-count"}>
            {unreadCount} unread
          </span>
          <button className="button button--primary" type="button" onClick={() => setComposerOpen((current) => !current)}>
            {composerOpen ? "Close" : "New message"}
          </button>
        </div>
      </header>

      {composerOpen ? (
        <section className="doctor-portal-panel">
          <div className="doctor-portal-panel__header">
            <h2>Compose message</h2>
            <p>Send an internal message to a doctor or administrator.</p>
          </div>
          <form className="doctor-message-compose" onSubmit={handleSubmit}>
            <label className="form-field doctor-message-compose__recipient">
              <span className="form-field__label">Recipient</span>
              <select className="form-field__input" required value={mailForm.recipient} onChange={(event) => setMailForm((current) => ({ ...current, recipient: event.target.value }))}>
                <option value="">Select an administrator or doctor</option>
                <optgroup label="Administration">
                  {mailState.admins.map((item) => (
                    <option key={`admin-${item.admin_id}`} value={`admin:${item.admin_id}`}>
                      {item.display_name || `Administrator ${item.admin_id}`}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Doctors">
                  {mailState.doctors.map((item) => (
                    <option key={`doctor-${item.telegram_id}`} value={`doctor:${item.telegram_id}`}>
                      {item.name} / {item.specialty}
                    </option>
                  ))}
                </optgroup>
              </select>
            </label>
            <label className="form-field doctor-message-compose__subject">
              <span className="form-field__label">Subject</span>
              <input className="form-field__input" required value={mailForm.subject} onChange={(event) => setMailForm((current) => ({ ...current, subject: event.target.value }))} />
            </label>
            <label className="form-field doctor-message-compose__body">
              <span className="form-field__label">Message</span>
              <textarea className="form-field__input form-field__input--textarea" required rows="4" value={mailForm.body} onChange={(event) => setMailForm((current) => ({ ...current, body: event.target.value }))} />
            </label>
            <div className="doctor-message-compose__actions">
              <button className="button button--primary" disabled={mailState.status === "loading"} type="submit">
                Send message
              </button>
            </div>
          </form>
        </section>
      ) : null}

      <section className="doctor-portal-panel">
        <div className="doctor-portal-panel__header">
          <h2>Inbox</h2>
          <p>Unread messages are highlighted until opened.</p>
        </div>
        {mailState.message ? (
          <p className={`doctor-message-page__status doctor-message-page__status--${mailState.status}`}>
            {mailState.message}
          </p>
        ) : null}
        <div className="doctor-message-list">
          {mailState.messages.map((message) => (
            <details
              className={message.read_at ? "doctor-message-row" : "doctor-message-row doctor-message-row--unread"}
              key={message.id}
              onToggle={(event) => event.currentTarget.open && handleOpen(message)}
            >
              <summary>
                <span className="doctor-message-row__indicator" aria-hidden="true" />
                <span className="doctor-message-row__sender">
                  {message.sender_role === "admin" ? "Administration" : `Doctor ${message.sender_id}`}
                </span>
                <strong>{message.subject}</strong>
                <time>{formatMessageDate(message.created_at)}</time>
              </summary>
              <div className="doctor-message-row__content">
                {message.body ? <p>{message.body}</p> : null}
                {message.attachment_url ? (
                  <a href={`${API_BASE_URL}${message.attachment_url}`} target="_blank" rel="noreferrer">
                    {message.attachment_name || "Open attachment"}
                  </a>
                ) : null}
              </div>
            </details>
          ))}
          {!mailState.messages.length && mailState.status !== "loading" ? (
            <p className="doctor-message-page__empty">No messages yet.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
