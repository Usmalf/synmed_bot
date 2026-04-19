import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import StatusPill from "../components/StatusPill.jsx";
import { clearAuthToken, restoreSession } from "../api/auth.js";
import { createInvestigation, createPrescription } from "../api/doctorDocuments.js";
import {
  endDoctorChat,
  fetchDoctorTranscript,
  sendDoctorMessage,
} from "../api/doctorConsultation.js";
import { connectDoctorToPatient, fetchDoctorWorkspace, updateDoctorPresence } from "../api/doctors.js";
import "../styles/doctor.css";
import "../styles/forms.css";

export default function DoctorDashboardPage() {
  const navigate = useNavigate();
  const [authState, setAuthState] = useState({
    status: "loading",
    message: "Checking doctor session...",
    session: null,
  });
  const [workspaceState, setWorkspaceState] = useState({
    status: "idle",
    message: "Doctor workspace will appear after sign-in.",
    result: null,
  });
  const [transcriptState, setTranscriptState] = useState({
    status: "idle",
    message: "Doctor transcript will appear here during an active consultation.",
    transcript: [],
  });
  const [draftMessage, setDraftMessage] = useState("");
  const [documentState, setDocumentState] = useState({
    status: "idle",
    message: "Clinical document tools are ready when a consultation is active.",
    result: null,
  });
  const [prescriptionForm, setPrescriptionForm] = useState({
    diagnosis: "",
    medications_text: "",
    notes: "",
  });
  const [investigationForm, setInvestigationForm] = useState({
    diagnosis: "",
    tests_text: "",
    notes: "",
  });
  const [activeTool, setActiveTool] = useState("prescription");

  async function loadWorkspace() {
    setWorkspaceState({
      status: "loading",
      message: "Loading doctor workspace...",
      result: null,
    });

    try {
      const result = await fetchDoctorWorkspace();
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
      if (result.active_consultation) {
        loadTranscript();
      } else {
        setTranscriptState({
          status: "idle",
          message: "No active consultation transcript available yet.",
          transcript: [],
        });
      }
    } catch (error) {
      setWorkspaceState({
        status: "error",
        message: "Unable to load doctor workspace right now.",
        result: null,
      });
    }
  }

  async function loadTranscript() {
    try {
      const result = await fetchDoctorTranscript();
      setTranscriptState({
        status: result.found ? "success" : "empty",
        message: result.message,
        transcript: result.transcript || [],
      });
    } catch (error) {
      setTranscriptState({
        status: "error",
        message: "Unable to load doctor transcript right now.",
        transcript: [],
      });
    }
  }

  async function handlePresence(action) {
    if (!authState.session?.user?.user_id) {
      return;
    }

    setWorkspaceState((current) => ({
      ...current,
      status: "loading",
      message: `Updating doctor status to ${action}...`,
    }));

    try {
      const result = await updateDoctorPresence({
        doctor_id: authState.session.user.user_id,
        action,
      });
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
    } catch (error) {
      setWorkspaceState({
        status: "error",
        message: "Unable to update doctor presence right now.",
        result: null,
      });
    }
  }

  useEffect(() => {
    if (!authState.session?.user?.user_id || !workspaceState.result?.doctor) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      loadWorkspace();
      if (workspaceState.result?.active_consultation) {
        loadTranscript();
      }
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [authState.session?.user?.user_id, workspaceState.result?.doctor?.status, workspaceState.result?.active_consultation]);

  useEffect(() => {
    async function bootstrapSession() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "doctor") {
          navigate("/doctor/signin", { replace: true });
          return;
        }
        setAuthState({
          status: "success",
          message: session.message,
          session,
        });
        loadWorkspace();
      } catch (error) {
        navigate("/doctor/signin", { replace: true });
      }
    }

    bootstrapSession();
  }, [navigate]);

  async function handleDoctorSendMessage(event) {
    event.preventDefault();
    if (!draftMessage.trim() || !authState.session?.user?.user_id) {
      return;
    }

    try {
      const result = await sendDoctorMessage({
        doctor_id: authState.session.user.user_id,
        message_text: draftMessage.trim(),
      });
      setTranscriptState({
        status: result.sent ? "success" : "empty",
        message: result.message,
        transcript: result.transcript || [],
      });
      setDraftMessage("");
    } catch (error) {
      setTranscriptState((current) => ({
        ...current,
        status: "error",
        message: "Unable to send doctor message right now.",
      }));
    }
  }

  async function handleEndChat() {
    if (!authState.session?.user?.user_id) {
      return;
    }

    try {
      if (!window.confirm("Are you sure you want to end this consultation?")) {
        return;
      }
      const result = await endDoctorChat(authState.session.user.user_id);
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
      setTranscriptState({
        status: "idle",
        message: "Consultation ended. Transcript cleared for the next assignment.",
        transcript: [],
      });
    } catch (error) {
      setWorkspaceState((current) => ({
        ...current,
        status: "error",
        message: "Unable to end the consultation right now.",
      }));
    }
  }

  async function handleConnectPatient(runtimePatientId) {
    try {
      const result = await connectDoctorToPatient(runtimePatientId);
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
      if (result.active_consultation) {
        await loadTranscript();
      }
    } catch (error) {
      setWorkspaceState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to connect to that patient right now.",
      }));
    }
  }

  function handleSignOut() {
    clearAuthToken();
    setAuthState({
      status: "idle",
      message: "Signed out.",
      session: null,
    });
    setWorkspaceState({
      status: "idle",
      message: "Doctor workspace will appear after sign-in.",
      result: null,
    });
    setTranscriptState({
      status: "idle",
      message: "Doctor transcript will appear here during an active consultation.",
      transcript: [],
    });
    setDocumentState({
      status: "idle",
      message: "Clinical document tools are ready when a consultation is active.",
      result: null,
    });
    setDraftMessage("");
    navigate("/doctor/signin");
  }

  async function handleCreatePrescription(event) {
    event.preventDefault();
    try {
      const result = await createPrescription(prescriptionForm);
      setDocumentState({
        status: result.created ? "success" : "error",
        message: result.message,
        result,
      });
      if (result.created) {
        setPrescriptionForm({
          diagnosis: "",
          medications_text: "",
          notes: "",
        });
      }
    } catch (error) {
      setDocumentState({
        status: "error",
        message: error.message || "Unable to create prescription right now.",
        result: null,
      });
    }
  }

  async function handleCreateInvestigation(event) {
    event.preventDefault();
    try {
      const result = await createInvestigation(investigationForm);
      setDocumentState({
        status: result.created ? "success" : "error",
        message: result.message,
        result,
      });
      if (result.created) {
        setInvestigationForm({
          diagnosis: "",
          tests_text: "",
          notes: "",
        });
      }
    } catch (error) {
      setDocumentState({
        status: "error",
        message: error.message || "Unable to create investigation request right now.",
        result: null,
      });
    }
  }

  return (
    <div className="page-stack">
      <SectionCard title="Doctor Workspace" subtitle="Protected web control for verified SynMed doctors.">
        <div className={`doctor-state doctor-state--${authState.status}`}>
          <p className="doctor-state__message">{authState.message}</p>
          {authState.session?.user ? (
            <div className="doctor-toolbar">
              <div className="doctor-toolbar__identity">
                <h3>{authState.session.user.display_name}</h3>
                <p>{authState.session.user.role}</p>
              </div>
              <div className="doctor-toolbar__actions">
                <StatusPill label="Authenticated" tone="success" />
                <Link className="button button--secondary" to="/doctor/account">
                  Open Account
                </Link>
                <button className="button button--secondary" type="button" onClick={handleSignOut}>
                  Log Out
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Presence"
        subtitle="Control whether you are online, offline, or actively occupied with a consultation."
      >
        <div className={`doctor-state doctor-state--${workspaceState.status}`}>
          <p className="doctor-state__message">{workspaceState.message}</p>
          {workspaceState.result?.doctor && authState.session?.user ? (
            <div className="doctor-toolbar">
              <div className="doctor-toolbar__identity">
                <h3>{workspaceState.result.doctor.name}</h3>
                <p>{workspaceState.result.doctor.specialty}</p>
              </div>
              <StatusPill
                label={workspaceState.result.doctor.status}
                tone={
                  workspaceState.result.doctor.status === "busy"
                    ? "danger"
                    : workspaceState.result.doctor.status === "available"
                    ? "success"
                    : "warning"
                }
              />
              <div className="doctor-toolbar__actions">
                <button className="button button--primary" type="button" onClick={() => handlePresence("online")}>
                  Go Online
                </button>
                <button className="button button--secondary" type="button" onClick={() => handlePresence("offline")}>
                  Go Offline
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </SectionCard>

      <SectionCard
        title="Active Consultation"
        subtitle="Current doctor assignment from the shared SynMed runtime, with web messaging control."
      >
        <div className="doctor-state doctor-state--panel">
          {workspaceState.result?.active_consultation ? (
            <>
              <div className="consult-card">
                <h3>
                  {workspaceState.result.active_consultation.hospital_number} |{" "}
                  {workspaceState.result.active_consultation.patient_name}
                </h3>
                <p>{workspaceState.result.active_consultation.summary}</p>
                <div className="consult-card__meta">
                  <StatusPill
                    label={workspaceState.result.active_consultation.source}
                    tone={workspaceState.result.active_consultation.source === "web" ? "success" : "neutral"}
                  />
                  {workspaceState.result.active_consultation.emergency ? (
                    <StatusPill label="Emergency" tone="danger" />
                  ) : null}
                </div>
              </div>

              <div className={`doctor-state doctor-state--${transcriptState.status}`}>
                <p className="doctor-state__message">{transcriptState.message}</p>
                <div className="doctor-transcript">
                  {transcriptState.transcript.length ? (
                    transcriptState.transcript.map((item, index) => (
                      <article
                        key={`${item.created_at}-${index}`}
                        className={
                          item.sender_role === "doctor" || item.sender_role === "doctor_web"
                            ? "doctor-bubble doctor-bubble--doctor"
                            : "doctor-bubble doctor-bubble--patient"
                        }
                      >
                        <span className="doctor-bubble__role">{item.sender_role}</span>
                        <p>{item.message_text}</p>
                        <time className="doctor-bubble__time">{item.created_at}</time>
                      </article>
                    ))
                  ) : (
                    <p className="doctor-state__message">No transcript messages yet.</p>
                  )}
                </div>

                <form className="form-panel form-panel--inline doctor-compose" onSubmit={handleDoctorSendMessage}>
                  <label className="form-field form-field--grow">
                    <span className="form-field__label">Reply to Patient</span>
                    <input
                      className="form-field__input"
                      type="text"
                      placeholder="Type your response..."
                      value={draftMessage}
                      onChange={(event) => setDraftMessage(event.target.value)}
                    />
                  </label>
                  <button className="button button--primary" type="submit">
                    Send
                  </button>
                  <button className="button button--secondary" type="button" onClick={handleEndChat}>
                    End Chat
                  </button>
                </form>
              </div>
            </>
          ) : (
            <p className="doctor-state__message">No active consultation assigned right now.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Waiting Patients"
        subtitle="Emergency flags and queue order from the shared SynMed queue."
      >
        <div className="queue-list">
          {workspaceState.result?.queue?.length ? (
            workspaceState.result.queue.map((item) => (
              <article key={`${item.runtime_patient_id}-${item.hospital_number}`} className="queue-item">
                <div>
                  <h3>
                    {item.hospital_number} | {item.name}
                  </h3>
                  <p>{item.summary}</p>
                </div>
                <div className="queue-item__meta">
                  <StatusPill label={item.source} tone={item.source === "web" ? "success" : "neutral"} />
                  <StatusPill label={item.emergency ? "Emergency" : "Queued"} tone={item.emergency ? "danger" : "neutral"} />
                  <button className="button button--secondary" type="button" onClick={() => handleConnectPatient(item.runtime_patient_id)}>
                    Connect
                  </button>
                </div>
              </article>
            ))
          ) : (
            <p className="doctor-state__message">No waiting patients in queue right now.</p>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title="Clinical Documents"
        subtitle="Open one clinical tool at a time from these fixed controls."
      >
        <div className="doctor-tool-switch">
          <button className={activeTool === "prescription" ? "button button--primary" : "button button--secondary"} type="button" onClick={() => setActiveTool("prescription")}>
            Prescription
          </button>
          <button className={activeTool === "investigation" ? "button button--primary" : "button button--secondary"} type="button" onClick={() => setActiveTool("investigation")}>
            Investigation
          </button>
          <button className={activeTool === "history" ? "button button--primary" : "button button--secondary"} type="button" onClick={() => setActiveTool("history")}>
            Patient History
          </button>
          <button className={activeTool === "followup" ? "button button--primary" : "button button--secondary"} type="button" onClick={() => setActiveTool("followup")}>
            Book Appointment / Follow-Up
          </button>
        </div>

        <div className={`doctor-state doctor-state--${documentState.status}`}>
          <p className="doctor-state__message">{documentState.message}</p>
          {documentState.result?.filename ? (
            <p className="doctor-state__message">
              Latest document: {documentState.result.filename}
            </p>
          ) : null}
          {documentState.result?.preview_text ? (
            <pre className="doctor-document-preview">{documentState.result.preview_text}</pre>
          ) : null}
        </div>

        <div className="doctor-doc-grid">
          {activeTool === "prescription" ? (
          <form className="form-panel doctor-doc-form" onSubmit={handleCreatePrescription}>
            <h3>Create Prescription</h3>
            <label className="form-field">
              <span className="form-field__label">Diagnosis</span>
              <input
                className="form-field__input"
                type="text"
                value={prescriptionForm.diagnosis}
                onChange={(event) =>
                  setPrescriptionForm((current) => ({ ...current, diagnosis: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Medications</span>
              <textarea
                className="form-field__input form-field__input--textarea"
                rows="5"
                placeholder="1. Tablet Paracetamol 500mg twice daily for 5 days"
                value={prescriptionForm.medications_text}
                onChange={(event) =>
                  setPrescriptionForm((current) => ({ ...current, medications_text: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Notes</span>
              <textarea
                className="form-field__input form-field__input--textarea"
                rows="3"
                value={prescriptionForm.notes}
                onChange={(event) =>
                  setPrescriptionForm((current) => ({ ...current, notes: event.target.value }))
                }
              />
            </label>
            <button className="button button--primary" type="submit">
              Create Prescription
            </button>
          </form>
          ) : null}

          {activeTool === "investigation" ? (
          <form className="form-panel doctor-doc-form" onSubmit={handleCreateInvestigation}>
            <h3>Create Investigation</h3>
            <label className="form-field">
              <span className="form-field__label">Diagnosis</span>
              <input
                className="form-field__input"
                type="text"
                value={investigationForm.diagnosis}
                onChange={(event) =>
                  setInvestigationForm((current) => ({ ...current, diagnosis: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Investigations</span>
              <textarea
                className="form-field__input form-field__input--textarea"
                rows="5"
                placeholder="Full blood count&#10;Urinalysis&#10;Malaria parasite test"
                value={investigationForm.tests_text}
                onChange={(event) =>
                  setInvestigationForm((current) => ({ ...current, tests_text: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Notes</span>
              <textarea
                className="form-field__input form-field__input--textarea"
                rows="3"
                value={investigationForm.notes}
                onChange={(event) =>
                  setInvestigationForm((current) => ({ ...current, notes: event.target.value }))
                }
              />
            </label>
            <button className="button button--primary" type="submit">
              Create Investigation
            </button>
          </form>
          ) : null}

          {activeTool === "history" ? (
            <div className="doctor-doc-form">
              <h3>Patient History</h3>
              <p>Patient history stays separate from prescribing so the doctor can focus on one task at a time.</p>
            </div>
          ) : null}

          {activeTool === "followup" ? (
            <div className="doctor-doc-form">
              <h3>Book Appointment / Follow-Up</h3>
              <p>Appointment and follow-up actions are separated here instead of mixing with document writing.</p>
            </div>
          ) : null}
        </div>
      </SectionCard>
    </div>
  );
}
