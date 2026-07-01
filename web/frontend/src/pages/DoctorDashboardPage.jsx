import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, Navigate, useNavigate } from "react-router-dom";
import BrandedLoader from "../components/BrandedLoader.jsx";
import SectionCard from "../components/SectionCard.jsx";
import StatusPill from "../components/StatusPill.jsx";
import { clearAuthToken, clearPendingLogin, restoreSession } from "../api/auth.js";
import { createInvestigation, createMedicalReport, createPrescription, saveDoctorHistory } from "../api/doctorDocuments.js";
import {
  acceptDoctorCall,
  endDoctorCall,
  endDoctorChat,
  fetchDoctorTranscript,
  rejectDoctorCall,
  sendDoctorAttachment,
  sendDoctorMessage,
  sendDoctorCallCandidate,
  startDoctorCall,
} from "../api/doctorConsultation.js";
import {
  connectDoctorToPatient,
  fetchDoctorWorkspace,
} from "../api/doctors.js";
import "../styles/doctor.css";
import "../styles/forms.css";

const quickTools = [
  { key: "prescription", label: "Prescription" },
  { key: "investigation", label: "Investigation" },
  { key: "medicalReport", label: "Medical Report" },
  { key: "history", label: "Patient History" },
  { key: "followup", label: "Book Appointment / Follow-Up" },
];

const DOCTOR_CONSULTATION_VIEW_KEY = "synmed_doctor_consultation_view_active";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const QUEUE_PAGE_SIZE = 3;

function historyDraftKey(consultationId) {
  return consultationId ? `doctor-history-draft:${consultationId}` : "";
}

function prescriptionDraftKey(consultationId) {
  return consultationId ? `doctor-prescription-draft:${consultationId}` : "";
}

function investigationDraftKey(consultationId) {
  return consultationId ? `doctor-investigation-draft:${consultationId}` : "";
}

function formatSavedTime(timestamp) {
  if (!timestamp) {
    return "";
  }

  try {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function formatDoctorDisplayName(name) {
  if (!name) {
    return "Doctor";
  }

  if (/^dr\.?\s/i.test(name)) {
    return name;
  }

  return `Dr. ${name}`;
}

function getDisplayInitials(name) {
  const normalized = (name || "").replace(/^dr\.?\s+/i, "").trim();
  if (!normalized) {
    return "P";
  }

  const parts = normalized.split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function shouldAutoFocusChatComposer() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(min-width: 861px) and (pointer: fine)").matches
  );
}

function focusChatComposer(input) {
  if (!input) {
    return;
  }

  window.setTimeout(() => {
    try {
      input.focus({ preventScroll: true });
    } catch {
      input.focus();
    }

    const cursorPosition = input.value.length;
    input.setSelectionRange?.(cursorPosition, cursorPosition);
  }, 80);
}

function VoiceNoteIcon() {
  return (
    <svg className="chat-tool-button__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M12 3.2a3.35 3.35 0 0 0-3.35 3.35v5.2a3.35 3.35 0 0 0 6.7 0v-5.2A3.35 3.35 0 0 0 12 3.2Z" />
      <path d="M5.7 10.35v1.35a6.3 6.3 0 0 0 12.6 0v-1.35" />
      <path d="M12 18v3" />
      <path d="M8.05 21h7.9" />
    </svg>
  );
}

function SendMessageIcon() {
  return (
    <svg className="chat-tool-button__icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="m4 4 16 8-16 8 3-8-3-8Z" />
      <path d="M7 12h13" />
    </svg>
  );
}
function formatChatTimestamp(timestamp) {
  if (!timestamp) {
    return "";
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }

  const now = new Date();
  const isSameDay = parsed.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday = parsed.toDateString() === yesterday.toDateString();
  const timeText = parsed.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });

  if (isSameDay) {
    return timeText;
  }

  if (isYesterday) {
    return `Yesterday, ${timeText}`;
  }

  return `${parsed.toLocaleDateString([], {
    day: "numeric",
    month: "short",
  })}, ${timeText}`;
}

