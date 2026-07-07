import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useSearchParams } from "react-router-dom";
import BrandedLoader from "../components/BrandedLoader.jsx";
import {
  acceptConsultationCall,
  createConsultationEventSource,
  createConsultationWebSocket,
  endConsultationCall,
  endConsultation,
  fetchConsultationDocuments,
  fetchConsultationStatus,
  fetchConsultationTranscript,
  rejectConsultationCall,
  requestConsultation,
  sendConsultationAttachment,
  sendConsultationMessage,
  sendConsultationCallCandidate,
  startConsultationCall,
  submitConsultationFeedback,
} from "../api/consultations.js";
import SectionCard from "../components/SectionCard.jsx";
import "../styles/consultation.css";
import "../styles/forms.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const INITIAL_ROOM_MESSAGE = "Describe how you're feeling. You may begin typing below.";
const QUEUED_ROOM_MESSAGE = "Your consultation request is queued. We will open the conversation here once a doctor joins.";
const QUEUED_PROMPT_TITLE = "Consultation Request Submitted";
const QUEUED_PROMPT_MESSAGE =
  "Your symptoms have been received and your consultation is now in the queue. Please remain on this page; a SynMed doctor will join you shortly.";
const TRANSCRIPT_PENDING_MESSAGE = "Your conversation will appear here once the consultation becomes active.";
const SKIPPED_FEEDBACK_KEY = "synmed_skipped_feedback_consultations";
const BACKGROUND_THEME_KEY = "synmed-background-theme";
const BACKGROUND_OPTIONS = [
  { key: "dark", label: "Dark" },
  { key: "light", label: "Light" },
];

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
    return "D";
  }

  const parts = normalized.split(/\s+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function getCallStageInitials(name, fallback = "C") {
  const initials = getDisplayInitials(name);
  return initials || fallback;
}

function getConsultationDocumentTitle(kind) {
  if (kind === "prescription") return "Prescription";
  if (kind === "investigation") return "Investigation";
  if (kind === "medical_report") return "Medical Report";
  return "Clinical Document";
}

function getConsultationDocumentDownloadName(item) {
  const extension = item.asset_type === "application/pdf" ? "pdf" : "png";
  return `${item.kind}-${item.document_id}.${extension}`;
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

function getRoomMessage(statusResult, fallbackMessage = TRANSCRIPT_PENDING_MESSAGE) {
  const status = statusResult?.status || "not_started";
  const hasConsultation = Boolean(statusResult?.consultation_id);

  if (!hasConsultation && status === "queued") {
    return QUEUED_ROOM_MESSAGE;
  }

  if (!hasConsultation && ["not_started", "missing_payment", "payment_not_verified", "idle"].includes(status)) {
    return INITIAL_ROOM_MESSAGE;
  }

  return fallbackMessage;
}

function getConsultationSenderLabel(senderRole, statusResult) {
  if (senderRole === "patient" || senderRole === "patient_web") {
    return statusResult?.patient?.name || "Patient";
  }

  if (senderRole === "doctor" || senderRole === "doctor_web") {
    return formatDoctorDisplayName(statusResult?.doctor?.name);
  }

  return senderRole || "Participant";
}

function mergeTranscriptWithPending(serverTranscript = [], currentTranscript = []) {
  const pending = (currentTranscript || []).filter((item) => item.optimistic || item.realtime);
  if (!pending.length) {
    return serverTranscript || [];
  }

  const serverItems = serverTranscript || [];
  const unmatchedPending = pending.filter((pendingItem) => {
    const pendingTime = Date.parse(pendingItem.created_at || "") || Date.now();
    return !serverItems.some((serverItem) => {
      if (serverItem.sender_role !== pendingItem.sender_role) return false;
      if ((serverItem.message_text || "") !== (pendingItem.message_text || "")) return false;
      const serverTime = Date.parse(serverItem.created_at || "") || pendingTime;
      return Math.abs(serverTime - pendingTime) < 120000;
    });
  });

  return [...serverItems, ...unmatchedPending].sort((left, right) => {
    const leftTime = Date.parse(left.created_at || "") || 0;
    const rightTime = Date.parse(right.created_at || "") || 0;
    return leftTime - rightTime;
  });
}

function mergeRealtimeMessage(currentTranscript = [], message) {
  const messageTime = Date.parse(message.created_at || "") || Date.now();
  let replacedPending = false;
  const nextTranscript = (currentTranscript || []).map((item) => {
    const itemTime = Date.parse(item.created_at || "") || messageTime;
    const isMatchingPending =
      item.optimistic &&
      item.sender_role === message.sender_role &&
      (item.message_text || "") === (message.message_text || "") &&
      Math.abs(itemTime - messageTime) < 120000;
    if (isMatchingPending) {
      replacedPending = true;
      return { ...message, realtime: true };
    }
    return item;
  });

  if (!replacedPending) {
    const exists = nextTranscript.some(
      (item) =>
        item.sender_role === message.sender_role &&
        (item.message_text || "") === (message.message_text || "") &&
        item.created_at === message.created_at,
    );
    if (!exists) nextTranscript.push({ ...message, realtime: true });
  }

  return nextTranscript.sort((left, right) => {
    const leftTime = Date.parse(left.created_at || "") || 0;
    const rightTime = Date.parse(right.created_at || "") || 0;
    return leftTime - rightTime;
  });
}

function createPeerConnection() {
  return new RTCPeerConnection({
    iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
  });
}

function getSkippedFeedbackIds() {
  try {
    const raw = window.localStorage.getItem(SKIPPED_FEEDBACK_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveSkippedFeedbackIds(ids) {
  window.localStorage.setItem(SKIPPED_FEEDBACK_KEY, JSON.stringify(ids));
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

export default function ConsultationPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const transcriptWindowRef = useRef(null);
  const transcriptEndRef = useRef(null);
  const callOverlayRef = useRef(null);
  const callDragStateRef = useRef(null);
  const previousCallStatusRef = useRef(null);
  const handledCallLogKeysRef = useRef(new Set());
  const endedStatusCandidateRef = useRef({ consultationId: "", count: 0 });
  const peerConnectionRef = useRef(null);
  const localStreamRef = useRef(null);
  const remoteStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const localVideoRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const ringtoneIntervalRef = useRef(null);
  const ringtoneAudioContextRef = useRef(null);
  const streamConnectedRef = useRef(false);
  const seenCandidateKeysRef = useRef(new Set());
  const attachmentInputRef = useRef(null);
  const messageInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const voiceChunksRef = useRef([]);
  const voiceStartedAtRef = useRef(0);
  const voiceElapsedBeforePauseRef = useRef(0);
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
  const [activityEvents, setActivityEvents] = useState([]);
  const [documentState, setDocumentState] = useState({
    status: "idle",
    message: "Clinical documents will appear here when the doctor issues them.",
    documents: [],
  });
  const [draftMessage, setDraftMessage] = useState("");
  const [attachmentState, setAttachmentState] = useState({ status: "idle", message: "" });
  const [previewedAssets, setPreviewedAssets] = useState(() => new Set());
  const [voiceRecording, setVoiceRecording] = useState(false);
  const [voicePaused, setVoicePaused] = useState(false);
  const [voiceElapsedSeconds, setVoiceElapsedSeconds] = useState(0);
  const [callState, setCallState] = useState(null);
  const [callUiState, setCallUiState] = useState({
    status: "idle",
    message: "",
    localMediaReady: false,
    audioMuted: false,
    videoDisabled: false,
  });
  const [callWindowMinimized, setCallWindowMinimized] = useState(false);
  const [queuedPromptVisible, setQueuedPromptVisible] = useState(false);
  const autoExpandedVideoCallRef = useRef("");
  const [callWindowPosition, setCallWindowPosition] = useState({ x: null, y: null });
  const [callTimerNow, setCallTimerNow] = useState(() => Date.now());
  const [consultationDetailsOpen, setConsultationDetailsOpen] = useState(false);
  const [backgroundTheme, setBackgroundTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    return window.localStorage.getItem(BACKGROUND_THEME_KEY) || document.body.dataset.backgroundTheme || "dark";
  });
  const [feedbackState, setFeedbackState] = useState({
    visible: false,
    status: "idle",
    message: "Rate and review your doctor before leaving this consultation.",
    rating: 5,
    review: "",
    doctor: null,
    consultationId: "",
  });

  useLayoutEffect(() => {
    const input = messageInputRef.current;
    if (!input) return;
    input.style.height = "auto";
    const nextHeight = Math.max(48, Math.min(input.scrollHeight, 120));
    input.style.height = `${nextHeight}px`;
    input.style.overflowY = input.scrollHeight > 120 ? "auto" : "hidden";
  }, [draftMessage]);
  const feedbackSectionRef = useRef(null);
  const feedbackVisibleRef = useRef(false);
  const statusResultRef = useRef(null);

  useEffect(() => {
    document.body.dataset.backgroundTheme = backgroundTheme;
    window.localStorage.setItem(BACKGROUND_THEME_KEY, backgroundTheme);
  }, [backgroundTheme]);

  useEffect(() => {
    feedbackVisibleRef.current = feedbackState.visible;
  }, [feedbackState.visible]);

  useEffect(() => {
    statusResultRef.current = statusState.result;
  }, [statusState.result]);

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

  function showFeedbackCard(result, message = "Rate and review your doctor before leaving this consultation.") {
    const consultationId = result?.consultation_id || "";
    if (consultationId && getSkippedFeedbackIds().includes(consultationId)) {
      return false;
    }

    feedbackVisibleRef.current = true;
    setFeedbackState({
      visible: true,
      status: "idle",
      message,
      rating: 5,
      review: "",
      doctor: result?.doctor || null,
      consultationId,
    });

    window.setTimeout(() => {
      feedbackSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 200);
    return true;
  }

  function resetEndedStatusCandidate() {
    endedStatusCandidateRef.current = { consultationId: "", count: 0 };
  }

  function maybeShowFeedbackFromEndedStatus(result) {
    if (feedbackVisibleRef.current || result?.status !== "ended") {
      if (result?.status !== "ended") {
        resetEndedStatusCandidate();
      }
      return false;
    }

    const consultationId = result?.consultation_id || statusResultRef.current?.consultation_id || "";
    if (!consultationId || getSkippedFeedbackIds().includes(consultationId)) {
      return false;
    }

    const candidate = endedStatusCandidateRef.current;
    const count = candidate.consultationId === consultationId ? candidate.count + 1 : 1;
    endedStatusCandidateRef.current = { consultationId, count };

    if (count < 2) {
      return false;
    }

    return showFeedbackCard({
      ...result,
      consultation_id: consultationId,
      doctor: result.doctor || statusResultRef.current?.doctor || null,
    });
  }

  function isStaleRoomDowngrade(nextStatus, currentStatus = statusResultRef.current) {
    if (!nextStatus || !currentStatus?.consultation_id) {
      return false;
    }

    if (nextStatus.status === "ended") {
      return false;
    }

    return !nextStatus.consultation_id && ["queued", "not_started", "idle"].includes(nextStatus.status);
  }

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
      if (isStaleRoomDowngrade(result)) {
        return;
      }
      setStatusState({
        status: result.submitted ? "success" : "empty",
        message: result.message,
        result,
      });
      maybeShowFeedbackFromEndedStatus(result);
      setCallState(result.call || null);
      if (result.status === "connected" || result.consultation_id) {
        loadTranscript(referenceToLoad.trim());
        loadDocuments(referenceToLoad.trim());
      } else {
        setTranscriptState({
          status: "idle",
          message: getRoomMessage(result, TRANSCRIPT_PENDING_MESSAGE),
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
      setTranscriptState((current) => ({
        status: result.found ? "success" : "empty",
        message: result.message,
        transcript: mergeTranscriptWithPending(result.transcript || [], current.transcript || []),
      }));
      if (result.call) {
        setCallState(result.call);
      }
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
      if (result.call) {
        setCallState(result.call);
      }
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
    setActivityEvents([]);
    previousCallStatusRef.current = null;
    handledCallLogKeysRef.current = new Set();
  }, [reference]);

  useEffect(() => {
    const connectedAt = getCallDurationAnchor(callState);
    if (callState?.status !== "active" || !connectedAt) {
      return undefined;
    }

    setCallTimerNow(Date.now());
    const timer = window.setInterval(() => {
      setCallTimerNow(Date.now());
    }, 1000);

    return () => window.clearInterval(timer);
  }, [callState?.status, callState?.connected_at, callState?.started_at]);

  useEffect(() => {
    if (!reference.trim()) {
      return undefined;
    }

    streamConnectedRef.current = false;
    const source = createConsultationEventSource(reference);
    source.onopen = () => {
      streamConnectedRef.current = true;
    };
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const nextStatus = payload.status;
        const nextTranscript = payload.transcript;
        const nextDocuments = payload.documents;
        const nextCall = payload.call;
        const hasActiveConsultation = Boolean(nextStatus?.consultation_id);
        if (
          statusResultRef.current?.status === "ended" &&
          feedbackVisibleRef.current &&
          nextStatus?.status !== "ended"
        ) {
          return;
        }
        if (isStaleRoomDowngrade(nextStatus)) {
          return;
        }
        setStatusState({
          status: nextStatus.submitted ? "success" : "empty",
          message: nextStatus.message,
          result: nextStatus,
        });
        setTranscriptState((current) => ({
          status: nextTranscript.found ? "success" : hasActiveConsultation ? "empty" : "idle",
          message: nextTranscript.found
            ? nextTranscript.message
            : getRoomMessage(nextStatus, TRANSCRIPT_PENDING_MESSAGE),
          transcript: mergeTranscriptWithPending(nextTranscript.transcript || [], current.transcript || []),
        }));
        if (nextDocuments) {
          setDocumentState({
            status: nextDocuments?.found ? "success" : hasActiveConsultation ? "empty" : "idle",
            message:
              nextDocuments?.found || hasActiveConsultation
                ? nextDocuments?.message || "No consultation documents yet."
                : "Documents will appear here once the consultation becomes active.",
            documents: nextDocuments?.documents || [],
          });
        }
        setCallState(nextCall || null);
        maybeShowFeedbackFromEndedStatus(nextStatus);
      } catch {}
    };

    source.onerror = () => {
      streamConnectedRef.current = false;
      setTranscriptState((current) => ({
        ...current,
        status: current.transcript.length ? current.status : "error",
        message: current.transcript.length
          ? current.message
          : "Live consultation stream disconnected. You can still keep working here.",
      }));
    };

    return () => {
      streamConnectedRef.current = false;
      source.close();
    };
  }, [reference]);

  useEffect(() => {
    if (!reference.trim()) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "hidden" || feedbackState.visible || streamConnectedRef.current) {
        return;
      }
      loadStatus(reference, { silent: true });
    }, 10000);

    return () => window.clearInterval(intervalId);
  }, [reference, feedbackState.visible]);

  useEffect(() => {
    const consultationId = statusState.result?.consultation_id;
    if (!reference.trim() || !consultationId) {
      return undefined;
    }

    const socket = createConsultationWebSocket(reference.trim());
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type !== "message" || !payload.message) return;
        setTranscriptState((current) => ({
          ...current,
          status: "success",
          transcript: mergeRealtimeMessage(current.transcript || [], payload.message),
        }));
      } catch {}
    };

    return () => socket.close();
  }, [reference, statusState.result?.consultation_id]);

  useEffect(() => {
    if (statusState.result?.status !== "ended" || feedbackState.visible) {
      return;
    }

    const consultationId = statusState.result?.consultation_id || "";
    if (consultationId && getSkippedFeedbackIds().includes(consultationId)) {
      return;
    }

    maybeShowFeedbackFromEndedStatus(statusState.result);
  }, [statusState.result, feedbackState.visible]);

  useEffect(() => {
    if (
      statusState.result?.status === "ended" ||
      statusState.result?.status === "not_started"
    ) {
      return;
    }

    setFeedbackState((current) =>
      current.visible
        ? {
            ...current,
            visible: false,
            consultationId: "",
          }
        : current,
    );
  }, [statusState.result?.status]);

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
      const width = Math.min(220, Math.max(160, window.innerWidth * 0.28));
      return {
        x: Math.max(12, window.innerWidth - width - 20),
        y: Math.max(88, window.innerHeight - 220),
      };
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

  function toggleLocalAudio() {
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

  function toggleLocalVideo() {
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
        await sendConsultationCallCandidate({
          reference,
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

  async function handleStartCall(callType) {
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
      const result = await startConsultationCall({
        reference,
        call_type: callType,
        offer_sdp: {
          type: offer.type,
          sdp: offer.sdp,
        },
      });
      if (!result.ok) {
        throw new Error(result.message || "Unable to start the call right now.");
      }
      setCallState(result.call || null);
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

  async function handleAcceptIncomingCall() {
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
      const result = await acceptConsultationCall({
        reference,
        answer_sdp: {
          type: answer.type,
          sdp: answer.sdp,
        },
      });
      if (!result.ok) {
        throw new Error(result.message || "Unable to accept the call right now.");
      }
      setCallState(result.call || null);
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

  async function handleRejectIncomingCall() {
    try {
      const result = await rejectConsultationCall(reference);
      if (!result.ok) {
        throw new Error(result.message || "Unable to reject the call right now.");
      }
      setCallState(result.call || null);
      closeCallMedia();
    } catch (error) {
      setCallUiState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to reject the call right now.",
      }));
    }
  }

  async function handleEndCurrentCall() {
    try {
      const result = await endConsultationCall(reference);
      if (!result.ok) {
        throw new Error(result.message || "Unable to end the call right now.");
      }
      setCallState(result.call || null);
    } catch (error) {
      setCallUiState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to end the call right now.",
      }));
    } finally {
      closeCallMedia();
    }
  }

  async function handleSendMessage(event) {
    event.preventDefault();
    if (!draftMessage.trim()) {
      return;
    }

    if (roomNeedsInitialSymptoms) {
      setConsultationStateFromSymptoms(draftMessage.trim());
      return;
    }

    const messageText = draftMessage.trim();
    const optimisticMessage = {
      sender_role: "patient_web",
      sender_id: statusState.result?.patient?.internal_id || "patient",
      message_text: messageText,
      asset_url: null,
      asset_type: null,
      created_at: new Date().toISOString(),
      optimistic: true,
    };

    setDraftMessage("");
    if (messageInputRef.current) {
      messageInputRef.current.style.height = "auto";
      messageInputRef.current.style.overflowY = "hidden";
    }
    setTranscriptState((current) => ({
      status: "success",
      message: current.message,
      transcript: [...(current.transcript || []), optimisticMessage],
    }));

    sendConsultationMessage({
        reference,
        message_text: messageText,
      })
      .then((result) => {
      setTranscriptState((current) => ({
        status: "success",
        message: current.message,
        transcript: result.transcript?.length
          ? mergeTranscriptWithPending(result.transcript, current.transcript || [])
          : current.transcript,
      }));
      })
      .catch(() => {
      setTranscriptState((current) => ({
        ...current,
        status: "error",
        message: "Unable to send your message right now.",
      }));
      });
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

  async function uploadPatientAttachment(file) {
    if (!reference.trim() || !file || roomWaitingForDoctor || roomNeedsInitialSymptoms) {
      return;
    }

    try {
      setAttachmentState({ status: "loading", message: "Sending attachment..." });
      const result = await sendConsultationAttachment(reference.trim(), file);
      setTranscriptState({
        status: result.sent ? "success" : "empty",
        message: result.message,
        transcript: result.transcript || [],
      });
      if (result.call) {
        setCallState(result.call);
      }
      setAttachmentState({ status: "success", message: result.message });
    } catch {
      setAttachmentState({ status: "error", message: "Unable to send attachment right now." });
    }
  }

  function handlePatientAttachmentChange(event) {
    const [file] = Array.from(event.target.files || []);
    event.target.value = "";
    if (file) {
      uploadPatientAttachment(file);
    }
  }

  async function handlePatientVoiceMessage() {
    if (voiceRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }

    if (roomWaitingForDoctor || roomNeedsInitialSymptoms) {
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
          uploadPatientAttachment(new File([blob], `voice-message-${Date.now()}.webm`, { type: blob.type }));
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

  function handlePatientVoicePauseToggle() {
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

  async function setConsultationStateFromSymptoms(symptoms) {
    setConsultationStateMessage("Submitting your consultation request...");

    try {
      const result = await requestConsultation({
        reference,
        symptoms,
      });
      setStatusState({
        status: result.submitted ? "success" : "error",
        message: result.message,
        result,
      });
      setDraftMessage("");
      if (result.submitted) {
        setTranscriptState({
          status: result.status === "connected" ? "success" : "idle",
          message:
            result.status === "connected"
              ? "Consultation started. You may continue typing here."
              : getRoomMessage(result, TRANSCRIPT_PENDING_MESSAGE),
          transcript: [],
        });
        if (result.consultation_id || result.status === "connected") {
          loadTranscript(reference);
          loadDocuments(reference);
        }
      }
    } catch (error) {
      setStatusState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to submit consultation request right now.",
      }));
    }
  }

  function setConsultationStateMessage(message) {
    setTranscriptState((current) => ({
      ...current,
      status: current.status === "success" ? current.status : "idle",
      message,
    }));
  }

  async function handleEndChat() {
    if (!reference.trim()) {
      return;
    }

    try {
      const result = await endConsultation(reference.trim());
      setStatusState((current) => ({
        status: result.ended ? "success" : "error",
        message: result.message,
        result: result.ended
          ? {
              ...(current.result || {}),
              status: "ended",
              consultation_id: result.consultation_id || current.result?.consultation_id || "",
              doctor: result.doctor || current.result?.doctor || null,
            }
          : current.result,
      }));
      setTranscriptState((current) => ({
        ...current,
        status: current.transcript.length ? current.status : "idle",
        message: "Consultation ended.",
      }));
      setCallState(null);
      setFeedbackState({
        visible: false,
        status: "idle",
        message: "Rate and review your doctor before leaving this consultation.",
        rating: 5,
        review: "",
        doctor: null,
        consultationId: "",
      });
      if (result.ended && result.consultation_id) {
        resetEndedStatusCandidate();
        showFeedbackCard({
          consultation_id: result.consultation_id || "",
          doctor: result.doctor,
        });
      }
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
      if (feedbackState.consultationId) {
        const nextIds = getSkippedFeedbackIds().filter((item) => item !== feedbackState.consultationId);
        saveSkippedFeedbackIds(nextIds);
      }
      setFeedbackState((current) => ({
        ...current,
        status: result.saved ? "success" : "error",
        message: result.message,
      }));
      if (result.saved) {
        window.setTimeout(() => {
          navigate("/patient", { replace: true });
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

  function handleSkipFeedback() {
    if (feedbackState.consultationId) {
      const nextIds = Array.from(new Set([...getSkippedFeedbackIds(), feedbackState.consultationId]));
      saveSkippedFeedbackIds(nextIds);
    }
    setFeedbackState((current) => ({
      ...current,
      visible: false,
      status: "idle",
      message: "Rate and review your doctor before leaving this consultation.",
    }));
    feedbackVisibleRef.current = false;
    navigate("/patient", { replace: true });
  }

  function renderTranscriptAsset(item) {
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

  const timelineItems = [
    ...(transcriptState.transcript || []).map((item, index) => ({
      kind: "message",
      created_at: item.created_at,
      sortKey: `${item.created_at || ""}-message-${index}`,
      payload: item,
    })),
    ...(documentState.documents || []).map((item, index) => ({
      kind: "document",
      created_at: item.created_at,
      sortKey: `${item.created_at || ""}-document-${index}`,
      payload: item,
    })),
    ...activityEvents.map((item) => ({
      kind: "activity",
      created_at: item.created_at,
      sortKey: `${item.created_at || ""}-activity-${item.id}`,
      payload: item,
    })),
  ].sort((left, right) => {
    const leftTime = Date.parse(left.created_at || "") || 0;
    const rightTime = Date.parse(right.created_at || "") || 0;
    if (leftTime !== rightTime) {
      return leftTime - rightTime;
    }
    return left.sortKey.localeCompare(right.sortKey);
  });

  const roomNeedsInitialSymptoms =
    !statusState.result?.consultation_id &&
    ["not_started", "missing_payment", "payment_not_verified", "idle"].includes(
      statusState.result?.status || "not_started",
    );
  const roomWaitingForDoctor =
    !statusState.result?.consultation_id && statusState.result?.status === "queued";
  const roomStatusMessage = roomNeedsInitialSymptoms
    ? INITIAL_ROOM_MESSAGE
    : roomWaitingForDoctor
      ? QUEUED_ROOM_MESSAGE
      : transcriptState.message;
  const showRoomLoader =
    statusState.status === "loading" &&
    !statusState.result?.consultation_id &&
    !timelineItems.length;
  const roomMetaMessage =
    statusState.result?.consultation_id && transcriptState.status === "error" ? transcriptState.message : "";

  useEffect(() => {
    if (roomWaitingForDoctor) {
      setQueuedPromptVisible(true);
    } else {
      setQueuedPromptVisible(false);
    }
  }, [roomWaitingForDoctor]);

  useEffect(() => {
    if (!roomWaitingForDoctor) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      setQueuedPromptVisible((current) => !current);
    }, 60000);

    return () => window.clearTimeout(timer);
  }, [roomWaitingForDoctor, queuedPromptVisible]);

  useEffect(() => {
    if (
      !shouldAutoFocusChatComposer() ||
      roomWaitingForDoctor ||
      voiceRecording ||
      feedbackState.visible
    ) {
      return;
    }

    focusChatComposer(messageInputRef.current);
  }, [
    feedbackState.visible,
    roomNeedsInitialSymptoms,
    roomWaitingForDoctor,
    statusState.result?.consultation_id,
    statusState.result?.status,
    voiceRecording,
  ]);

  useLayoutEffect(() => {
    if (!timelineItems.length) {
      return;
    }

    if (transcriptWindowRef.current) {
      window.requestAnimationFrame(() => {
        if (transcriptWindowRef.current) {
          transcriptWindowRef.current.scrollTop = transcriptWindowRef.current.scrollHeight;
        }
      });
      return;
    }

    transcriptEndRef.current?.scrollIntoView({
      behavior: "auto",
      block: "end",
    });
  }, [timelineItems.length, timelineItems[timelineItems.length - 1]?.sortKey, draftMessage]);

  useEffect(() => {
    async function syncCallState() {
      if (!callState) {
        return;
      }

      if (callState.status === "ended" || callState.status === "rejected") {
        closeCallMedia();
        return;
      }

      const peer = peerConnectionRef.current;
      if (!peer) {
        return;
      }

      if (callState.answer_sdp && peer.localDescription?.type === "offer" && !peer.currentRemoteDescription) {
        try {
          await peer.setRemoteDescription(new RTCSessionDescription(callState.answer_sdp));
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

      for (const candidate of callState.doctor_candidates || []) {
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

    syncCallState();
  }, [callState, reference]);

  useEffect(() => {
    const previousStatus = previousCallStatusRef.current;
    const nextStatus = callState?.status || null;
    const endedOrRejected = ["ended", "rejected"].includes(nextStatus || "");

    if (callState?.started_at && endedOrRejected) {
      const logKey = [
        callState.consultation_id || reference || "consultation",
        callState.started_at || "",
        callState.updated_at || "",
        callState.status || "",
      ].join(":");

      if (!handledCallLogKeysRef.current.has(logKey)) {
        const callTypeLabel = (callState.call_type || "voice").replace(/^./, (letter) => letter.toUpperCase());
        const endedAt = callState.updated_at || new Date().toISOString();
        const connectedAt = callState.connected_at || null;
        const duration = connectedAt ? formatCallDuration(connectedAt, endedAt) : "";
        const patientStartedCall = callState.initiated_by === "patient";
        const connectedBeforeClosing = previousStatus === "active" || Boolean(connectedAt);
        let title = (connectedBeforeClosing ? "\u260E " : callTypeLabel === "Video" ? "\uD83C\uDFA5 " : "\uD83D\uDCF5 ") + callTypeLabel + " call";
        let body = connectedBeforeClosing ? duration : "";
        let tone = connectedBeforeClosing ? "success" : "danger";

        if (!connectedBeforeClosing && nextStatus === "ended") {
          title = patientStartedCall
            ? (callTypeLabel === "Video" ? "\uD83C\uDFA5" : "\uD83D\uDCF4") + " " + callTypeLabel + " call not answered"
            : (callTypeLabel === "Video" ? "\uD83C\uDFA5" : "\uD83D\uDCF5") + " Missed " + callTypeLabel.toLowerCase() + " call";
        } else if (!connectedBeforeClosing && nextStatus === "rejected") {
          title = patientStartedCall ? "\uD83D\uDEAB " + callTypeLabel + " call rejected" : "\uD83D\uDEAB " + callTypeLabel + " call declined";
        }
        appendActivityEvent({
          kind: "call",
          align: patientStartedCall ? "patient" : "doctor",
          title,
          body,
          tone,
          created_at: endedAt,
        });
        handledCallLogKeysRef.current.add(logKey);
      }

      previousCallStatusRef.current = nextStatus;
      return;
    }

    previousCallStatusRef.current = nextStatus;
  }, [callState, statusState.result?.doctor?.name]);

  useEffect(
    () => () => {
      stopCallWindowDrag();
      stopRingtone();
      closeCallMedia();
    },
    [],
  );

  const activeCall = callState?.status === "active";
  const incomingCall = callState?.status === "ringing" && callState?.initiated_by === "doctor";
  const acceptingIncomingCall = incomingCall && ["connecting", "active"].includes(callUiState.status);
  const outgoingCall = callState?.status === "ringing" && callState?.initiated_by === "patient";
  const effectiveActiveCall = activeCall || callUiState.status === "active";
  const hasCallInProgress =
    ["ringing", "active", "connecting"].includes(callState?.status || "") ||
    ["ringing", "active", "connecting", "starting"].includes(callUiState.status);
  const hasLocalVideoTrack = Boolean(localStreamRef.current?.getVideoTracks().length);
  const showVideoCallLayout = callState?.call_type === "video" || hasLocalVideoTrack;
  const showSelfPreviewAsMain = showVideoCallLayout && !effectiveActiveCall;
  const activeVideoControlsOnly = showVideoCallLayout && effectiveActiveCall;
  const callTimerLabel =
    effectiveActiveCall && getCallDurationAnchor(callState)
      ? formatCallDuration(getCallDurationAnchor(callState), new Date(callTimerNow).toISOString())
      : "";
  const callStatusLabel =
    callUiState.message ||
    (incomingCall
      ? `Incoming ${callState?.call_type || "voice"} call from ${formatDoctorDisplayName(statusState.result?.doctor?.name)}`
      : outgoingCall
        ? `${callState?.call_type === "video" ? "Video" : "Voice"} call is ringing...`
        : effectiveActiveCall
          ? `${callState?.call_type === "video" ? "Video" : "Voice"} call connected`
          : "");

  useEffect(() => {
    const callKey = callState?.consultation_id || statusState.result?.consultation_id || "";
    if (callState?.call_type === "video" && effectiveActiveCall && autoExpandedVideoCallRef.current !== callKey) {
      autoExpandedVideoCallRef.current = callKey;
      setCallWindowMinimized(false);
    }
    if (!effectiveActiveCall) {
      autoExpandedVideoCallRef.current = "";
    }
  }, [callState?.call_type, callState?.consultation_id, effectiveActiveCall, statusState.result?.consultation_id]);

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
  }, [callUiState.localMediaReady, callState?.status, callState?.call_type, callWindowMinimized, effectiveActiveCall]);

  useEffect(() => {
    if (effectiveActiveCall || callUiState.status === "connecting") {
      stopRingtone();
      return;
    }

    if (incomingCall) {
      startRingtone("incoming");
      return;
    }

    if (outgoingCall || callUiState.status === "starting") {
      startRingtone("outgoing");
      return;
    }

    stopRingtone();
  }, [effectiveActiveCall, incomingCall, outgoingCall, callUiState.status]);

  const callOverlay =
    effectiveActiveCall || incomingCall || outgoingCall || callUiState.localMediaReady
      ? createPortal(
          <div
            ref={callOverlayRef}
            className={
              callWindowMinimized
                ? "consultation-call-overlay consultation-call-overlay--minimized"
                : "consultation-call-overlay consultation-call-overlay--centered"
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
                  ? "consultation-call-stage consultation-call-stage--overlay consultation-call-stage--minimized"
                  : `consultation-call-stage consultation-call-stage--overlay${
                      showVideoCallLayout ? " consultation-call-stage--video" : " consultation-call-stage--voice"
                    }${activeVideoControlsOnly ? " consultation-call-stage--controls-only" : ""}`
              }
            >
              <audio ref={remoteAudioRef} autoPlay playsInline className="consultation-call-stage__audio" />
              {!showVideoCallLayout ? (
                <div className="consultation-call-stage__voice-avatar">
                  {getCallStageInitials(statusState.result?.doctor?.name, "D")}
                </div>
              ) : null}
              {showVideoCallLayout ? (
                <>
                  {showSelfPreviewAsMain ? (
                    <video
                      ref={localVideoRef}
                      className="consultation-call-stage__remote consultation-call-stage__remote--self"
                      autoPlay
                      muted
                      playsInline
                    />
                  ) : (
                    <video ref={remoteVideoRef} className="consultation-call-stage__remote" autoPlay playsInline />
                  )}
                  {effectiveActiveCall ? (
                    <video ref={localVideoRef} className="consultation-call-stage__local" autoPlay muted playsInline />
                  ) : null}
                </>
              ) : null}
              <div
                className={
                  callWindowMinimized
                    ? "consultation-call-stage__sheet consultation-call-stage__sheet--minimized"
                    : "consultation-call-stage__sheet"
                }
              >
                {!activeVideoControlsOnly ? <div className="consultation-call-stage__topline">
                  <span className="consultation-call-stage__mode">
                    {callState?.call_type === "video" ? "Video Call" : "Voice Call"}
                  </span>
                  <button className="consultation-call-overlay__toggle" type="button" onClick={handleCallWindowToggle}>
                    {callWindowMinimized ? "Expand" : "Minimize"}
                  </button>
                </div> : null}
                {!activeVideoControlsOnly ? <div className="consultation-call-stage__identity">
                  <div className="consultation-call-stage__avatar">
                    {getDisplayInitials(statusState.result?.doctor?.name)}
                  </div>
                  <div className="consultation-call-stage__copy">
                    <strong>{formatDoctorDisplayName(statusState.result?.doctor?.name)}</strong>
                    <span>{callStatusLabel || "Preparing call..."}</span>
                    {callTimerLabel ? <span className="consultation-call-stage__timer">{callTimerLabel}</span> : null}
                  </div>
                </div> : null}
                <div className="consultation-call-stage__controls">
                  {incomingCall && !acceptingIncomingCall ? (
                    <>
                      <button className="button button--primary" type="button" onClick={handleAcceptIncomingCall}>
                        Accept
                      </button>
                      <button className="button button--secondary" type="button" onClick={handleRejectIncomingCall}>
                        Decline
                      </button>
                    </>
                  ) : null}
                  {(outgoingCall || effectiveActiveCall || acceptingIncomingCall || callUiState.localMediaReady) &&
                  !(incomingCall && !acceptingIncomingCall) ? (
                    <>
                      {callUiState.localMediaReady ? (
                        <button className="button button--secondary" type="button" onClick={toggleLocalAudio}>
                          {callUiState.audioMuted ? "Unmute" : "Mute"}
                        </button>
                      ) : null}
                      {callUiState.localMediaReady && hasLocalVideoTrack ? (
                        <button className="button button--secondary" type="button" onClick={toggleLocalVideo}>
                          {callUiState.videoDisabled ? "Camera On" : "Camera Off"}
                        </button>
                      ) : null}
                      <button className="button button--secondary" type="button" onClick={handleEndCurrentCall}>
                        {effectiveActiveCall ? "End Call" : "Cancel"}
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

  return (
    <div className="consultation-layout">
      <div className="consultation-toolbar">
        <button className="consultation-toolbar__back" type="button" onClick={() => navigate("/patient")}>
          {"\u2190"} Back to patient home
        </button>
      </div>

      <SectionCard
        title=""
        subtitle=""
      >
        <div className={`consultation-room consultation-room--${transcriptState.status}`}>
          <div className="consultation-floating-theme" aria-label="Theme">
            {BACKGROUND_OPTIONS.map((option) => (
              <button
                key={option.key}
                className={
                  backgroundTheme === option.key
                    ? "site-shell__theme-toggle site-shell__theme-toggle--active"
                    : "site-shell__theme-toggle"
                }
                type="button"
                onClick={() => setBackgroundTheme(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="consultation-room__workspace">
            <aside className="consultation-room__sidebar">
              <div
                className={
                  consultationDetailsOpen
                    ? `consultation-overview consultation-overview--sticky consultation-overview--open consultation-overview--${statusState.status}`
                    : `consultation-overview consultation-overview--sticky consultation-overview--collapsed consultation-overview--${statusState.status}`
                }
              >
                <button
                  aria-expanded={consultationDetailsOpen}
                  className="consultation-overview__toggle"
                  type="button"
                  onClick={() => setConsultationDetailsOpen((current) => !current)}
                >
                  <span>Consultation details</span>
                  <span aria-hidden="true">{consultationDetailsOpen ? "\u2212" : "+"}</span>
                </button>
                <div
                  className={
                    consultationDetailsOpen
                      ? "consultation-overview__content consultation-overview__content--open"
                      : "consultation-overview__content"
                  }
                >
                  <div className="consultation-overview__topline">
                    <div className="consultation-overview__identity">
                      <span className="consultation-room__eyebrow">Patient</span>
                      <h3>{statusState.result?.patient?.name || "Patient"}</h3>
                      <p>{statusState.result?.patient?.hospital_number || "Hospital number pending"}</p>
                    </div>
                    <div className="consultation-overview__reference">
                      <span className="consultation-room__eyebrow">Payment Reference</span>
                      <strong>{reference || "No reference"}</strong>
                    </div>
                  </div>

                  <div className="consultation-summary-grid">
                    <article className="consultation-room__panel">
                      <span className="consultation-room__eyebrow">State</span>
                      <h3>{statusState.result?.status || "Waiting"}</h3>
                    </article>

                    <article className="consultation-room__panel consultation-room__panel--wide">
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
              </div>

              <div className="consultation-room__meta">
                {showRoomLoader ? (
                  <BrandedLoader compact label={roomStatusMessage} />
                ) : roomMetaMessage ? <p className="consultation-status__message">{roomMetaMessage}</p> : null}
              </div>

              {statusState.result?.consultation_id ? (
                <div className="consultation-callbar">
                  <div className="consultation-callbar__actions">
                    <button
                      className="button button--secondary"
                      type="button"
                      disabled={hasCallInProgress}
                      onClick={() => handleStartCall("voice")}
                    >
                      {"\u260E"} Voice Call
                    </button>
                    <button
                      className="button button--secondary"
                      type="button"
                      disabled={hasCallInProgress}
                      onClick={() => handleStartCall("video")}
                    >
                      {"\u25B6"} Video Call
                    </button>
                  </div>
                </div>
              ) : null}

              {statusState.result?.consultation_id && documentState.documents.length ? (
                <details className="consultation-mobile-documents">
                  <summary>
                    <span>Clinical Documents</span>
                    <strong>{documentState.documents.length}</strong>
                  </summary>
                  <div className="consultation-mobile-documents__list">
                    {documentState.documents.map((item) => (
                      <article className="consultation-mobile-document" key={`${item.kind}-${item.document_id}`}>
                        <div>
                          <strong>{getConsultationDocumentTitle(item.kind)}</strong>
                          <span>{formatChatTimestamp(item.created_at)}</span>
                        </div>
                        <div>
                          <a href={`${API_BASE_URL}${item.asset_url}`} target="_blank" rel="noreferrer">
                            Preview
                          </a>
                          <a href={`${API_BASE_URL}${item.asset_url}`} download={getConsultationDocumentDownloadName(item)}>
                            Download
                          </a>
                        </div>
                      </article>
                    ))}
                  </div>
                </details>
              ) : null}
            </aside>

            <section className="consultation-room__chatpane">
              <div className="consultation-chat-header">
                <button className="consultation-toolbar__back consultation-toolbar__back--inline" type="button" onClick={() => navigate("/patient")}>
                  {"\u2190"} Back
                </button>
                <div className="consultation-chat-header__copy">
                  <h2>{statusState.result?.doctor?.name ? formatDoctorDisplayName(statusState.result.doctor.name) : "Waiting for doctor"}</h2>
                  <p>{statusState.result?.status || "Waiting"}</p>
                </div>
              </div>

          <div ref={transcriptWindowRef} className="transcript-window transcript-window--large">
            {timelineItems.length ? (
              timelineItems.map((entry) =>
                entry.kind === "document" ? (
                  <article
                    key={`${entry.payload.kind}-${entry.payload.document_id}-${entry.payload.created_at}`}
                    className="transcript-document-card"
                  >
                    <div className="transcript-document-card__copy">
                      <span className="consultation-room__eyebrow">{entry.payload.title}</span>
                      <h4>{getConsultationDocumentTitle(entry.payload.kind)} ready</h4>
                      <p>{formatChatTimestamp(entry.payload.created_at)}</p>
                    </div>
                    <div className="document-card__actions">
                      <a
                        className="button button--secondary"
                        href={`${API_BASE_URL}${entry.payload.asset_url}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Preview
                      </a>
                      <a
                        className="button button--primary"
                        href={`${API_BASE_URL}${entry.payload.asset_url}`}
                        download={getConsultationDocumentDownloadName(entry.payload)}
                      >
                        Download
                      </a>
                    </div>
                  </article>
                ) : entry.kind === "activity" ? (
                  <article
                    key={entry.payload.id}
                    className={`transcript-system-card transcript-system-card--${entry.payload.align || "center"} transcript-system-card--${entry.payload.tone || "neutral"}`}
                  >
                    <span className="transcript-system-card__title">{entry.payload.title}</span>
                    {entry.payload.body ? <p>{entry.payload.body}</p> : null}
                    <time className="transcript-bubble__time">{formatChatTimestamp(entry.payload.created_at)}</time>
                  </article>
                ) : (
                  <article
                    key={`${entry.payload.created_at}-${entry.sortKey}`}
                    className={
                      entry.payload.sender_role === "patient" || entry.payload.sender_role === "patient_web"
                        ? "transcript-bubble transcript-bubble--patient"
                        : "transcript-bubble transcript-bubble--doctor"
                    }
                  >
                    <span className="transcript-bubble__role">
                      {getConsultationSenderLabel(entry.payload.sender_role, statusState.result)}
                    </span>
                    {renderTranscriptAsset(entry.payload)}
                    <p>{entry.payload.message_text}</p>
                    <time className="transcript-bubble__time">{formatChatTimestamp(entry.payload.created_at)}</time>
                  </article>
                ),
              )
            ) : (
              <p className="consultation-status__message">
                {statusState.result?.consultation_id ? roomStatusMessage : ""}
              </p>
            )}
            <div ref={transcriptEndRef} />
          </div>

          <div className="consultation-room__composer">
            <form
              className={
                roomNeedsInitialSymptoms
                  ? "form-panel form-panel--inline consultation-compose consultation-compose--initial"
                  : voiceRecording
                    ? "form-panel form-panel--inline consultation-compose consultation-compose--recording"
                  : "form-panel form-panel--inline consultation-compose"
              }
              onSubmit={handleSendMessage}
            >
              <input
                ref={attachmentInputRef}
                type="file"
                accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx,.txt"
                hidden
                onChange={handlePatientAttachmentChange}
              />
              {!roomNeedsInitialSymptoms && !voiceRecording ? (
                <button
                  className="chat-tool-button"
                  type="button"
                  disabled={roomWaitingForDoctor}
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
                    onClick={handlePatientVoicePauseToggle}
                    aria-label={voicePaused ? "Resume voice recording" : "Pause voice recording"}
                    title={voicePaused ? "Resume voice recording" : "Pause voice recording"}
                  >
                    {voicePaused ? "\u25CF" : "\u23F8"}
                  </button>
                </div>
              ) : (
                <label className="form-field form-field--grow">
                  <span className="form-field__label">Message</span>
                  <textarea
                    className="form-field__input"
                    ref={messageInputRef}
                    rows="1"
                    disabled={roomWaitingForDoctor}
                    placeholder={
                      roomNeedsInitialSymptoms
                        ? "Describe how you're feeling..."
                        : roomWaitingForDoctor
                          ? "Waiting for doctor to join..."
                          : "Type your update to the doctor..."
                    }
                    value={draftMessage}
                    onChange={(event) => setDraftMessage(event.target.value)}
                    onKeyDown={handleChatComposerKeyDown}
                  />
                </label>
              )}
              {roomNeedsInitialSymptoms ? (
                <button className="button button--primary" type="submit" disabled={roomWaitingForDoctor}>
                  Start Consultation
                </button>
              ) : draftMessage.trim() ? (
                <button
                  className="chat-tool-button chat-tool-button--send"
                  type="submit"
                  disabled={roomWaitingForDoctor}
                  aria-label="Send message"
                  title="Send message"
                >
                  <SendMessageIcon />
                </button>
              ) : (
                <button
                  className={voiceRecording ? "chat-tool-button chat-tool-button--recording" : "chat-tool-button"}
                  type="button"
                  disabled={roomWaitingForDoctor}
                  onClick={handlePatientVoiceMessage}
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

            {statusState.result?.consultation_id ? (
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
            ) : null}
          </div>
            </section>
          </div>
        </div>
      </SectionCard>
      {callOverlay}

      {queuedPromptVisible && roomWaitingForDoctor
        ? createPortal(
            <div className="consultation-queue-overlay" aria-live="polite">
              <div className="consultation-queue-card">
                <div className="consultation-feedback-card__header">
                  <span className="consultation-call-stage__mode">Queued</span>
                </div>
                <div className="consultation-feedback-card__body">
                  <h3>{QUEUED_PROMPT_TITLE}</h3>
                  <p className="consultation-status__message">{QUEUED_PROMPT_MESSAGE}</p>
                  <BrandedLoader compact label="Waiting for doctor..." />
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {feedbackState.visible
        ? createPortal(
            <div className="consultation-feedback-overlay">
              <div
                ref={feedbackSectionRef}
                className={`consultation-feedback-card consultation-feedback-card--${feedbackState.status}`}
              >
                <div className="consultation-feedback-card__header">
                  <span className="consultation-call-stage__mode">Rate And Review</span>
                </div>
                <div className="consultation-feedback-card__body">
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
                            {"\u2605"}
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
                    <div className="consultation-feedback-card__actions">
                      <button className="button button--primary" type="submit">
                        Submit Rating And Review
                      </button>
                      <button className="button button--secondary" type="button" onClick={handleSkipFeedback}>
                        Skip
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
