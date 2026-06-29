import { useEffect, useRef, useState } from "react";
import { getAuthToken } from "../api/auth.js";
import {
  fetchPatientSupportTicket,
  sendPatientSupportAiMessage,
  sendPatientSupportTicketMessage,
  submitPatientSupportTicketFeedback,
} from "../api/patients.js";
import {
  fetchPublicSupportTicket,
  sendPublicSupportAiMessage,
  sendPublicSupportTicketMessage,
  submitPublicSupportTicketFeedback,
} from "../api/support.js";

const SUPPORT_MESSAGES_KEY = "synmed_support_assistant_messages";
const SUPPORT_TICKET_KEY = "synmed_support_assistant_ticket";
const SUPPORT_EMAIL_KEY = "synmed_support_contact_email";
const SUPPORT_LAST_ACTIVITY_KEY = "synmed_support_last_activity_at";
const SUPPORT_IDLE_RESET_MS = 30 * 60 * 1000;

const defaultMessages = [
  {
    role: "assistant",
    text: "Hi, I am SynMed support assistant. I can help with OTP, payments, documents, appointments, and consultation access.",
  },
];

const defaultQuickReplies = ["OTP problem", "Payment issue", "Documents", "Talk to agent"];

function loadSavedMessages() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SUPPORT_MESSAGES_KEY) || "[]");
    return Array.isArray(parsed) && parsed.length ? parsed.slice(-40) : defaultMessages;
  } catch {
    return defaultMessages;
  }
}

function loadSavedTicketId() {
  try {
    return window.localStorage.getItem(SUPPORT_TICKET_KEY) || "";
  } catch {
    return "";
  }
}

function loadSavedSupportEmail() {
  try {
    return window.localStorage.getItem(SUPPORT_EMAIL_KEY) || "";
  } catch {
    return "";
  }
}

function getLastSupportActivity() {
  try {
    return Number(window.localStorage.getItem(SUPPORT_LAST_ACTIVITY_KEY) || "0");
  } catch {
    return 0;
  }
}

function shouldEscalate(message) {
  return /\b(human|agent|customer care|support staff|real person|representative)\b/i.test(message);
}

function getQuickReplyRoute(reply) {
  const normalized = reply.toLowerCase();
  if (normalized === "start consultation") return "/patient/consultation";
  if (normalized === "return to chat") return "/patient";
  if (normalized === "documents" || normalized.includes("prescription") || normalized.includes("report")) {
    return "/patient/documents";
  }
  if (normalized === "i need to sign in") return "/patient/signin";
  return "";
}