function formatCallDuration(startedAt, endedAt) {
  const start = Date.parse(startedAt || "");
  const end = Date.parse(endedAt || "");
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) {
    return "under a minute";
  }

  const totalSeconds = Math.max(1, Math.round((end - start) / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatRecordingDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (!value) {
    return "File";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(value < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function getCallDurationAnchor(callState) {
  return callState?.connected_at || callState?.started_at || "";
}

function getDoctorTranscriptSenderLabel(senderRole, doctorName, patientName) {
  if (senderRole === "doctor" || senderRole === "doctor_web") {
    return formatDoctorDisplayName(doctorName);
  }

  if (senderRole === "patient" || senderRole === "patient_web") {
    return patientName || "Patient";
  }

  return senderRole || "Participant";
}

function createPeerConnection() {
  return new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  });
}

function renderDoctorTranscriptAsset(item, previewedAssets, setPreviewedAssets) {
  if (!item.asset_url) {
    return null;
  }

  const assetSrc = `${API_BASE_URL}${item.asset_url}`;
  const assetKey = `${item.created_at || ""}-${item.asset_url}`;
  const isPreviewed = previewedAssets.has(assetKey);
  const isImage = (item.asset_type || "").startsWith("image/");
  const isVideo = (item.asset_type || "").startsWith("video/");
  const isAudio = (item.asset_type || "").startsWith("audio/");
  const fileLabel = item.message_text || (isImage ? "Photo" : isVideo ? "Video" : isAudio ? "Voice message" : "Attachment");

  if ((isImage || isVideo) && !isPreviewed) {
    return (
      <button
        className="transcript-attachment-card"
        type="button"
        onClick={() => setPreviewedAssets((current) => new Set([...current, assetKey]))}
      >
        <span
          className="transcript-attachment-card__preview"
          style={isImage ? { backgroundImage: `url("${assetSrc}")` } : undefined}
        >
          {isVideo ? <video src={assetSrc} muted playsInline preload="metadata" /> : null}
          <span className="transcript-attachment-card__scrim" />
        </span>
        <span className="transcript-attachment-card__meta">
          <span className="transcript-attachment-card__name">{fileLabel}</span>
          <span className="transcript-attachment-card__download" aria-hidden="true">{"\u2B07"}</span>
          <span className="transcript-attachment-card__size">{formatFileSize(item.asset_size)}</span>
        </span>
      </button>
    );
  }

  if (isImage) {
    return (
      <div className="transcript-attachment-preview">
        <a className="transcript-attachment-preview__open" href={assetSrc} target="_blank" rel="noreferrer">
          <img className="transcript-bubble__asset" src={assetSrc} alt="Consultation attachment" />
        </a>
        <a className="transcript-bubble__link" href={assetSrc} download>
          Save to device
        </a>
      </div>
    );
  }
  if (isVideo) {
    return (
      <div className="transcript-attachment-preview">
        <video className="transcript-bubble__asset" src={assetSrc} controls />
        <a className="transcript-bubble__link" href={assetSrc} target="_blank" rel="noreferrer">
          Open attachment
        </a>
        <a className="transcript-bubble__link" href={assetSrc} download>
          Save to device
        </a>
      </div>
    );
  }
  if (isAudio) {
    return <audio className="transcript-bubble__audio" src={assetSrc} controls />;
  }
  return (
    <a className="transcript-bubble__link" href={assetSrc} target="_blank" rel="noreferrer">
      Open attachment
    </a>
  );
}

function getDefaultCallWindowPosition() {
  const width = Math.min(220, Math.max(160, window.innerWidth * 0.28));
  return {
    x: Math.max(12, window.innerWidth - width - 20),
    y: Math.max(88, window.innerHeight - 220),
  };
}

function seedNumberedList(value) {
  return value.trim() ? value : "1. ";
}

export default function DoctorDashboardPage() {
  const navigate = useNavigate();
  const autosaveTimeoutRef = useRef(null);
  const transcriptWindowRef = useRef(null);
  const diagnosisPanelRef = useRef(null);
  const callOverlayRef = useRef(null);
  const callDragStateRef = useRef(null);
  const previousCallStatusRef = useRef(null);
  const peerConnectionRef = useRef(null);
  const localStreamRef = useRef(null);
  const remoteStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const ringtoneIntervalRef = useRef(null);
  const ringtoneAudioContextRef = useRef(null);
  const seenCandidateKeysRef = useRef(new Set());
  const attachmentInputRef = useRef(null);
  const messageInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const voiceChunksRef = useRef([]);
  const voiceStartedAtRef = useRef(0);
  const voiceElapsedBeforePauseRef = useRef(0);
  const composerDockRef = useRef(null);
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
  const [activityEvents, setActivityEvents] = useState([]);
  const [queuePage, setQueuePage] = useState(1);
  const [draftMessage, setDraftMessage] = useState("");
  const [attachmentState, setAttachmentState] = useState({ status: "idle", message: "" });
  const [previewedAssets, setPreviewedAssets] = useState(() => new Set());
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voicePaused, setVoicePaused] = useState(false);
  const [voiceElapsedSeconds, setVoiceElapsedSeconds] = useState(0);
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
  const [prescriptionDraftState, setPrescriptionDraftState] = useState({
    status: "idle",
    message: "Prescription draft will autosave while you type.",
    savedAt: "",
  });
  const [investigationForm, setInvestigationForm] = useState({
    diagnosis: "",
    tests_text: "",
    notes: "",
  });
  const [medicalReportForm, setMedicalReportForm] = useState({
    diagnosis: "",
    report_note: "",
  });
  const [investigationDraftState, setInvestigationDraftState] = useState({
    status: "idle",
    message: "Investigation draft will autosave while you type.",
    savedAt: "",
  });
  const [historyForm, setHistoryForm] = useState("");
  const [historySaveState, setHistorySaveState] = useState({
    status: "idle",
    message: "History notes will autosave while you type.",
    savedAt: "",
  });
  const [activeTool, setActiveTool] = useState(null);
  const [clinicalToolsOpen, setClinicalToolsOpen] = useState(false);
  const [patientSummaryOpen, setPatientSummaryOpen] = useState(false);
  const [composerDockHeight, setComposerDockHeight] = useState(180);
  const [showConsultationView, setShowConsultationView] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.sessionStorage.getItem(DOCTOR_CONSULTATION_VIEW_KEY) === "true";
  });
  const [consultationDiagnosis, setConsultationDiagnosis] = useState("");
  const [diagnosisPanelOpen, setDiagnosisPanelOpen] = useState(false);
  const [callUiState, setCallUiState] = useState({
    status: "idle",
    message: "",
    localMediaReady: false,
    audioMuted: false,
    videoDisabled: false,
  });
  const [callWindowMinimized, setCallWindowMinimized] = useState(false);
  const autoExpandedVideoCallRef = useRef("");
  const [callWindowPosition, setCallWindowPosition] = useState({ x: null, y: null });
  const [callTimerNow, setCallTimerNow] = useState(() => Date.now());

  useEffect(() => {
    if (!draftMessage && messageInputRef.current) {
      messageInputRef.current.style.height = "48px";
      messageInputRef.current.style.overflowY = "hidden";
    }
  }, [draftMessage]);

  useLayoutEffect(() => {
    if (!showConsultationView || !composerDockRef.current) {
      return undefined;
    }

    const updateDockHeight = () => {
      setComposerDockHeight(Math.ceil(composerDockRef.current?.getBoundingClientRect().height || 180));
    };
    const resizeObserver = new ResizeObserver(updateDockHeight);
    resizeObserver.observe(composerDockRef.current);
    updateDockHeight();

    return () => resizeObserver.disconnect();
  }, [showConsultationView, diagnosisPanelOpen, voiceRecording]);

  function appendActivityEvent(event) {
    setActivityEvents((current) => [
      ...current,
      {
        id: `${event.kind}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
        kind: event.kind,
        align: event.align || "center",
        title: event.title,
        body: event.body,
        created_at: event.created_at || new Date().toISOString(),
      },
    ]);
  }

  useEffect(() => {
    if (!voiceRecording || voicePaused) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      const activeSeconds = Math.floor((Date.now() - voiceStartedAtRef.current) / 1000);
      setVoiceElapsedSeconds(voiceElapsedBeforePauseRef.current + Math.max(0, activeSeconds));
    }, 250);

    return () => window.clearInterval(intervalId);
  }, [voiceRecording, voicePaused]);

  async function loadWorkspace(options = {}) {
    const { silent = false } = options;
    if (!silent) {
      setWorkspaceState((current) => ({
        status: current.result ? current.status : "loading",
        message: current.result ? current.message : "Loading doctor workspace...",
        result: current.result,
      }));
    }

    try {
      const result = await fetchDoctorWorkspace();
      const existingConsultation = workspaceState.result?.active_consultation;
      if (
        silent &&
        showConsultationView &&
        existingConsultation?.consultation_id &&
        !result.active_consultation?.consultation_id
      ) {
        const transcriptResult = await loadTranscript();
        if (transcriptResult?.found && transcriptResult.consultation_id === existingConsultation.consultation_id) {
          const nextResult = {
            ...result,
            active_consultation: existingConsultation,
            call: transcriptResult.call || result.call,
          };
          setWorkspaceState({
            status: nextResult.found ? "success" : "empty",
            message: nextResult.message,
            result: nextResult,
          });
          window.dispatchEvent(new CustomEvent("synmed:doctor-presence-updated", { detail: nextResult }));
          return;
        }
      }
      const nextResult = result;
      setWorkspaceState({
        status: nextResult.found ? "success" : "empty",
        message: nextResult.message,
        result: nextResult,
      });
      window.dispatchEvent(new CustomEvent("synmed:doctor-presence-updated", { detail: nextResult }));
      if (nextResult.active_consultation) {
        loadTranscript();
      } else {
        setShowConsultationView(false);
        setTranscriptState({
          status: "idle",
          message: "No active consultation transcript available yet.",
          transcript: [],
        });
      }
    } catch {
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
      return result;
    } catch {
      setTranscriptState({
        status: "error",
        message: "Unable to load doctor transcript right now.",
        transcript: [],
      });
      return null;
    }
  }

  useEffect(() => {
    if (!authState.session?.user?.user_id || !workspaceState.result?.doctor) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      loadWorkspace({ silent: true });
      if (workspaceState.result?.active_consultation) {
        loadTranscript();
      }
    }, 5000);

    return () => window.clearInterval(intervalId);
  }, [
    authState.session?.user?.user_id,
    workspaceState.result?.doctor?.status,
    workspaceState.result?.active_consultation,
    showConsultationView,
  ]);

  useEffect(() => {
    function handlePresenceUpdate(event) {
      if (!event.detail?.doctor) {
        loadWorkspace({ silent: true });
        return;
      }

      setWorkspaceState({
        status: event.detail.found ? "success" : "empty",
        message: event.detail.message || "Doctor presence updated.",
        result: event.detail,
      });
    }

    window.addEventListener("synmed:doctor-presence-updated", handlePresenceUpdate);
    return () => window.removeEventListener("synmed:doctor-presence-updated", handlePresenceUpdate);
  }, []);

  useEffect(() => {
    async function bootstrapSession() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "doctor") {
          setAuthState({
            status: "unauthenticated",
            message: "Sign in or register your doctor account to access the clinical workspace.",
            session: null,
          });
          return;
        }
        setAuthState({
          status: "success",
          message: session.message,
          session,
        });
        window.dispatchEvent(new CustomEvent("synmed:session-updated", { detail: session }));
        loadWorkspace();
      } catch {
        setAuthState({
          status: "unauthenticated",
          message: "Sign in or register your doctor account to access the clinical workspace.",
          session: null,
        });
      }
    }

    bootstrapSession();
  }, [navigate]);

  useEffect(() => {
    const shouldFlagActive = Boolean(showConsultationView);

    if (shouldFlagActive) {
      window.sessionStorage.setItem(DOCTOR_CONSULTATION_VIEW_KEY, "true");
    } else {
      window.sessionStorage.removeItem(DOCTOR_CONSULTATION_VIEW_KEY);
    }

    window.dispatchEvent(new Event("synmed:doctor-consultation-view"));

    return () => {
      if (!shouldFlagActive) {
        window.sessionStorage.removeItem(DOCTOR_CONSULTATION_VIEW_KEY);
        window.dispatchEvent(new Event("synmed:doctor-consultation-view"));
      }
    };
  }, [workspaceState.result?.active_consultation?.consultation_id, showConsultationView]);

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
    } catch {
      setTranscriptState((current) => ({
        ...current,
        status: "error",
        message: "Unable to send doctor message right now.",
      }));
    }
  }

  function handleChatComposerKeyDown(event) {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent?.isComposing ||
      !shouldAutoFocusChatComposer()
    ) {
      return;
    }

    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  async function uploadDoctorAttachment(file) {
    if (!file || !activeConsultation?.consultation_id) {
      return;
    }

    try {
      setAttachmentState({ status: "loading", message: "Sending attachment..." });
      const result = await sendDoctorAttachment(file);
      setTranscriptState({
        status: result.sent ? "success" : "empty",
        message: result.message,
        transcript: result.transcript || [],
      });
      setAttachmentState({ status: "success", message: result.message });
    } catch {
      setAttachmentState({ status: "error", message: "Unable to send attachment right now." });
    }
  }

  function handleDoctorAttachmentChange(event) {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    if (file) {
      uploadDoctorAttachment(file);
    }
  }

  async function handleDoctorVoiceMessage() {
    if (voiceRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      voiceChunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) {
          voiceChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        setVoiceRecording(false);
        setVoicePaused(false);
        setVoiceElapsedSeconds(0);
        voiceStartedAtRef.current = 0;
        voiceElapsedBeforePauseRef.current = 0;
        const blob = new Blob(voiceChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (blob.size) {
          uploadDoctorAttachment(new File([blob], `voice-message-${Date.now()}.webm`, { type: blob.type }));
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      voiceStartedAtRef.current = Date.now();
      voiceElapsedBeforePauseRef.current = 0;
      setVoiceElapsedSeconds(0);
      setVoicePaused(false);
      setVoiceRecording(true);
    } catch {
      setAttachmentState({ status: "error", message: "Unable to start voice recording right now." });
    }
  }

  function handleDoctorVoicePauseToggle() {
    const recorder = mediaRecorderRef.current;
    if (!recorder || !voiceRecording) {
      return;
    }

    if (voicePaused) {
      recorder.resume();
      voiceStartedAtRef.current = Date.now();
      setVoicePaused(false);
      return;
    }

    recorder.pause();
    voiceElapsedBeforePauseRef.current = voiceElapsedSeconds;
    setVoicePaused(true);
  }

  async function handleEndChat() {
    if (!authState.session?.user?.user_id) {
      return;
    }

    try {
      if (!window.confirm("Are you sure you want to end this consultation?")) {
        return;
      }
      const consultationDraftKey = historyDraftKey(activeConsultation?.consultation_id);
      const prescriptionDraftStorageKey = prescriptionDraftKey(activeConsultation?.consultation_id);
      const investigationDraftStorageKey = investigationDraftKey(activeConsultation?.consultation_id);
      if (autosaveTimeoutRef.current) {
        window.clearTimeout(autosaveTimeoutRef.current);
        autosaveTimeoutRef.current = null;
      }
      const result = await endDoctorChat(authState.session.user.user_id);
      if (consultationDraftKey) {
        window.localStorage.removeItem(consultationDraftKey);
      }
      if (prescriptionDraftStorageKey) {
        window.localStorage.removeItem(prescriptionDraftStorageKey);
      }
      if (investigationDraftStorageKey) {
        window.localStorage.removeItem(investigationDraftStorageKey);
      }
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
      window.dispatchEvent(new CustomEvent("synmed:doctor-presence-updated", { detail: result }));
      setShowConsultationView(false);
      setTranscriptState({
        status: "idle",
        message: "Consultation ended. Transcript cleared for the next assignment.",
        transcript: [],
      });
      setPrescriptionForm({
        diagnosis: "",
        medications_text: "",
        notes: "",
      });
      setInvestigationForm({
        diagnosis: "",
        tests_text: "",
        notes: "",
      });
      setPrescriptionDraftState({
        status: "idle",
        message: "Prescription draft will autosave while you type.",
        savedAt: "",
      });
      setInvestigationDraftState({
        status: "idle",
        message: "Investigation draft will autosave while you type.",
        savedAt: "",
      });
      navigate("/doctor", { replace: true });
    } catch {
      setWorkspaceState((current) => ({
        ...current,
        status: "error",
        message: "Unable to end the consultation right now.",
      }));
    }
  }

  async function handleConnectPatient(runtimePatientId) {
    if (doctor?.status !== "available") {
      setWorkspaceState((current) => ({
        ...current,
        status: current.result ? "success" : current.status,
        message: "Go online before connecting to a queued patient.",
      }));
      return;
    }

    try {
      setWorkspaceState((current) => ({
        ...current,
        status: "loading",
        message: "Connecting to selected patient...",
      }));
      const result = await connectDoctorToPatient(runtimePatientId);
      setWorkspaceState({
        status: result.found ? "success" : "empty",
        message: result.message,
        result,
      });
      window.dispatchEvent(new CustomEvent("synmed:doctor-presence-updated", { detail: result }));
      if (result.active_consultation) {
        setShowConsultationView(true);
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
    if (autosaveTimeoutRef.current) {
      window.clearTimeout(autosaveTimeoutRef.current);
      autosaveTimeoutRef.current = null;
    }
    clearAuthToken();
    clearPendingLogin();
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
    setPrescriptionForm({
      diagnosis: "",
      medications_text: "",
      notes: "",
    });
    setInvestigationForm({
      diagnosis: "",
      tests_text: "",
      notes: "",
    });
    setHistoryForm("");
    setPrescriptionDraftState({
      status: "idle",
      message: "Prescription draft will autosave while you type.",
      savedAt: "",
    });
    setInvestigationDraftState({
      status: "idle",
      message: "Investigation draft will autosave while you type.",
      savedAt: "",
    });
    setHistorySaveState({
      status: "idle",
      message: "History notes will autosave while you type.",
      savedAt: "",
    });
    navigate("/", { replace: true });
  }

  function handleDiagnosisChange(value) {
    setConsultationDiagnosis(value);
    setPrescriptionForm((current) => ({ ...current, diagnosis: value }));
    setInvestigationForm((current) => ({ ...current, diagnosis: value }));
    setMedicalReportForm((current) => ({ ...current, diagnosis: value }));
  }

  function handleNumberedListFocus(value, setter, field) {
    if (value.trim()) {
      return;
    }
    setter((current) => ({
      ...current,
      [field]: seedNumberedList(current[field] || ""),
    }));
  }

  function handleNumberedListKeyDown(event, value, setter, field) {
    if (event.key !== "Enter") {
      return;
    }

    event.preventDefault();
    const textarea = event.currentTarget;
    const selectionStart = textarea.selectionStart ?? value.length;
    const beforeCursor = value.slice(0, selectionStart);
    const afterCursor = value.slice(selectionStart);
    const lines = beforeCursor.split("\n");
    const currentLine = lines[lines.length - 1] || "";
    const match = currentLine.match(/^\s*(\d+)\.\s?/);
    const nextNumber = match ? Number(match[1]) + 1 : 2;
    const insertion = `\n${nextNumber}. `;
    const nextValue = `${beforeCursor}${insertion}${afterCursor}`;

    setter((current) => ({
      ...current,
      [field]: nextValue,
    }));

    window.requestAnimationFrame(() => {
      const nextCursor = selectionStart + insertion.length;
      textarea.selectionStart = nextCursor;
      textarea.selectionEnd = nextCursor;
    });
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
        appendActivityEvent({
          kind: "prescription",
          title: "Prescription created",
          body: result.filename
            ? `${result.filename} was issued during this consultation.`
            : "A prescription was issued during this consultation.",
          created_at: new Date().toISOString(),
        });
        if (activeConsultation?.consultation_id) {
          window.localStorage.removeItem(prescriptionDraftKey(activeConsultation.consultation_id));
        }
        setPrescriptionForm({
          diagnosis: "",
          medications_text: "",
          notes: "",
        });
        setPrescriptionDraftState({
          status: "idle",
          message: "Prescription draft will autosave while you type.",
          savedAt: "",
        });
        setActiveTool(null);
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
        appendActivityEvent({
          kind: "investigation",
          title: "Investigation created",
          body: result.filename
            ? `${result.filename} was issued during this consultation.`
            : "An investigation request was issued during this consultation.",
          created_at: new Date().toISOString(),
        });
        if (activeConsultation?.consultation_id) {
          window.localStorage.removeItem(investigationDraftKey(activeConsultation.consultation_id));
        }
        setInvestigationForm({
          diagnosis: "",
          tests_text: "",
          notes: "",
        });
        setInvestigationDraftState({
          status: "idle",
          message: "Investigation draft will autosave while you type.",
          savedAt: "",
        });
        setActiveTool(null);
      }
    } catch (error) {
      setDocumentState({
        status: "error",
        message: error.message || "Unable to create investigation request right now.",
        result: null,
      });
    }
  }

  async function handleCreateMedicalReport(event) {
    event.preventDefault();
    try {
      const result = await createMedicalReport(medicalReportForm);
      setDocumentState({
        status: result.created ? "success" : "error",
        message: result.message,
        result,
      });
      if (result.created) {
        appendActivityEvent({
          kind: "medical_report",
          title: "Medical report created",
          body: result.filename
            ? `${result.filename} was issued during this consultation.`
            : "A medical report was issued during this consultation.",
          created_at: new Date().toISOString(),
        });
        setMedicalReportForm({
          diagnosis: "",
          report_note: "",
        });
        setActiveTool(null);
      }
    } catch (error) {
      setDocumentState({
        status: "error",
        message: error.message || "Unable to create medical report right now.",
        result: null,
      });
    }
  }

  async function persistHistoryNote(noteText, { silent = false } = {}) {
    const trimmed = noteText.trim();
    if (!activeConsultation?.consultation_id) {
      return false;
    }

    if (!silent) {
      setHistorySaveState({
        status: "saving",
        message: "Saving history...",
        savedAt: "",
      });
    }

    try {
      const result = await saveDoctorHistory({ notes: trimmed });
      setHistorySaveState({
        status: "saved",
        message: result.message || "Patient history saved.",
        savedAt: new Date().toISOString(),
      });
      setWorkspaceState((current) =>
        current.result?.active_consultation?.consultation_id === result.consultation_id
          ? {
              ...current,
              result: {
                ...current.result,
                active_consultation: {
                  ...current.result.active_consultation,
                  summary: trimmed || "No symptoms recorded",
                  saved_history: trimmed,
                },
              },
            }
          : current,
      );
      return true;
    } catch (error) {
      setHistorySaveState({
        status: "error",
        message: error.message || "Unable to save history right now. Your draft is still kept on this device.",
        savedAt: "",
      });
      return false;
    }
  }

  async function handleSaveHistory(event) {
    event.preventDefault();
    await persistHistoryNote(historyForm);
  }

  const doctor = workspaceState.result?.doctor;
  const activeConsultation = workspaceState.result?.active_consultation;
  const queue = workspaceState.result?.queue || [];
  const queuePageCount = Math.max(1, Math.ceil(queue.length / QUEUE_PAGE_SIZE));
  const safeQueuePage = Math.min(queuePage, queuePageCount);
  const visibleQueue = queue.slice(
    (safeQueuePage - 1) * QUEUE_PAGE_SIZE,
    safeQueuePage * QUEUE_PAGE_SIZE,
  );
  const selectedTool = quickTools.find((tool) => tool.key === activeTool) || null;
  const doctorOnline = doctor?.status === "available";
  const doctorBusy = doctor?.status === "busy";
  const doctorStatusLabel = doctorBusy ? "busy" : doctorOnline ? "online" : "offline";
  const doctorCanConnect = doctorOnline && !activeConsultation?.consultation_id;
  const doctorInSession = Boolean(activeConsultation?.consultation_id);
  const currentCall = workspaceState.result?.call || null;
  const doctorAcceptingIncomingCall =
    currentCall?.status === "ringing" &&
    currentCall?.initiated_by === "patient" &&
    ["connecting", "active"].includes(callUiState.status);
  const doctorEffectiveActiveCall = currentCall?.status === "active" || callUiState.status === "active";
  const doctorHasCallInProgress =
    ["ringing", "active", "connecting"].includes(currentCall?.status || "") ||
    ["ringing", "active", "connecting", "starting"].includes(callUiState.status);
  const doctorHasLocalVideoTrack = Boolean(localStreamRef.current?.getVideoTracks().length);
  const doctorShowVideoCallLayout = currentCall?.call_type === "video" || doctorHasLocalVideoTrack;
  const doctorShowSelfPreviewAsMain = doctorShowVideoCallLayout && !doctorEffectiveActiveCall;
  const doctorActiveVideoControlsOnly = doctorShowVideoCallLayout && doctorEffectiveActiveCall;
  const doctorCallTimerLabel =
    doctorEffectiveActiveCall && getCallDurationAnchor(currentCall)
      ? formatCallDuration(getCallDurationAnchor(currentCall), new Date(callTimerNow).toISOString())
      : "";

  useEffect(() => {
    const callKey = currentCall?.consultation_id || activeConsultation?.consultation_id || "";
    if (
      currentCall?.call_type === "video" &&
      doctorEffectiveActiveCall &&
      autoExpandedVideoCallRef.current !== callKey
    ) {
      autoExpandedVideoCallRef.current = callKey;
      setCallWindowMinimized(false);
    }
    if (!doctorEffectiveActiveCall) {
      autoExpandedVideoCallRef.current = "";
    }
  }, [activeConsultation?.consultation_id, currentCall?.call_type, currentCall?.consultation_id, doctorEffectiveActiveCall]);

  useEffect(() => {
    if (
      !shouldAutoFocusChatComposer() ||
      !showConsultationView ||
      !doctorInSession ||
      activeTool ||
      voiceRecording
    ) {
      return;
    }

    focusChatComposer(messageInputRef.current);
  }, [
    activeConsultation?.consultation_id,
    activeTool,
    doctorInSession,
    showConsultationView,
    voiceRecording,
  ]);

  const doctorTimelineItems = [
    ...(transcriptState.transcript || []).map((item, index) => ({
      key: `message-${item.created_at || "unknown"}-${index}`,
      type: "message",
      created_at: item.created_at,
      payload: item,
    })),
    ...activityEvents.map((item) => ({
      key: item.id,
      type: "activity",
      created_at: item.created_at,
      payload: item,
    })),
  ].sort((left, right) => {
    const leftTime = Date.parse(left.created_at || "") || 0;
    const rightTime = Date.parse(right.created_at || "") || 0;
    if (leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    return left.key.localeCompare(right.key);
  });
  const doctorCallStatusLabel =
    callUiState.message ||
    (currentCall?.status === "ringing" && currentCall?.initiated_by === "patient"
      ? `Incoming ${currentCall.call_type || "voice"} call from ${activeConsultation?.patient_name || "Patient"}`
      : currentCall?.status === "ringing" && currentCall?.initiated_by === "doctor"
        ? `${currentCall.call_type === "video" ? "Video" : "Voice"} call is ringing...`
        : doctorEffectiveActiveCall
          ? `${currentCall.call_type === "video" ? "Video" : "Voice"} call connected`
          : "");

  useEffect(() => {
    const connectedAt = getCallDurationAnchor(currentCall);
    if (currentCall?.status !== "active" || !connectedAt) {
      return undefined;
    }

    setCallTimerNow(Date.now());
    const timer = window.setInterval(() => {
      setCallTimerNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [currentCall?.status, currentCall?.connected_at, currentCall?.started_at]);

  useEffect(() => {
    const previousStatus = previousCallStatusRef.current;
    const nextStatus = currentCall?.status || null;
    const shouldHandleCallLog =
      currentCall?.started_at &&
      previousStatus &&
      ["ringing", "connecting", "active"].includes(previousStatus) &&
      ["ended", "rejected"].includes(nextStatus || "");

    if (shouldHandleCallLog) {
      const callTypeLabel = (currentCall.call_type || "voice").replace(/^./, (letter) => letter.toUpperCase());
      const endedAt = currentCall.updated_at || new Date().toISOString();
      const connectedAt = currentCall.connected_at || null;
      const duration = connectedAt ? formatCallDuration(connectedAt, endedAt) : "";
      const doctorStartedCall = currentCall.initiated_by === "doctor";
      const connectedBeforeClosing = previousStatus === "active" || Boolean(connectedAt);
      let title = (connectedBeforeClosing ? "\u260E " : callTypeLabel === "Video" ? "\uD83C\uDFA5 " : "\uD83D\uDCF5 ") + callTypeLabel + " call";
      let body = connectedBeforeClosing ? duration : "";
      let tone = connectedBeforeClosing ? "success" : "danger";

      if (!connectedBeforeClosing && nextStatus === "ended") {
        title = doctorStartedCall
          ? (callTypeLabel === "Video" ? "\uD83C\uDFA5" : "\uD83D\uDCF4") + " " + callTypeLabel + " call not answered"
          : (callTypeLabel === "Video" ? "\uD83C\uDFA5" : "\uD83D\uDCF5") + " Missed " + callTypeLabel.toLowerCase() + " call";
      } else if (!connectedBeforeClosing && nextStatus === "rejected") {
        title = doctorStartedCall ? "\uD83D\uDEAB " + callTypeLabel + " call rejected" : "\uD83D\uDEAB " + callTypeLabel + " call declined";
      }
      appendActivityEvent({
        kind: "call",
        align: doctorStartedCall ? "doctor" : "patient",
        title,
        body,
        tone,
        created_at: endedAt,
      });
    }

    previousCallStatusRef.current = nextStatus;
  }, [currentCall, activeConsultation?.patient_name]);

  useEffect(() => {
    if (localVideoRef.current && localStreamRef.current) {
      localVideoRef.current.srcObject = localStreamRef.current;
    }
    if (remoteVideoRef.current && remoteStreamRef.current) {
      remoteVideoRef.current.srcObject = remoteStreamRef.current;
    }
    if (remoteAudioRef.current && remoteStreamRef.current) {
      remoteAudioRef.current.srcObject = remoteStreamRef.current;
    }
  }, [callUiState.localMediaReady, currentCall?.status, currentCall?.call_type, callWindowMinimized]);

  useEffect(() => {
    if (doctorEffectiveActiveCall || callUiState.status === "connecting") {
      stopRingtone();
      return;
    }

    if (currentCall?.status === "ringing" && currentCall?.initiated_by === "patient") {
      startRingtone("incoming");
      return;
    }

    if ((currentCall?.status === "ringing" && currentCall?.initiated_by === "doctor") || callUiState.status === "starting") {
      startRingtone("outgoing");
      return;
    }

    stopRingtone();
  }, [currentCall?.status, currentCall?.initiated_by, callUiState.status]);

  const doctorCallOverlay =
    currentCall?.status === "active" || currentCall?.status === "ringing" || callUiState.localMediaReady
      ? createPortal(
          <div
            ref={callOverlayRef}
            className={
              callWindowMinimized
                ? "doctor-call-overlay doctor-call-overlay--minimized"
                : "doctor-call-overlay doctor-call-overlay--centered"
            }
            style={
              callWindowMinimized && callWindowPosition.x !== null && callWindowPosition.y !== null
                ? {
                    left: `${callWindowPosition.x}px`,
                    top: `${callWindowPosition.y}px`,
                  }
                : undefined
            }
            onPointerDown={beginCallWindowDrag}
          >
            <div
              className={
                callWindowMinimized
                  ? "doctor-call-stage doctor-call-stage--overlay doctor-call-stage--minimized"
                  : `doctor-call-stage doctor-call-stage--overlay${
                      doctorShowVideoCallLayout ? " doctor-call-stage--video" : " doctor-call-stage--voice"
                    }${doctorActiveVideoControlsOnly ? " doctor-call-stage--controls-only" : ""}`
              }
            >
              <audio ref={remoteAudioRef} autoPlay playsInline className="doctor-call-stage__audio" />
              {!doctorShowVideoCallLayout ? (
                <div className="doctor-call-stage__voice-avatar">
                  {getDisplayInitials(activeConsultation?.patient_name)}
                </div>
              ) : null}
              {doctorShowVideoCallLayout ? (
                <>
                  {doctorShowSelfPreviewAsMain ? (
                    <video
                      ref={localVideoRef}
                      className="doctor-call-stage__remote doctor-call-stage__remote--self"
                      autoPlay
                      muted
                      playsInline
                    />
                  ) : (
                    <video ref={remoteVideoRef} className="doctor-call-stage__remote" autoPlay playsInline />
                  )}
                  {doctorEffectiveActiveCall ? (
                    <video ref={localVideoRef} className="doctor-call-stage__local" autoPlay muted playsInline />
                  ) : null}
                </>
              ) : null}
              <div
                className={
                  callWindowMinimized
                    ? "doctor-call-stage__sheet doctor-call-stage__sheet--minimized"
                    : "doctor-call-stage__sheet"
                }
              >
                {!doctorActiveVideoControlsOnly ? <div className="doctor-call-stage__topline">
                  <span className="doctor-call-stage__mode">
                    {currentCall?.call_type === "video" ? "Video Call" : "Voice Call"}
                  </span>
                  <button className="doctor-call-overlay__toggle" type="button" onClick={handleCallWindowToggle}>
                    {callWindowMinimized ? "Expand" : "Minimize"}
                  </button>
                </div> : null}
                {!doctorActiveVideoControlsOnly ? <div className="doctor-call-stage__identity">
                  <div className="doctor-call-stage__avatar">
                    {getDisplayInitials(activeConsultation?.patient_name)}
                  </div>
                  <div className="doctor-call-stage__copy">
                    <strong>{activeConsultation?.patient_name}</strong>
                    <span>{doctorCallStatusLabel || "Preparing call..."}</span>
                    {doctorCallTimerLabel ? <span className="doctor-call-stage__timer">{doctorCallTimerLabel}</span> : null}
                  </div>
                </div> : null}
                <div className="doctor-call-stage__controls">
                  {currentCall?.status === "ringing" && currentCall?.initiated_by === "patient" && !doctorAcceptingIncomingCall ? (
                    <>
                      <button
                        className="button button--primary"
                        type="button"
                        onClick={() => handleAcceptDoctorIncomingCall(currentCall)}
                      >
                        Accept
                      </button>
                      <button className="button button--secondary" type="button" onClick={handleRejectDoctorIncomingCall}>
                        Decline
                      </button>
                    </>
                  ) : null}
                  {(doctorEffectiveActiveCall || currentCall?.status === "ringing" || callUiState.localMediaReady) &&
                  !(currentCall?.status === "ringing" && currentCall?.initiated_by === "patient" && !doctorAcceptingIncomingCall) ? (
                    <>
                      {callUiState.localMediaReady ? (
                        <button className="button button--secondary" type="button" onClick={toggleDoctorAudio}>
                          {callUiState.audioMuted ? "Unmute" : "Mute"}
                        </button>
                      ) : null}
                      {callUiState.localMediaReady && doctorHasLocalVideoTrack ? (
                        <button className="button button--secondary" type="button" onClick={toggleDoctorVideo}>
                          {callUiState.videoDisabled ? "Camera On" : "Camera Off"}
                        </button>
                      ) : null}
                      <button className="button button--secondary" type="button" onClick={handleEndDoctorCurrentCall}>
                        {doctorEffectiveActiveCall ? "End Call" : "Cancel"}
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )
      : null;

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      setShowConsultationView(false);
    }
  }, [activeConsultation?.consultation_id]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id && activeTool) {
      setActiveTool(null);
    }
  }, [activeConsultation?.consultation_id, activeTool]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      setConsultationDiagnosis("");
      setDiagnosisPanelOpen(false);
      return;
    }

    const nextDiagnosis =
      prescriptionForm.diagnosis || investigationForm.diagnosis || consultationDiagnosis || "";
    setConsultationDiagnosis(nextDiagnosis);
  }, [activeConsultation?.consultation_id]);

  useEffect(() => {
    if (!diagnosisPanelOpen) {
      return undefined;
    }

    function handleOutsidePointer(event) {
      if (!diagnosisPanelRef.current?.contains(event.target)) {
        setDiagnosisPanelOpen(false);
      }
    }

    document.addEventListener("mousedown", handleOutsidePointer);
    return () => document.removeEventListener("mousedown", handleOutsidePointer);
  }, [diagnosisPanelOpen]);

  useEffect(() => {
    async function syncDoctorCallState() {
      if (!currentCall) {
        return;
      }

      if (currentCall.status === "ended" || currentCall.status === "rejected") {
        closeCallMedia();
        return;
      }

      const peer = peerConnectionRef.current;
      if (!peer) {
        return;
      }

      if (currentCall.answer_sdp && peer.localDescription?.type === "offer" && !peer.currentRemoteDescription) {
        try {
          await peer.setRemoteDescription(new RTCSessionDescription(currentCall.answer_sdp));
          setCallUiState((current) => ({
            ...current,
            status: "active",
            message: "Call connected.",
          }));
        } catch {}
      }

      if (!peer.remoteDescription) {
        return;
      }

      for (const candidate of currentCall.patient_candidates || []) {
        const key = JSON.stringify(candidate);
        if (seenCandidateKeysRef.current.has(key)) {
          continue;
        }
        try {
          await peer.addIceCandidate(new RTCIceCandidate(candidate));
          seenCandidateKeysRef.current.add(key);
        } catch {}
      }
    }

    syncDoctorCallState();
  }, [currentCall]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      setActivityEvents([]);
      previousCallStatusRef.current = null;
      setPrescriptionForm({
        diagnosis: "",
        medications_text: "",
        notes: "",
      });
      setInvestigationForm({
        diagnosis: "",
        tests_text: "",
        notes: "",
      });
      setHistoryForm("");
      setPrescriptionDraftState({
        status: "idle",
        message: "Prescription draft will autosave while you type.",
        savedAt: "",
      });
      setInvestigationDraftState({
        status: "idle",
        message: "Investigation draft will autosave while you type.",
        savedAt: "",
      });
      setHistorySaveState({
        status: "idle",
        message: "History notes will autosave while you type.",
        savedAt: "",
      });
      return;
    }

    const draftKey = historyDraftKey(activeConsultation.consultation_id);
    const localDraft = window.localStorage.getItem(draftKey);
    const nextValue =
      typeof localDraft === "string" && localDraft.length
        ? localDraft
        : activeConsultation.saved_history || activeConsultation.summary || "";
    setHistoryForm(nextValue);
    setHistorySaveState({
      status: localDraft ? "saved" : "idle",
      message: localDraft
        ? "Recovered your saved draft for this consultation."
        : "History notes will autosave while you type.",
      savedAt: localDraft ? new Date().toISOString() : "",
    });

    const savedPrescriptionDraft = window.localStorage.getItem(
      prescriptionDraftKey(activeConsultation.consultation_id),
    );
    if (savedPrescriptionDraft) {
      try {
        const parsed = JSON.parse(savedPrescriptionDraft);
        setPrescriptionForm({
          diagnosis: parsed?.diagnosis || "",
          medications_text: parsed?.medications_text || "",
          notes: parsed?.notes || "",
        });
        setPrescriptionDraftState({
          status: "saved",
          message: "Recovered your saved prescription draft.",
          savedAt: new Date().toISOString(),
        });
      } catch {
        setPrescriptionForm({
          diagnosis: "",
          medications_text: "",
          notes: "",
        });
        setPrescriptionDraftState({
          status: "idle",
          message: "Prescription draft will autosave while you type.",
          savedAt: "",
        });
      }
    } else {
      setPrescriptionForm({
        diagnosis: "",
        medications_text: "",
        notes: "",
      });
      setPrescriptionDraftState({
        status: "idle",
        message: "Prescription draft will autosave while you type.",
        savedAt: "",
      });
    }

    const savedInvestigationDraft = window.localStorage.getItem(
      investigationDraftKey(activeConsultation.consultation_id),
    );
    if (savedInvestigationDraft) {
      try {
        const parsed = JSON.parse(savedInvestigationDraft);
        setInvestigationForm({
          diagnosis: parsed?.diagnosis || "",
          tests_text: parsed?.tests_text || "",
          notes: parsed?.notes || "",
        });
        setInvestigationDraftState({
          status: "saved",
          message: "Recovered your saved investigation draft.",
          savedAt: new Date().toISOString(),
        });
      } catch {
        setInvestigationForm({
          diagnosis: "",
          tests_text: "",
          notes: "",
        });
        setInvestigationDraftState({
          status: "idle",
          message: "Investigation draft will autosave while you type.",
          savedAt: "",
        });
      }
    } else {
      setInvestigationForm({
        diagnosis: "",
        tests_text: "",
        notes: "",
      });
      setInvestigationDraftState({
        status: "idle",
        message: "Investigation draft will autosave while you type.",
        savedAt: "",
      });
    }
  }, [activeConsultation?.consultation_id, activeConsultation?.saved_history, activeConsultation?.summary]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      if (autosaveTimeoutRef.current) {
        window.clearTimeout(autosaveTimeoutRef.current);
        autosaveTimeoutRef.current = null;
      }
      return undefined;
    }

    const draftKey = historyDraftKey(activeConsultation.consultation_id);
    window.localStorage.setItem(draftKey, historyForm);

    if (autosaveTimeoutRef.current) {
      window.clearTimeout(autosaveTimeoutRef.current);
    }

    setHistorySaveState((current) =>
      historyForm.trim()
        ? {
            ...current,
            status: current.status === "error" ? "error" : "typing",
            message:
              current.status === "error"
                ? current.message
                : "Draft saved on this device. Syncing automatically...",
            savedAt: current.status === "error" ? current.savedAt : current.savedAt,
          }
        : {
            ...current,
            status: "idle",
            message: "History notes will autosave while you type.",
            savedAt: "",
          },
    );

    if (!historyForm.trim()) {
      return undefined;
    }

    autosaveTimeoutRef.current = window.setTimeout(() => {
      persistHistoryNote(historyForm, { silent: true });
    }, 1200);

    return () => {
      if (autosaveTimeoutRef.current) {
        window.clearTimeout(autosaveTimeoutRef.current);
        autosaveTimeoutRef.current = null;
      }
    };
  }, [historyForm, activeConsultation?.consultation_id]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      return;
    }

    const hasPrescriptionDraft = Boolean(
      prescriptionForm.diagnosis.trim() ||
        prescriptionForm.medications_text.trim() ||
        prescriptionForm.notes.trim(),
    );

    if (!hasPrescriptionDraft) {
      window.localStorage.removeItem(prescriptionDraftKey(activeConsultation.consultation_id));
      setPrescriptionDraftState({
        status: "idle",
        message: "Prescription draft will autosave while you type.",
        savedAt: "",
      });
      return;
    }

    window.localStorage.setItem(
      prescriptionDraftKey(activeConsultation.consultation_id),
      JSON.stringify(prescriptionForm),
    );
    setPrescriptionDraftState({
      status: "saved",
      message: "Prescription draft saved on this device.",
      savedAt: new Date().toISOString(),
    });
  }, [prescriptionForm, activeConsultation?.consultation_id]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      return;
    }

    const hasInvestigationDraft = Boolean(
      investigationForm.diagnosis.trim() ||
        investigationForm.tests_text.trim() ||
        investigationForm.notes.trim(),
    );

    if (!hasInvestigationDraft) {
      window.localStorage.removeItem(investigationDraftKey(activeConsultation.consultation_id));
      setInvestigationDraftState({
        status: "idle",
        message: "Investigation draft will autosave while you type.",
        savedAt: "",
      });
      return;
    }

    window.localStorage.setItem(
      investigationDraftKey(activeConsultation.consultation_id),
      JSON.stringify(investigationForm),
    );
    setInvestigationDraftState({
      status: "saved",
      message: "Investigation draft saved on this device.",
      savedAt: new Date().toISOString(),
    });
  }, [investigationForm, activeConsultation?.consultation_id]);

  useEffect(() => {
    if (!activeConsultation?.consultation_id) {
      return undefined;
    }

    return () => {
      if (autosaveTimeoutRef.current) {
        window.clearTimeout(autosaveTimeoutRef.current);
        autosaveTimeoutRef.current = null;
      }
    };
  }, [activeConsultation?.consultation_id]);

  useLayoutEffect(() => {
    if (!doctorInSession || !transcriptState.transcript.length || !transcriptWindowRef.current) {
      return;
    }

    transcriptWindowRef.current.scrollTop = transcriptWindowRef.current.scrollHeight;
  }, [
    doctorInSession,
    transcriptState.transcript.length,
    transcriptState.transcript[transcriptState.transcript.length - 1]?.created_at,
  ]);

  async function handleSaveDiagnosis() {
    await persistHistoryNote(historyForm);
    setDiagnosisPanelOpen(false);
  }

  useEffect(
    () => () => {
      stopCallWindowDrag();
      stopRingtone();
      closeCallMedia();
    },
    [],
  );

  async function ensureLocalMedia(callType) {
    if (localStreamRef.current) {
      return localStreamRef.current;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: callType === "video",
    });
    localStreamRef.current = stream;
    setCallUiState((current) => ({
      ...current,
      localMediaReady: true,
    }));
    return stream;
  }

  function stopRingtone() {
    if (ringtoneIntervalRef.current) {
      window.clearInterval(ringtoneIntervalRef.current);
      ringtoneIntervalRef.current = null;
    }

    if (ringtoneAudioContextRef.current) {
      ringtoneAudioContextRef.current.close().catch(() => {});
      ringtoneAudioContextRef.current = null;
    }
  }

  function playRingtonePulse(audioContext, tones = [0, 180]) {
    tones.forEach((offset) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = "sine";
      oscillator.frequency.value = 820;
      gain.gain.setValueAtTime(0.0001, audioContext.currentTime + offset / 1000);
      gain.gain.exponentialRampToValueAtTime(0.04, audioContext.currentTime + offset / 1000 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioContext.currentTime + offset / 1000 + 0.18);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(audioContext.currentTime + offset / 1000);
      oscillator.stop(audioContext.currentTime + offset / 1000 + 0.22);
    });
  }

  function startRingtone(kind = "outgoing") {
    if (ringtoneIntervalRef.current) {
      return;
    }

    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      return;
    }

    try {
      const audioContext = new AudioContextCtor();
      ringtoneAudioContextRef.current = audioContext;
      const tones = kind === "incoming" ? [0, 220, 520] : [0, 200];
      playRingtonePulse(audioContext, tones);
      ringtoneIntervalRef.current = window.setInterval(() => {
        if (audioContext.state === "suspended") {
          audioContext.resume().catch(() => {});
        }
        playRingtonePulse(audioContext, tones);
      }, kind === "incoming" ? 1800 : 1500);
    } catch {}
  }

  function closeCallMedia() {
    if (peerConnectionRef.current) {
      peerConnectionRef.current.onicecandidate = null;
      peerConnectionRef.current.ontrack = null;
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }
    if (localStreamRef.current) {
      localStreamRef.current.getTracks().forEach((track) => track.stop());
      localStreamRef.current = null;
    }
    remoteStreamRef.current = null;
    seenCandidateKeysRef.current = new Set();
    if (localVideoRef.current) {
      localVideoRef.current.srcObject = null;
    }
    if (remoteVideoRef.current) {
      remoteVideoRef.current.srcObject = null;
    }
    if (remoteAudioRef.current) {
      remoteAudioRef.current.srcObject = null;
    }
    stopRingtone();
    setCallUiState({
      status: "idle",
      message: "",
      localMediaReady: false,
      audioMuted: false,
      videoDisabled: false,
    });
    setCallWindowMinimized(false);
    setCallWindowPosition({ x: null, y: null });
  }

  function ensureMinimizedWindowPosition() {
    setCallWindowPosition((current) => {
      if (current.x !== null && current.y !== null) {
        return current;
      }
      return getDefaultCallWindowPosition();
    });
  }

  function handleCallWindowToggle() {
    setCallWindowMinimized((current) => {
      const next = !current;
      if (next) {
        ensureMinimizedWindowPosition();
      }
      return next;
    });
  }

  function stopCallWindowDrag() {
    callDragStateRef.current = null;
    window.removeEventListener("pointermove", handleCallWindowDrag);
    window.removeEventListener("pointerup", stopCallWindowDrag);
  }

  function handleCallWindowDrag(event) {
    const dragState = callDragStateRef.current;
    const overlay = callOverlayRef.current;
    if (!dragState || !overlay) {
      return;
    }

    const width = overlay.offsetWidth || 180;
    const height = overlay.offsetHeight || 180;
    const maxX = Math.max(12, window.innerWidth - width - 12);
    const maxY = Math.max(72, window.innerHeight - height - 12);
    setCallWindowPosition({
      x: Math.min(Math.max(12, event.clientX - dragState.offsetX), maxX),
      y: Math.min(Math.max(72, event.clientY - dragState.offsetY), maxY),
    });
  }

  function beginCallWindowDrag(event) {
    if (!callWindowMinimized || !callOverlayRef.current || event.target.closest("button")) {
      return;
    }
    const rect = callOverlayRef.current.getBoundingClientRect();
    callDragStateRef.current = {
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    window.addEventListener("pointermove", handleCallWindowDrag);
    window.addEventListener("pointerup", stopCallWindowDrag);
  }

  function toggleDoctorAudio() {
    if (!localStreamRef.current) {
      return;
    }

    const nextMuted = !callUiState.audioMuted;
    localStreamRef.current.getAudioTracks().forEach((track) => {
      track.enabled = !nextMuted;
    });
    setCallUiState((current) => ({
      ...current,
      audioMuted: nextMuted,
    }));
  }

  function toggleDoctorVideo() {
    if (!localStreamRef.current) {
      return;
    }

    const videoTracks = localStreamRef.current.getVideoTracks();
    if (!videoTracks.length) {
      return;
    }

    const nextDisabled = !callUiState.videoDisabled;
    videoTracks.forEach((track) => {
      track.enabled = !nextDisabled;
    });
    setCallUiState((current) => ({
      ...current,
      videoDisabled: nextDisabled,
    }));
  }

  async function preparePeerConnection(callType) {
    const stream = await ensureLocalMedia(callType);
    if (peerConnectionRef.current) {
      return peerConnectionRef.current;
    }

    const peer = createPeerConnection();
    stream.getTracks().forEach((track) => peer.addTrack(track, stream));
    peer.ontrack = (event) => {
      const [remoteStream] = event.streams;
      remoteStreamRef.current = remoteStream;
      if (remoteVideoRef.current) {
        remoteVideoRef.current.srcObject = remoteStream;
      }
      if (remoteAudioRef.current) {
        remoteAudioRef.current.srcObject = remoteStream;
      }
    };
    peer.onicecandidate = async (event) => {
      if (!event.candidate) {
        return;
      }
      try {
        await sendDoctorCallCandidate({
          candidate: {
            candidate: event.candidate.candidate,
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex,
            usernameFragment: event.candidate.usernameFragment,
          },
        });
      } catch {}
    };
    peerConnectionRef.current = peer;
    return peer;
  }

  async function handleStartDoctorCall(callType) {
    try {
      setCallUiState({
        status: "starting",
        message: `Starting ${callType} call...`,
        localMediaReady: false,
        audioMuted: false,
        videoDisabled: false,
      });
      const peer = await preparePeerConnection(callType);
      const offer = await peer.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: callType === "video",
      });
      await peer.setLocalDescription(offer);
      const result = await startDoctorCall({
        call_type: callType,
        offer_sdp: {
          type: offer.type,
          sdp: offer.sdp,
        },
      });
      if (!result.ok) {
        throw new Error(result.message || "Unable to start the call right now.");
      }
      setWorkspaceState((current) =>
        current.result
          ? {
              ...current,
              result: {
                ...current.result,
                call: result.call || null,
              },
            }
          : current,
      );
      setCallUiState((current) => ({
        ...current,
        status: "ringing",
        message: `${callType === "video" ? "Video" : "Voice"} call is ringing...`,
      }));
    } catch (error) {
      closeCallMedia();
      setCallUiState({
        status: "error",
        message: error.message || "Unable to start the call right now.",
        localMediaReady: false,
      });
    }
  }

  async function handleAcceptDoctorIncomingCall(callState) {
    if (!callState?.offer_sdp) {
      return;
    }

    try {
      setCallUiState({
        status: "connecting",
        message: "Connecting call...",
        localMediaReady: false,
        audioMuted: false,
        videoDisabled: false,
      });
      const peer = await preparePeerConnection(callState.call_type || "voice");
      await peer.setRemoteDescription(new RTCSessionDescription(callState.offer_sdp));
      const answer = await peer.createAnswer();
      await peer.setLocalDescription(answer);
      const result = await acceptDoctorCall({
        answer_sdp: {
          type: answer.type,
          sdp: answer.sdp,
        },
      });
      if (!result.ok) {
        throw new Error(result.message || "Unable to accept the call right now.");
      }
      setWorkspaceState((current) =>
        current.result
          ? {
              ...current,
              result: {
                ...current.result,
                call: result.call || null,
              },
            }
          : current,
      );
      setCallUiState((current) => ({
        ...current,
        status: "active",
        message: "Call connected.",
      }));
    } catch (error) {
      closeCallMedia();
      setCallUiState({
        status: "error",
        message: error.message || "Unable to accept the call right now.",
        localMediaReady: false,
      });
    }
  }

  async function handleRejectDoctorIncomingCall() {
    try {
      const result = await rejectDoctorCall();
      if (!result.ok) {
        throw new Error(result.message || "Unable to reject the call right now.");
      }
      setWorkspaceState((current) =>
        current.result
          ? {
              ...current,
              result: {
                ...current.result,
                call: result.call || null,
              },
            }
          : current,
      );
      closeCallMedia();
    } catch (error) {
      setCallUiState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to reject the call right now.",
      }));
    }
  }

  async function handleEndDoctorCurrentCall() {
    try {
      const endingCall = currentCall;
      const result = await endDoctorCall();
      if (!result.ok) {
        throw new Error(result.message || "Unable to end the call right now.");
      }
      appendActivityEvent({
        kind: "call",
        align: (endingCall?.initiated_by || result.call?.initiated_by) === "doctor" ? "doctor" : "patient",
        title: ((endingCall?.call_type || "voice") === "video" ? "\uD83C\uDFA5" : "\uD83D\uDCDE") + " " + ((endingCall?.call_type || "voice").replace(/^./, (letter) => letter.toUpperCase())) + " call",
        body:
          endingCall?.connected_at || result.call?.connected_at
            ? formatCallDuration(
                endingCall?.connected_at || result.call?.connected_at,
                result.call?.updated_at || new Date().toISOString(),
              )
            : "",
        created_at: result.call?.updated_at || new Date().toISOString(),
      });
      previousCallStatusRef.current = result.call?.status || "ended";
      setWorkspaceState((current) =>
        current.result
          ? {
              ...current,
              result: {
                ...current.result,
                call: result.call || null,
              },
            }
          : current,
      );
    } catch (error) {
      setCallUiState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to end the call right now.",
      }));
      closeCallMedia();
    }
  }

  if (authState.status === "loading") {
    return (
      <div className="doctor-dashboard">
        <section className="doctor-dashboard__hero">
          <div className="doctor-dashboard__intro">
            <span className="workspace-pill">Doctor Workspace</span>
            <h1>Preparing doctor workspace...</h1>
            <BrandedLoader label={authState.message} />
          </div>
        </section>
      </div>
    );
  }

  if (authState.status === "unauthenticated") {
    return <Navigate to="/signin" replace />;
  }

  if (doctorInSession && showConsultationView) {
    return (
      <div className="doctor-dashboard doctor-dashboard--session">
        <div className="doctor-dashboard__session-main">
          <SectionCard
            title="Live Consultation"
          >
            <div className="doctor-workspace-card">
              <aside className="doctor-workspace__sidebar">
                <div className="doctor-active-card">
                  <button
                    aria-expanded={patientSummaryOpen}
                    className="doctor-active-card__toggle"
                    type="button"
                    onClick={() => setPatientSummaryOpen((current) => !current)}
                  >
                    <span>Current Patient</span>
                    <span aria-hidden="true">{patientSummaryOpen ? "\u2212" : "+"}</span>
                  </button>
                  <div
                    className={
                      patientSummaryOpen
                        ? "doctor-active-card__content doctor-active-card__content--open"
                        : "doctor-active-card__content"
                    }
                  >
                    <div className="doctor-active-card__copy">
                      <span className="consultation-room__eyebrow">Current Patient</span>
                      <h3>
                        {activeConsultation.hospital_number} | {activeConsultation.patient_name}
                      </h3>
                      <p>{activeConsultation.summary}</p>
                      <div className="doctor-active-card__facts">
                        <span>Age: {activeConsultation.age || "N/A"}</span>
                        <span>Gender: {activeConsultation.gender || "N/A"}</span>
                        <span>Allergies: {activeConsultation.allergy || "None recorded"}</span>
                        <span>Conditions: {activeConsultation.medical_conditions || "None recorded"}</span>
                      </div>
                    </div>
                    <div className="doctor-active-card__meta">
                      <StatusPill
                        label={activeConsultation.source}
                        tone={activeConsultation.source === "web" ? "success" : "neutral"}
                      />
                      {activeConsultation.emergency ? <StatusPill label="Emergency" tone="danger" /> : null}
                    </div>
                  </div>
                </div>

                <div className="doctor-chat-actions doctor-chat-actions--sticky">
                  <button
                    className="consultation-toolbar__back consultation-toolbar__back--inline"
                    type="button"
                    onClick={() => {
                      if (activeTool) {
                        setActiveTool(null);
                        return;
                      }
                      setShowConsultationView(false);
                    }}
                  >
                    {activeTool ? "\u2190 Back to consultation" : "\u2190 Back to dashboard"}
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={doctorHasCallInProgress}
                    onClick={() => handleStartDoctorCall("voice")}
                  >
                    {"\u260E"} Voice Call
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    disabled={doctorHasCallInProgress}
                    onClick={() => handleStartDoctorCall("video")}
                  >
                    {"\u25B6"} Video Call
                  </button>
                  <button
                    aria-expanded={clinicalToolsOpen}
                    className="doctor-clinical-tools-toggle"
                    type="button"
                    onClick={() => setClinicalToolsOpen((current) => !current)}
                  >
                    <span>Clinical tools</span>
                    <span aria-hidden="true">{clinicalToolsOpen ? "\u2212" : "+"}</span>
                  </button>
                  <div
                    className={
                      clinicalToolsOpen
                        ? "doctor-clinical-tools doctor-clinical-tools--open"
                        : "doctor-clinical-tools"
                    }
                  >
                    {quickTools.map((tool) => (
                    <button
                      key={tool.key}
                      className={activeTool === tool.key ? "button button--primary" : "button button--secondary"}
                      type="button"
                      onClick={() => {
                        setActiveTool(tool.key);
                        setClinicalToolsOpen(false);
                      }}
                    >
                      {tool.label}
                    </button>
                    ))}
                  </div>
                </div>
              </aside>

              <section className={activeTool ? "doctor-workspace__main doctor-workspace__main--tool" : "doctor-workspace__main"}>
              {activeTool ? (
                <div className="doctor-tools doctor-tools--session">
                  <div className={`doctor-workspace-state doctor-workspace-state--${documentState.status}`}>
                    <p className="doctor-state__message">{documentState.message}</p>
                    {documentState.result?.filename ? (
                      <p className="doctor-state__message">Latest document: {documentState.result.filename}</p>
                    ) : null}
                  </div>

                  <div className="doctor-tool-panel">
                    {activeTool === "prescription" ? (
                      <form className="form-panel doctor-doc-form" onSubmit={handleCreatePrescription}>
                        <h3>Create Prescription</h3>
                        <label className="form-field">
                          <span className="form-field__label">Diagnosis</span>
                          <input
                            className="form-field__input"
                            type="text"
                            value={prescriptionForm.diagnosis}
                            onChange={(event) => handleDiagnosisChange(event.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          <span className="form-field__label">Medications</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="5"
                            placeholder="1. Tablet Paracetamol 500mg twice daily for 5 days"
                            value={prescriptionForm.medications_text}
                            onFocus={() =>
                              handleNumberedListFocus(
                                prescriptionForm.medications_text,
                                setPrescriptionForm,
                                "medications_text",
                              )
                            }
                            onKeyDown={(event) =>
                              handleNumberedListKeyDown(
                                event,
                                prescriptionForm.medications_text,
                                setPrescriptionForm,
                                "medications_text",
                              )
                            }
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
                            onChange={(event) => handleDiagnosisChange(event.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          <span className="form-field__label">Investigations</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="5"
                            placeholder={"Full blood count\nUrinalysis\nMalaria parasite test"}
                            value={investigationForm.tests_text}
                            onFocus={() =>
                              handleNumberedListFocus(
                                investigationForm.tests_text,
                                setInvestigationForm,
                                "tests_text",
                              )
                            }
                            onKeyDown={(event) =>
                              handleNumberedListKeyDown(
                                event,
                                investigationForm.tests_text,
                                setInvestigationForm,
                                "tests_text",
                              )
                            }
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

                    {activeTool === "medicalReport" ? (
                      <form className="form-panel doctor-doc-form" onSubmit={handleCreateMedicalReport}>
                        <h3>Create Medical Report</h3>
                        <label className="form-field">
                          <span className="form-field__label">Diagnosis</span>
                          <input
                            className="form-field__input"
                            type="text"
                            value={medicalReportForm.diagnosis}
                            onChange={(event) => handleDiagnosisChange(event.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          <span className="form-field__label">Medical Report</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="7"
                            placeholder="Write the medical report summary, relevant findings, and recommendations..."
                            value={medicalReportForm.report_note}
                            onChange={(event) =>
                              setMedicalReportForm((current) => ({ ...current, report_note: event.target.value }))
                            }
                          />
                        </label>
                        <button className="button button--primary" type="submit">
                          Create Medical Report
                        </button>
                      </form>
                    ) : null}

                    {activeTool === "history" ? (
                      <form className="form-panel doctor-doc-form" onSubmit={handleSaveHistory}>
                        <h3>Patient History</h3>
                        <p>
                          View the current patient history and update it when needed. This saves into the active
                          consultation and remains available while you continue care.
                        </p>
                        <label className="form-field">
                          <span className="form-field__label">Consultation History Note</span>
                          <textarea
                            className="form-field__input form-field__input--textarea"
                            rows="8"
                            placeholder="Type the patient history, examination notes, and clinical summary here..."
                            value={historyForm}
                            onChange={(event) => setHistoryForm(event.target.value)}
                          />
                        </label>
                        <div className={`doctor-workspace-state doctor-workspace-state--${historySaveState.status}`}>
                          <p className="doctor-state__message">{historySaveState.message}</p>
                          {historySaveState.savedAt ? (
                            <p className="doctor-state__message">
                              Last saved at {formatSavedTime(historySaveState.savedAt)}
                            </p>
                          ) : null}
                        </div>
                        <button className="button button--primary" type="submit">
                          Save History
                        </button>
                      </form>
                    ) : null}

                    {activeTool === "followup" ? (
                      <div className="doctor-doc-form">
                        <h3>Book Appointment / Follow-Up</h3>
                        <p>Appointment and follow-up actions are separated here instead of mixing with document writing.</p>
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div
                  className={`doctor-workspace-state doctor-workspace-state--chat doctor-workspace-state--${transcriptState.status}`}
                  style={{ "--doctor-composer-height": `${composerDockHeight}px` }}
                >
                  <p className="doctor-state__message">{transcriptState.message}</p>
                  <div ref={transcriptWindowRef} className="doctor-transcript">
                    {doctorTimelineItems.length ? (
                      doctorTimelineItems.map((entry) =>
                        entry.type === "activity" ? (
                          <article
                            key={entry.key}
                            className={`doctor-bubble doctor-bubble--system doctor-bubble--system-${entry.payload.align || "center"} doctor-bubble--system-${entry.payload.tone || "neutral"}`}
                          >
                              <span className="doctor-bubble__role">{entry.payload.title}</span>
                              {entry.payload.body ? <p>{entry.payload.body}</p> : null}
                            <time className="doctor-bubble__time">{formatChatTimestamp(entry.payload.created_at)}</time>
                          </article>
                        ) : (
                          <article
                            key={entry.key}
                            className={
                              entry.payload.sender_role === "doctor" || entry.payload.sender_role === "doctor_web"
                                ? "doctor-bubble doctor-bubble--doctor"
                                : "doctor-bubble doctor-bubble--patient"
                            }
                          >
                            <span className="doctor-bubble__role">
                              {getDoctorTranscriptSenderLabel(
                                entry.payload.sender_role,
                                doctor?.name,
                                activeConsultation?.patient_name,
                              )}
                            </span>
                            {renderDoctorTranscriptAsset(entry.payload, previewedAssets, setPreviewedAssets)}
                            <p>{entry.payload.message_text}</p>
                            <time className="doctor-bubble__time">{formatChatTimestamp(entry.payload.created_at)}</time>
                          </article>
                        ),
                      )
                    ) : (
                      <p className="doctor-state__message">No transcript messages yet.</p>
                    )}
                  </div>

                  <div ref={composerDockRef} className="doctor-workspace__composer">
                    <div ref={diagnosisPanelRef} className="doctor-diagnosis-zone">
                      {diagnosisPanelOpen ? (
                        <div className="doctor-diagnosis-panel">
                          <label className="form-field">
                            <span className="form-field__label">Diagnosis</span>
                            <input
                              className="form-field__input"
                              type="text"
                              value={consultationDiagnosis}
                              placeholder="Type the working diagnosis..."
                              onChange={(event) => handleDiagnosisChange(event.target.value)}
                              autoFocus
                            />
                          </label>
                          <button className="button button--primary" type="button" onClick={handleSaveDiagnosis}>
                            Save
                          </button>
                        </div>
                      ) : (
                        <button
                          className={
                            consultationDiagnosis.trim()
                              ? "doctor-diagnosis-toggle"
                              : "doctor-diagnosis-toggle doctor-diagnosis-toggle--blinking"
                          }
                          type="button"
                          onClick={() => setDiagnosisPanelOpen(true)}
                        >
                          {consultationDiagnosis.trim() ? `Diagnosis: ${consultationDiagnosis}` : "Add diagnosis"}
                        </button>
                      )}
                    </div>

                    <div className="doctor-workspace__end">
                      <button className="button button--secondary" type="button" onClick={handleEndChat}>
                        End Chat
                      </button>
                    </div>

                    <div className="doctor-workspace__composer-sticky">
                      <form
                        className={
                          voiceRecording
                            ? "form-panel form-panel--inline doctor-compose doctor-compose--recording"
                            : "form-panel form-panel--inline doctor-compose"
                        }
                        onSubmit={handleDoctorSendMessage}
                      >
                        <input
                          ref={attachmentInputRef}
                          type="file"
                          accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.txt"
                          hidden
                          onChange={handleDoctorAttachmentChange}
                        />
                        {!voiceRecording ? (
                          <button
                            className="chat-tool-button"
                            type="button"
                            onClick={() => attachmentInputRef.current?.click()}
                            aria-label="Attach file"
                            title="Attach file"
                          >
                            {"\uD83D\uDCCE"}
                          </button>
                        ) : null}
                        {voiceRecording ? (
                          <div className="voice-recording-control" aria-live="polite">
                            <span className="voice-recording-control__pulse" />
                            <span className="voice-recording-control__timer">{formatRecordingDuration(voiceElapsedSeconds)}</span>
                            <button
                              className="voice-recording-control__pause"
                              type="button"
                              onClick={handleDoctorVoicePauseToggle}
                              aria-label={voicePaused ? "Resume voice recording" : "Pause voice recording"}
                              title={voicePaused ? "Resume voice recording" : "Pause voice recording"}
                            >
                              {voicePaused ? "\u25CF" : "\u23F8"}
                            </button>
                          </div>
                        ) : (
                          <label className="form-field form-field--grow">
                            <span className="form-field__label">Reply to Patient</span>
                            <textarea
                              className="form-field__input"
                              ref={messageInputRef}
                              rows="1"
                              placeholder="Type your response..."
                              value={draftMessage}
                              onChange={(event) => {
                                setDraftMessage(event.target.value);
                                event.target.style.height = "auto";
                                event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
                                event.target.style.overflowY = event.target.scrollHeight > 120 ? "auto" : "hidden";
                              }}
                              onKeyDown={handleChatComposerKeyDown}
                            />
                          </label>
                        )}
                        {draftMessage.trim() ? (
                          <button
                            className="chat-tool-button chat-tool-button--send"
                            type="submit"
                            aria-label="Send message"
                            title="Send message"
                          >
                            <SendMessageIcon />
                          </button>
                        ) : (
                          <button
                            className={voiceRecording ? "chat-tool-button chat-tool-button--recording" : "chat-tool-button"}
                            type="button"
                            onClick={handleDoctorVoiceMessage}
                            aria-label={voiceRecording ? "Send voice message" : "Record voice message"}
                            title={voiceRecording ? "Send voice message" : "Record voice message"}
                          >
                            {voiceRecording ? "Send" : <VoiceNoteIcon />}
                          </button>
                        )}
                      </form>
                      {attachmentState.message ? (
                        <p className={`chat-composer-status chat-composer-status--${attachmentState.status}`}>
                          {attachmentState.message}
                        </p>
                      ) : null}
                    </div>
                  </div>
                </div>
              )}
              </section>
            </div>
          </SectionCard>
          {doctorCallOverlay}
        </div>
      </div>
    );
  }

  return (
    <div className="doctor-dashboard doctor-dashboard--portal">
      <section className="doctor-dashboard__hero">
        <div className="doctor-dashboard__intro">
          <span className="workspace-pill">Doctor Workspace</span>
          <h1>
            Welcome back
            {doctor?.name ? (
              <span className="doctor-dashboard__intro-name">{formatDoctorDisplayName(doctor.name)}.</span>
            ) : null}
          </h1>
        </div>

        <aside className="doctor-dashboard__identity-card">
          <div>
            <h2>{authState.session?.user?.display_name || "Doctor session"}</h2>
            <p>{authState.message}</p>
          </div>
          <div className="doctor-dashboard__identity-actions">
            <StatusPill label="Authenticated" tone="success" />
            <Link className="button button--secondary" to="/doctor/account">
              Open Account
            </Link>
            <button className="button button--secondary" type="button" onClick={handleSignOut}>
              Log Out
            </button>
          </div>
        </aside>
      </section>

      {activeConsultation ? (
        <SectionCard
          title="Active Consultation"
        >
          <div className="queue-item">
            <div className="queue-item__copy">
              <h3>
                {activeConsultation.hospital_number} | {activeConsultation.patient_name}
              </h3>
              <p>{activeConsultation.summary}</p>
            </div>
            <div className="queue-item__meta">
              <StatusPill
                label={activeConsultation.source}
                tone={activeConsultation.source === "web" ? "success" : "neutral"}
              />
              <button
                className="button button--primary"
                type="button"
                onClick={() => setShowConsultationView(true)}
              >
                Return to chat
              </button>
            </div>
          </div>
        </SectionCard>
      ) : null}

      <div className="doctor-dashboard__layout">
        <div className="doctor-dashboard__main">
          <SectionCard
            title="Waiting Patients"
          >
            <div className="queue-list">
              {queue.length ? (
                visibleQueue.map((item) => (
                  <article key={`${item.runtime_patient_id}-${item.hospital_number}`} className="queue-item">
                    <div className="queue-item__copy">
                      <h3>
                        {item.hospital_number} | {item.name}
                      </h3>
                      <p>{item.summary}</p>
                    </div>
                    <div className="queue-item__meta">
                      <StatusPill label={item.source} tone={item.source === "web" ? "success" : "neutral"} />
                      <StatusPill label={item.emergency ? "Emergency" : "Queued"} tone={item.emergency ? "danger" : "neutral"} />
                      <button
                        className="button button--secondary"
                        type="button"
                        disabled={!doctorCanConnect || workspaceState.status === "loading"}
                        onClick={() => handleConnectPatient(item.runtime_patient_id)}
                      >
                        {doctorCanConnect ? "Connect" : "Go online first"}
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <p className="doctor-state__message">No waiting patients in queue right now.</p>
              )}
            </div>
            {queuePageCount > 1 ? (
              <div className="doctor-pager">
                <span>Page {safeQueuePage} of {queuePageCount}</span>
                <div>
                  <button
                    type="button"
                    disabled={safeQueuePage <= 1}
                    onClick={() => setQueuePage(safeQueuePage - 1)}
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={safeQueuePage >= queuePageCount}
                    onClick={() => setQueuePage(safeQueuePage + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : null}
          </SectionCard>
        </div>

        <aside className="doctor-dashboard__rail">
          <SectionCard
            title="Presence"
          >
            <div className={`doctor-workspace-state doctor-workspace-state--${workspaceState.status}`}>
              {workspaceState.status === "loading" ? (
                <BrandedLoader compact label={workspaceState.message} />
              ) : (
                <p className="doctor-state__message">{workspaceState.message}</p>
              )}
              {doctor && authState.session?.user ? (
                <div className="doctor-presence-card">
                  <div>
                    <h3>{doctor.name}</h3>
                    <p>{doctor.specialty}</p>
                  </div>
                  <StatusPill
                    label={doctorStatusLabel}
                    tone={
                      doctor.status === "busy"
                        ? "danger"
                        : doctor.status === "available"
                        ? "success"
                        : "warning"
                    }
                  />
                </div>
              ) : null}
            </div>
          </SectionCard>

        </aside>
      </div>
    </div>
  );
}
