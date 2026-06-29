import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { restoreSession } from "../api/auth.js";
import { fetchConsultationStatus } from "../api/consultations.js";
import { fetchCurrentPatient, fetchPatientHistory } from "../api/patients.js";
import { fetchCurrentPaymentStatus } from "../api/payments.js";
import { fetchHealthTips } from "../api/admin.js";
import "../styles/patient-portal.css";

const actionCards = [
  {
    key: "consultation",
    title: "Start Consultation",
    body: "Continue into consultation. SynMed keeps a valid 24-hour payment window and only asks you to pay when needed.",
    to: "/patient/consultation",
    tone: "primary",
  },
  {
    key: "appointments",
    title: "Book Appointment",
    body: "Schedule a review, choose pay now or pay later, and keep appointment continuity without losing context.",
    to: "/patient/appointments",
    tone: "default",
  },
  {
    key: "history",
    title: "Past History",
    body: "Review previous diagnoses and clinical notes from your earlier SynMed consultations.",
    to: "/patient/history",
    tone: "default",
  },
  {
    key: "medicalReport",
    title: "Medical Report",
    body: "Request a medical report from your consultation record when you need formal documentation.",
    to: "/patient/medical-report-request",
    tone: "default",
  },
];

const fallbackPatientTips = [
  {
    title: "Patient Record",
    body: "Your biodata, documents, and previous diagnoses stay close so every return visit begins with better context.",
  },
  {
    title: "Care Access",
    body: "If a valid same-day payment still exists, SynMed reuses it. If not, you are prompted clearly before consultation starts.",
  },
  {
    title: "Consultation Window",
    body: "Recent clinical documents stay easier to reach while your current consultation window is still active.",
  },
];

function createEmptyPatient() {
  return {
    name: "",
    hospital_number: "",
    phone: "",
    email: "",
    allergy: "",
    medical_conditions: "",
  };
}

function parseTimestamp(value) {
  const parsed = value ? Date.parse(value) : NaN;
  return Number.isNaN(parsed) ? 0 : parsed;
}