export default function CustomerSupportWidget({ nudgedUp = false }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState(loadSavedMessages);
  const [quickReplies, setQuickReplies] = useState(defaultQuickReplies);
  const [activeTicketId, setActiveTicketId] = useState(loadSavedTicketId);
  const [supportEmail, setSupportEmail] = useState(loadSavedSupportEmail);
  const [emailDraft, setEmailDraft] = useState(loadSavedSupportEmail);
  const [awaitingEmail, setAwaitingEmail] = useState(false);
  const [pendingAgentMessage, setPendingAgentMessage] = useState("");
  const [reviewPrompt, setReviewPrompt] = useState({ visible: false, ticketId: "", rating: 5, review: "" });
  const messagesRef = useRef(null);

  function markSupportActivity() {
    try {
      window.localStorage.setItem(SUPPORT_LAST_ACTIVITY_KEY, String(Date.now()));
    } catch {}
  }

  function resetAssistantSession() {
    setInput("");
    setBusy(false);
    setMessages(defaultMessages);
    setQuickReplies(defaultQuickReplies);
    setAwaitingEmail(false);
    setPendingAgentMessage("");
    setReviewPrompt({ visible: false, ticketId: "", rating: 5, review: "" });
    window.localStorage.setItem(SUPPORT_MESSAGES_KEY, JSON.stringify(defaultMessages));
  }

  function resetIfSupportIdle() {
    const lastActivity = getLastSupportActivity();
    if (lastActivity && Date.now() - lastActivity >= SUPPORT_IDLE_RESET_MS) {
      resetAssistantSession();
      markSupportActivity();
      return true;
    }
    return false;
  }

  useEffect(() => {
    resetIfSupportIdle();
    markSupportActivity();
    const intervalId = window.setInterval(resetIfSupportIdle, 60 * 1000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(SUPPORT_MESSAGES_KEY, JSON.stringify(messages.slice(-40)));
  }, [messages]);

  useEffect(() => {
    if (activeTicketId) window.localStorage.setItem(SUPPORT_TICKET_KEY, activeTicketId);
    else window.localStorage.removeItem(SUPPORT_TICKET_KEY);
  }, [activeTicketId]);

  useEffect(() => {
    if (supportEmail) window.localStorage.setItem(SUPPORT_EMAIL_KEY, supportEmail);
  }, [supportEmail]);

  useEffect(() => {
    if (!open) return;
    messagesRef.current?.scrollTo({
      top: messagesRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, open]);

  useEffect(() => {
    if (!open || !activeTicketId) return undefined;
    let ignore = false;
    async function refreshTicket() {
      try {
        const ticket = getAuthToken()
          ? await fetchPatientSupportTicket(activeTicketId)
          : await fetchPublicSupportTicket(activeTicketId, supportEmail);
        if (ignore) return;
        const ticketMessages = (ticket.messages || []).map((entry) => ({
          role: entry.sender_role === "patient" ? "user" : "assistant",
          text: entry.message_text,
        }));
        setMessages(ticketMessages.length ? ticketMessages.slice(-40) : defaultMessages);
        setQuickReplies(ticket.status === "open" ? ["Add more details", "Start over"] : ["Start over"]);
        setReviewPrompt((current) => ({
          ...current,
          visible: ticket.status !== "open" && !ticket.feedback,
          ticketId: ticket.ticket_id,
        }));
      } catch {
        if (!ignore) setActiveTicketId("");
      }
    }
    if (!getAuthToken() && !supportEmail) return undefined;
    refreshTicket();
    const intervalId = window.setInterval(refreshTicket, 15000);
    return () => {
      ignore = true;
      window.clearInterval(intervalId);
    };
  }, [activeTicketId, open, supportEmail]);

  async function submitSupportMessage(message, options = {}) {
    if (!message || busy) return;
    markSupportActivity();
    const isReset = /^start over$|^reset$|^new issue$|^main menu$|^menu$/i.test(message.trim());
    const contactEmail = (options.contactEmail || supportEmail || "").trim().toLowerCase();
    if (!getAuthToken() && !contactEmail && shouldEscalate(message) && !isReset) {
      setPendingAgentMessage(message);
      setAwaitingEmail(true);
      setMessages((current) => [
        ...current,
        { role: "user", text: message },
        { role: "assistant", text: "Please enter your email so customer care can reply and notify you about this ticket." },
      ]);
      setQuickReplies([]);
      setInput("");
      return;
    }
    setInput("");
    if (isReset) {
      setActiveTicketId("");
      setAwaitingEmail(false);
      setPendingAgentMessage("");
      setMessages([{ role: "user", text: message }]);
    } else if (!options.skipEcho) {
      setMessages((current) => [...current, { role: "user", text: message }]);
    }
    setBusy(true);
    try {
      if (activeTicketId && !isReset && (getAuthToken() || contactEmail)) {
        if (getAuthToken()) {
          await sendPatientSupportTicketMessage(activeTicketId, message);
        } else {
          await sendPublicSupportTicketMessage(activeTicketId, message, contactEmail);
        }
        const ticket = getAuthToken()
          ? await fetchPatientSupportTicket(activeTicketId)
          : await fetchPublicSupportTicket(activeTicketId, contactEmail);
        const ticketMessages = (ticket.messages || []).map((entry) => ({
          role: entry.sender_role === "patient" ? "user" : "assistant",
          text: entry.message_text,
        }));
        setMessages(ticketMessages.length ? ticketMessages.slice(-40) : defaultMessages);
        setQuickReplies(ticket.status === "open" ? ["Add more details", "Start over"] : ["Start over"]);
        setReviewPrompt((current) => ({
          ...current,
          visible: ticket.status !== "open" && !ticket.feedback,
          ticketId: ticket.ticket_id,
        }));
        return;
      }
      const payload = {
        message,
        escalate: shouldEscalate(message),
        history: (isReset ? [] : messages).slice(-8),
        contact_email: contactEmail,
      };
      let result;
      if (getAuthToken()) {
        try {
          result = await sendPatientSupportAiMessage(payload);
        } catch {
          result = await sendPublicSupportAiMessage(payload);
        }
      } else {
        result = await sendPublicSupportAiMessage(payload);
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text: result.escalated
            ? `${result.reply}\n\nSupport ticket ${result.ticket.ticket_id} has been sent to customer care.`
            : result.reply,
        },
      ]);
      if (result.escalated && result.ticket?.ticket_id) {
        setActiveTicketId(result.ticket.ticket_id);
        if (contactEmail) setSupportEmail(contactEmail);
        setReviewPrompt({ visible: false, ticketId: "", rating: 5, review: "" });
      }
      setQuickReplies(result.quick_replies?.length ? result.quick_replies : defaultQuickReplies);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", text: error.message || "Unable to reach support assistant right now." },
      ]);
      setQuickReplies(["Try again", "Talk to agent"]);
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    markSupportActivity();
    await submitSupportMessage(input.trim());
  }

  async function submitEmail(event) {
    event.preventDefault();
    markSupportActivity();
    const nextEmail = emailDraft.trim().toLowerCase();
    if (!nextEmail) return;
    setSupportEmail(nextEmail);
    setAwaitingEmail(false);
    const message = pendingAgentMessage || "Talk to agent";
    setPendingAgentMessage("");
    await submitSupportMessage(message, { contactEmail: nextEmail, skipEcho: true });
  }

  async function submitSupportReview(skipped = false) {
    if (!reviewPrompt.ticketId || busy) return;
    markSupportActivity();
    setBusy(true);
    try {
      const payload = skipped
        ? { skipped: true, contact_email: supportEmail }
        : { rating: reviewPrompt.rating, review: reviewPrompt.review, skipped: false, contact_email: supportEmail };
      if (getAuthToken()) {
        await submitPatientSupportTicketFeedback(reviewPrompt.ticketId, payload);
      } else {
        await submitPublicSupportTicketFeedback(reviewPrompt.ticketId, payload);
      }
      setReviewPrompt({ visible: false, ticketId: "", rating: 5, review: "" });
      setActiveTicketId("");
      setQuickReplies(defaultQuickReplies);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: skipped ? "No problem. Thank you for using SynMed support." : "Thank you for rating customer care." },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", text: error.message || "Unable to save customer-care feedback right now." },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function handleQuickReply(reply) {
    markSupportActivity();
    const route = getQuickReplyRoute(reply);
    if (route && (getAuthToken() || route === "/patient/signin")) {
      setOpen(false);
      window.location.assign(route);
      return;
    }
    submitSupportMessage(reply);
  }

  function handleComposerKeyDown(event) {
    const isDesktop = window.matchMedia("(min-width: 861px)").matches;
    if (isDesktop && event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <>
      <button
        className={[
          "customer-support-fab",
          open ? "customer-support-fab--open" : "",
          nudgedUp ? "customer-support-fab--nudged" : "",
        ].filter(Boolean).join(" ")}
        type="button"
        onClick={() => {
          resetIfSupportIdle();
          markSupportActivity();
          setOpen(true);
        }}
        aria-label="Open customer support"
        title="Customer support"
      >
        <span className="customer-support-fab__icon" aria-hidden="true" />
        <span className="customer-support-fab__label">Customer support</span>
      </button>
      {open ? (
        <div className="customer-support-overlay" role="presentation" onMouseDown={() => setOpen(false)}>
          <section
            className={nudgedUp ? "customer-support-panel customer-support-panel--nudged" : "customer-support-panel"}
            role="dialog"
            aria-modal="true"
            aria-label="Customer support assistant"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <span>AI Support</span>
                <h2>Customer Support</h2>
              </div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close support">
                Close
              </button>
            </header>
            <div className="customer-support-messages" ref={messagesRef}>
              {messages.map((message, index) => (
                <article
                  className={
                    message.role === "user"
                      ? "customer-support-bubble customer-support-bubble--user"
                      : "customer-support-bubble"
                  }
                  key={`${message.role}-${index}`}
                >
                  {message.text.split("\n").map((line, lineIndex) => (
                    <p key={`${line}-${lineIndex}`}>{line}</p>
                  ))}
                </article>
              ))}
              {busy ? (
                <article className="customer-support-bubble customer-support-bubble--thinking">
                  <p>Checking that for you...</p>
                </article>
              ) : null}
            </div>
            {quickReplies.length ? (
              <div className="customer-support-quick-replies" aria-label="Suggested support replies">
                {quickReplies.map((reply) => (
                  <button
                    key={reply}
                    type="button"
                    disabled={busy}
                    onClick={() => handleQuickReply(reply)}
                  >
                    {reply}
                  </button>
                ))}
              </div>
            ) : null}
            {awaitingEmail ? (
              <form className="customer-support-email" onSubmit={submitEmail}>
                <input
                  aria-label="Email for customer care reply"
                  type="email"
                  required
                  placeholder="Email for customer care"
                  value={emailDraft}
                  onChange={(event) => {
                    markSupportActivity();
                    setEmailDraft(event.target.value);
                  }}
                  onFocus={markSupportActivity}
                />
                <button className="button button--primary" type="submit" disabled={busy || !emailDraft.trim()}>
                  Continue
                </button>
              </form>
            ) : null}
            {reviewPrompt.visible ? (
              <section className="customer-support-review-card" aria-label="Rate customer care">
                <span>Rate Customer Care</span>
                <strong>How was the support you received?</strong>
                <div className="customer-support-review-stars" aria-label={`Selected rating ${reviewPrompt.rating} stars`}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={value <= reviewPrompt.rating ? "customer-support-review-star customer-support-review-star--active" : "customer-support-review-star"}
                      onClick={() => {
                        markSupportActivity();
                        setReviewPrompt((current) => ({ ...current, rating: value }));
                      }}
                      aria-label={`${value} star${value === 1 ? "" : "s"}`}
                    >
                      ★
                    </button>
                  ))}
                </div>
                <textarea
                  rows="2"
                  placeholder="Optional review"
                  value={reviewPrompt.review}
                  onChange={(event) => {
                    markSupportActivity();
                    setReviewPrompt((current) => ({ ...current, review: event.target.value }));
                  }}
                  onFocus={markSupportActivity}
                />
                <div>
                  <button className="button button--secondary" type="button" onClick={() => submitSupportReview(true)} disabled={busy}>
                    No thanks
                  </button>
                  <button className="button button--primary" type="button" onClick={() => submitSupportReview(false)} disabled={busy}>
                    Submit
                  </button>
                </div>
              </section>
            ) : null}
            <form className="customer-support-composer" onSubmit={sendMessage}>
              <textarea
                placeholder="Tell support what happened"
                rows="2"
                value={input}
                onChange={(event) => {
                  markSupportActivity();
                  setInput(event.target.value);
                }}
                onKeyDown={handleComposerKeyDown}
                onFocus={markSupportActivity}
              />
              <button className="button button--primary" type="submit" disabled={busy || !input.trim()}>
                Send
              </button>
            </form>
          </section>
        </div>
      ) : null}
    </>
  );
}
