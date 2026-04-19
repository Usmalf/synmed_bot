import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  createConsultationEventSource,
  endConsultation,
  fetchConsultationDocuments,
  fetchConsultationStatus,
  fetchConsultationTranscript,
  sendConsultationMessage,
  submitConsultationFeedback,
} from "../api/consultations.js";
import SectionCard from "../components/SectionCard.jsx";
import "../styles/consultation.css";
import "../styles/forms.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function ConsultationPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [reference, setReference] = useState(searchParams.get("reference") || "");
  const [statusState, setStatusState] = useState({
    status: "idle",
    message: "Enter a payment reference to load consultation status.",
    result: null,
  });
  const [transcriptState, setTranscriptState] = useState({
    status: "idle",
    message: "Messages will appear here when a consultation is active.",
    transcript: [],
  });
  const [documentState, setDocumentState] = useState({
    status: "idle",
    message: "Prescriptions and investigations will appear here when the doctor issues them.",
    documents: [],
  });
  const [draftMessage, setDraftMessage] = useState("");
  const [feedbackState, setFeedbackState] = useState({
    visible: false,
    status: "idle",
    message: "Rate and review your doctor before leaving this consultation.",
    rating: 5,
    review: "",
    doctor: null,
  });
  const feedbackSectionRef = useRef(null);

  async function loadStatus(referenceToLoad, options = {}) {
    const { silent = false } = options;
    if (!referenceToLoad.trim()) {
      setStatusState({
        status: "error",
        message: "Payment reference is required.",
        result: null,
      });
      return;
    }

    if (!silent) {
      setStatusState((current) => ({
        status: "loading",
        message: "Loading consultation status...",
        result: current.result,
      }));
    }

    try {
      const result = await fetchConsultationStatus(referenceToLoad.trim());
      setStatusState({
        status: result.submitted ? "success" : "empty",
        message: result.message,
        result,
      });
      if (result.status === "connected" || result.consultation_id) {
        loadTranscript(referenceToLoad.trim());
        loadDocuments(referenceToLoad.trim());
      } else {
        setTranscriptState({
          status: "idle",
          message: "Transcript will load once the consultation is active.",
          transcript: [],
        });
        setDocumentState({
          status: "idle",
          message: "Documents will load once the consultation is active.",
          documents: [],
        });
      }
    } catch {
      setStatusState({
        status: "error",
        message: "Unable to load consultation status right now.",
        result: null,
      });
    }
  }

  async function loadTranscript(referenceToLoad) {
    try {
      const result = await fetchConsultationTranscript(referenceToLoad);
      setTranscriptState({
        status: result.found ? "success" : "empty",
        message: result.message,
        transcript: result.transcript || [],
      });
    } catch {
      setTranscriptState({
        status: "error",
        message: "Unable to load consultation messages right now.",
        transcript: [],
      });
    }
  }

  async function loadDocuments(referenceToLoad) {
    try {
      const result = await fetchConsultationDocuments(referenceToLoad);
      setDocumentState({
        status: result.found ? "success" : "empty",
        message: result.message,
        documents: result.documents || [],
      });
    } catch {
      setDocumentState({
        status: "error",
        message: "Unable to load consultation documents right now.",
        documents: [],
      });
    }
  }

  useEffect(() => {
    if (reference.trim()) {
      loadStatus(reference);
    }
  }, []);

  useEffect(() => {
    if (!reference.trim()) {
      return undefined;
    }

    const source = createConsultationEventSource(reference);
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const nextStatus = payload.status;
        const nextTranscript = payload.transcript;
        const nextDocuments = payload.documents;
        setStatusState({
          status: nextStatus.submitted ? "success" : "empty",
          message: nextStatus.message,
          result: nextStatus,
        });
        setTranscriptState({
          status: nextTranscript.found ? "success" : "empty",
          message: nextTranscript.message,
          transcript: nextTranscript.transcript || [],
        });
        setDocumentState({
          status: nextDocuments?.found ? "success" : "empty",
          message: nextDocuments?.message || "No consultation documents yet.",
          documents: nextDocuments?.documents || [],
        });
      } catch {}
    };

    source.onerror = () => {
      setTranscriptState((current) => ({
        ...current,
        status: current.transcript.length ? current.status : "error",
        message: current.transcript.length
          ? current.message
          : "Live consultation stream disconnected. You can still keep working here.",
      }));
    };

    return () => source.close();
  }, [reference]);

  useEffect(() => {
    if (!reference.trim() || feedbackState.visible) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      loadStatus(reference, { silent: true });
      loadTranscript(reference);
      loadDocuments(reference);
    }, 4000);

    return () => window.clearInterval(intervalId);
  }, [reference, feedbackState.visible]);

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!draftMessage.trim()) {
      return;
    }

    try {
      const result = await sendConsultationMessage({
        reference,
        message_text: draftMessage.trim(),
      });
      setTranscriptState({
        status: "success",
        message: result.message,
        transcript: result.transcript || [],
      });
      setDraftMessage("");
    } catch {
      setTranscriptState((current) => ({
        ...current,
        status: "error",
        message: "Unable to send your message right now.",
      }));
    }
  }

  async function handleEndChat() {
    if (!reference.trim()) {
      return;
    }

    try {
      const result = await endConsultation(reference.trim());
      setStatusState((current) => ({
        ...current,
        status: result.ended ? "success" : "error",
        message: result.message,
      }));
      setFeedbackState({
        visible: result.ended,
        status: "idle",
        message: "Rate and review your doctor before leaving this consultation.",
        rating: 5,
        review: "",
        doctor: result.doctor,
      });
      window.setTimeout(() => {
        feedbackSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 200);
    } catch {
      setStatusState((current) => ({
        ...current,
        status: "error",
        message: "Unable to end the consultation right now.",
      }));
    }
  }

  async function handleFeedbackSubmit(event) {
    event.preventDefault();
    setFeedbackState((current) => ({
      ...current,
      status: "loading",
      message: "Submitting rating and review...",
    }));

    try {
      const result = await submitConsultationFeedback({
        reference,
        rating: feedbackState.rating,
        review: feedbackState.review,
      });
      setFeedbackState((current) => ({
        ...current,
        status: result.saved ? "success" : "error",
        message: result.message,
      }));
      if (result.saved) {
        window.setTimeout(() => {
          navigate("/patient");
        }, 1200);
      }
    } catch {
      setFeedbackState((current) => ({
        ...current,
        status: "error",
        message: "Unable to save rating and review right now.",
      }));
    }
  }

  function renderTranscriptAsset(item) {
    if (!item.asset_url) {
      return null;
    }

    const assetSrc = `${API_BASE_URL}${item.asset_url}`;
    if ((item.asset_type || "").startsWith("image/")) {
      return <img className="transcript-bubble__asset" src={assetSrc} alt="Consultation attachment" />;
    }
    if ((item.asset_type || "").startsWith("video/")) {
      return <video className="transcript-bubble__asset" src={assetSrc} controls />;
    }
    return (
      <a className="transcript-bubble__link" href={assetSrc} target="_blank" rel="noreferrer">
        Open attachment
      </a>
    );
  }

  return (
    <div className="consultation-layout">
      <SectionCard
        title="Consultation"
        subtitle="Stay focused on the active doctor conversation, then close out with rating and review when you are done."
      >
        <div className={`consultation-status consultation-status--${statusState.status}`}>
          <div className="consultation-header">
            <div className="consultation-header__item">
              <span className="consultation-room__eyebrow">Patient</span>
              <strong>
                {statusState.result?.patient?.name || "Patient"}
                {statusState.result?.patient?.hospital_number
                  ? ` | ${statusState.result.patient.hospital_number}`
                  : ""}
              </strong>
            </div>
            <div className="consultation-header__item">
              <span className="consultation-room__eyebrow">Payment Reference</span>
              <strong>{reference || "No reference"}</strong>
            </div>
          </div>

          <div className="consultation-summary-grid">
            <article className="consultation-room__panel">
              <span className="consultation-room__eyebrow">State</span>
              <h3>{statusState.result?.status || "Waiting"}</h3>
            </article>

            <article className="consultation-room__panel">
              <span className="consultation-room__eyebrow">Consultation ID</span>
              <h3>{statusState.result?.consultation_id || "Pending"}</h3>
            </article>

            <article className="consultation-room__panel">
              <span className="consultation-room__eyebrow">Assigned Doctor</span>
              <h3>{statusState.result?.doctor?.name || "Waiting for doctor"}</h3>
              <p>
                {statusState.result?.doctor?.specialty || "No specialty yet"}
                {statusState.result?.doctor
                  ? ` | ${Number(statusState.result.doctor.average_rating || 0).toFixed(1)} stars`
                  : ""}
              </p>
            </article>

            <article className="consultation-room__panel">
              <span className="consultation-room__eyebrow">Flag</span>
              <h3>{statusState.result?.emergency?.is_emergency ? "Urgent" : "Standard"}</h3>
            </article>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title="Live Consultation"
        subtitle="This is the main space for the doctor conversation, including messages and shared media."
      >
        <div className={`consultation-status consultation-status consultation-status--${transcriptState.status}`}>
          <p className="consultation-status__message">{transcriptState.message}</p>
          <div className="transcript-window transcript-window--large">
            {documentState.documents.length ? (
              <div className="transcript-document-strip">
                {documentState.documents.map((item) => (
                  <article key={`${item.kind}-${item.document_id}`} className="transcript-document-card">
                    <div className="document-card__meta">
                      <span className="consultation-room__eyebrow">{item.title}</span>
                      <p>{item.created_at}</p>
                    </div>
                    <div className="document-card__actions">
                      <a
                        className="button button--secondary"
                        href={`${API_BASE_URL}${item.asset_url}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Preview
                      </a>
                      <a
                        className="button button--primary"
                        href={`${API_BASE_URL}${item.asset_url}`}
                        download={`${item.kind}-${item.document_id}.png`}
                      >
                        Download
                      </a>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            {transcriptState.transcript.length ? (
              transcriptState.transcript.map((item, index) => (
                <article
                  key={`${item.created_at}-${index}`}
                  className={
                    item.sender_role === "patient" || item.sender_role === "patient_web"
                      ? "transcript-bubble transcript-bubble--patient"
                      : "transcript-bubble transcript-bubble--doctor"
                  }
                >
                  <span className="transcript-bubble__role">{item.sender_role}</span>
                  {renderTranscriptAsset(item)}
                  <p>{item.message_text}</p>
                  <time className="transcript-bubble__time">{item.created_at}</time>
                </article>
              ))
            ) : (
              <p className="consultation-status__message">No consultation messages recorded yet.</p>
            )}
          </div>

          <form className="form-panel form-panel--inline consultation-compose" onSubmit={handleSendMessage}>
            <label className="form-field form-field--grow">
              <span className="form-field__label">Message</span>
              <input
                className="form-field__input"
                type="text"
                placeholder="Type your update to the doctor..."
                value={draftMessage}
                onChange={(event) => setDraftMessage(event.target.value)}
              />
            </label>
            <button className="button button--primary" type="submit">
              Send Message
            </button>
          </form>

          <div className="consultation-actions">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                if (window.confirm("Are you sure you want to end this consultation?")) {
                  handleEndChat();
                }
              }}
            >
              End Chat
            </button>
          </div>
        </div>
      </SectionCard>

      {feedbackState.visible ? (
        <SectionCard
          title="Rate And Review"
          subtitle="This appears immediately after chat ends so the patient can finish the encounter cleanly."
        >
          <div ref={feedbackSectionRef} className={`consultation-status consultation-status--${feedbackState.status}`}>
            <p className="consultation-status__message">{feedbackState.message}</p>
            {feedbackState.doctor ? (
              <p className="consultation-status__message">
                Doctor: <strong>{feedbackState.doctor.name}</strong>
              </p>
            ) : null}
            <form className="form-panel" onSubmit={handleFeedbackSubmit}>
              <label className="form-field">
                <span className="form-field__label">Rating</span>
                <div className="consultation-stars" aria-label={`Selected rating ${feedbackState.rating} stars`}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button
                      key={value}
                      className={
                        value <= feedbackState.rating
                          ? "consultation-stars__star consultation-stars__star--active"
                          : "consultation-stars__star"
                      }
                      type="button"
                      onClick={() =>
                        setFeedbackState((current) => ({
                          ...current,
                          rating: value,
                        }))
                      }
                    >
                      ★
                    </button>
                  ))}
                </div>
              </label>
              <label className="form-field">
                <span className="form-field__label">Review</span>
                <textarea
                  className="form-field__input form-field__input--textarea"
                  rows="4"
                  placeholder="Share a short review of the consultation..."
                  value={feedbackState.review}
                  onChange={(event) =>
                    setFeedbackState((current) => ({
                      ...current,
                      review: event.target.value,
                    }))
                  }
                />
              </label>
              <button className="button button--primary" type="submit">
                Submit Rating And Review
              </button>
            </form>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