export default function PatientWorkspaceHomePage() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState(createEmptyPatient);
  const [paymentState, setPaymentState] = useState({
    status: "idle",
    active: false,
  });
  const [activeConsultationState, setActiveConsultationState] = useState({
    reference: "",
    status: "",
  });
  const [historyState, setHistoryState] = useState({
    status: "idle",
    history: null,
  });
  const [currentFeedIndex, setCurrentFeedIndex] = useState(0);
  const [patientTips, setPatientTips] = useState(fallbackPatientTips);

  useEffect(() => {
    let ignore = false;

    async function loadWorkspace() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "patient") {
          return;
        }

        const [profileResult, historyResult, paymentResult] = await Promise.all([
          fetchCurrentPatient(),
          fetchPatientHistory(),
          fetchCurrentPaymentStatus(),
        ]);
        let activeConsultation = {
          reference: "",
          status: "",
        };
        const paymentReference = paymentResult.payment?.reference || "";

        if (paymentResult.active && paymentReference) {
          try {
            const consultationStatus = await fetchConsultationStatus(paymentReference);
            const consultationStillOpen =
              consultationStatus.status === "queued" ||
              consultationStatus.status === "connected" ||
              Boolean(consultationStatus.consultation_id);

            if (consultationStillOpen && consultationStatus.status !== "ended") {
              activeConsultation = {
                reference: paymentReference,
                status: consultationStatus.status || "connected",
              };
            }
          } catch {}
        }

        if (!ignore) {
          setProfile(profileResult.patient || createEmptyPatient());
          setHistoryState({
            status: "success",
            history: historyResult.history,
          });
          setPaymentState({
            status: "success",
            active: Boolean(paymentResult.active && paymentResult.payment?.reference),
          });
          setActiveConsultationState(activeConsultation);
        }
      } catch {
        if (!ignore) {
          setHistoryState({
            status: "idle",
            history: null,
          });
          setPaymentState({
            status: "idle",
            active: false,
          });
          setActiveConsultationState({
            reference: "",
            status: "",
          });
        }
      }
    }

    loadWorkspace();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setCurrentFeedIndex((current) => (current + 1) % patientTips.length);
    }, 7000);

    return () => window.clearInterval(intervalId);
  }, [patientTips.length]);

  useEffect(() => {
    let ignore = false;
    async function loadPatientTips() {
      try {
        const result = await fetchHealthTips("patient");
        if (!ignore && result.tips?.length) {
          setPatientTips(result.tips);
          setCurrentFeedIndex(0);
        }
      } catch {}
    }
    loadPatientTips();
    return () => {
      ignore = true;
    };
  }, []);

  const latestDiagnosisEntries = [
    ...(historyState.history?.consultations || []).map((item) => ({
      diagnosis: item.diagnosis || "",
      created_at: item.created_at,
      priority: 1,
    })),
    ...(historyState.history?.prescriptions || []).map((item) => ({
      diagnosis: item.diagnosis || "",
      created_at: item.created_at,
      priority: 2,
    })),
    ...(historyState.history?.investigations || []).map((item) => ({
      diagnosis: item.diagnosis || "",
      created_at: item.created_at,
      priority: 2,
    })),
  ]
    .filter((item) => item.diagnosis && item.diagnosis !== "N/A")
    .sort((left, right) => {
      const timeDifference = parseTimestamp(right.created_at) - parseTimestamp(left.created_at);
      return timeDifference || right.priority - left.priority;
    });

  const latestConsultation = historyState.history?.consultations?.[0] || null;
  const latestDiagnosis =
    latestDiagnosisEntries[0]?.diagnosis ||
    (latestConsultation
      ? latestConsultation.status === "closed"
        ? "Recent consultation completed"
        : "Consultation in progress"
      : "No consultation history yet");

  const recentHistoryDate =
    historyState.history?.consultations?.[0]?.created_at ||
    historyState.history?.prescriptions?.[0]?.created_at ||
    historyState.history?.investigations?.[0]?.created_at ||
    null;

  function handleStartConsultation() {
    navigate("/patient/consultation");
  }

  function handleReturnToChat() {
    if (!activeConsultationState.reference) {
      return;
    }

    navigate(`/consultation?reference=${encodeURIComponent(activeConsultationState.reference)}`);
  }

  function showPreviousTip() {
    setCurrentFeedIndex((current) => (current - 1 + patientTips.length) % patientTips.length);
  }

  function showNextTip() {
    setCurrentFeedIndex((current) => (current + 1) % patientTips.length);
  }

  return (
    <section className="patient-dashboard">
      <div className="patient-dashboard__hero patient-dashboard__hero--plain">
        <div className="patient-dashboard__intro">
          <span className="workspace-pill">Patient Home</span>
          <h1>{profile.name ? `Welcome back, ${profile.name}.` : "Welcome back."}</h1>

          <div className="patient-dashboard__quickmeta">
            <span>
              <strong>Hospital No:</strong> {profile.hospital_number || "Not assigned yet"}
            </span>
            <span>
              <strong>Allergies:</strong> {profile.allergy || "None recorded"}
            </span>
            <span>
              <strong>Conditions:</strong> {profile.medical_conditions || "None recorded"}
            </span>
          </div>
        </div>

        <aside className="patient-dashboard__summary">
          <div className="patient-dashboard__summary-card">
            <h2>{latestDiagnosis}</h2>
            <p>
              {recentHistoryDate
                ? `Most recent activity: ${new Date(recentHistoryDate).toLocaleString()}`
                : "Your consultation history will appear here once care records are created."}
            </p>
          </div>

          <div className="patient-dashboard__summary-links">
            {activeConsultationState.reference ? (
              <button className="button patient-dashboard__summary-link" type="button" onClick={handleReturnToChat}>
                Return to chat
              </button>
            ) : null}
            <button className="button patient-dashboard__summary-link" type="button" onClick={handleStartConsultation}>
              Start Consultation
            </button>
            <Link className="button patient-dashboard__summary-link" to="/patient/documents">
              Open Documents
            </Link>
          </div>
        </aside>
      </div>

      <div className="patient-dashboard__stack">
        <section className="patient-dashboard__section patient-dashboard__section--full patient-dashboard__section--plain">
          <div className="patient-dashboard__section-heading patient-dashboard__section-heading--centered">
            <div>
              <h2>What do you want to do today</h2>
            </div>
          </div>

          <div className="patient-dashboard__actions">
            {actionCards.map((item) => (
              <button
                key={item.key}
                className={
                  item.tone === "primary"
                    ? "patient-dashboard__action-card patient-dashboard__action-card--primary"
                    : "patient-dashboard__action-card"
                }
                type="button"
                onClick={item.key === "consultation" ? handleStartConsultation : () => navigate(item.to)}
              >
                <h3>{item.title}</h3>
              </button>
            ))}
          </div>
        </section>

        <section className="patient-dashboard__section patient-dashboard__section--full patient-dashboard__section--plain patient-dashboard__feed-card">
          <div className="patient-dashboard__section-heading patient-dashboard__section-heading--centered">
            <div>
              <h2>Health Tips</h2>
            </div>
          </div>

          <div className="patient-dashboard__feed-body">
            <button
              aria-label="Previous medical tip"
              className="patient-dashboard__feed-arrow patient-dashboard__feed-arrow--previous"
              type="button"
              onClick={showPreviousTip}
            >
              {"\u2039"}
            </button>
            <h3>{patientTips[currentFeedIndex].title}</h3>
            <p>{patientTips[currentFeedIndex].body}</p>
            <button
              aria-label="Next medical tip"
              className="patient-dashboard__feed-arrow patient-dashboard__feed-arrow--next"
              type="button"
              onClick={showNextTip}
            >
              {"\u203A"}
            </button>
            <div className="patient-dashboard__feed-dots" aria-label="Patient dashboard feed">
              {patientTips.map((item, index) => (
                <button
                  key={item.title}
                  className={
                    index === currentFeedIndex
                      ? "patient-dashboard__feed-dot patient-dashboard__feed-dot--active"
                      : "patient-dashboard__feed-dot"
                  }
                  type="button"
                  onClick={() => setCurrentFeedIndex(index)}
                  aria-label={`Show feed item ${index + 1}`}
                />
              ))}
            </div>
          </div>
        </section>

        <section className="patient-dashboard__section patient-dashboard__section--full patient-dashboard__section--centered patient-dashboard__records-section">
          <div className="patient-dashboard__section-heading patient-dashboard__section-heading--centered">
            <div>
              <h2>Your health records, ready when you need them</h2>
            </div>
          </div>

          <div className="patient-dashboard__tiles patient-dashboard__tiles--centered">
            <article className="patient-dashboard__tile">
              <h3>Follow-Up</h3>
              <Link className="landing-inline-link" to="/patient/followup">
                Open follow-up
              </Link>
            </article>

            <article className="patient-dashboard__tile">
              <h3>Prescriptions &amp; Investigations</h3>
              <Link className="landing-inline-link" to="/patient/documents">
                Open documents
              </Link>
            </article>
          </div>
        </section>
      </div>
    </section>
  );
}
