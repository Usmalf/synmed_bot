import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { restoreSession } from "../api/auth.js";
import { fetchPatientHistory } from "../api/patients.js";
import "../styles/patient-portal.css";

const entryActions = [
  {
    key: "consultation",
    title: "Start Consultation",
    body: "Continue straight into consultation. SynMed will keep any valid 24-hour payment and only ask for payment when needed.",
  },
  {
    key: "appointment",
    title: "Book Appointment",
    body: "Prepare the patient for scheduled review and appointment-based continuity.",
  },
  {
    key: "followup",
    title: "Follow-Up",
    body: "Check previous diagnoses and return with the right context instead of starting over.",
  },
];

export default function PatientWorkspaceHomePage() {
  const navigate = useNavigate();
  const [activeAction, setActiveAction] = useState("appointment");
  const [historyState, setHistoryState] = useState({
    status: "idle",
    history: null,
  });

  useEffect(() => {
    let ignore = false;

    async function loadWorkspace() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "patient") {
          return;
        }
        const history = await fetchPatientHistory();
        if (!ignore) {
          setHistoryState({
            status: "success",
            history: history.history,
          });
        }
      } catch {
        if (!ignore) {
          setHistoryState({
            status: "idle",
            history: null,
          });
        }
      }
    }

    loadWorkspace();
    return () => {
      ignore = true;
    };
  }, []);

  const latestDiagnosis =
    historyState.history?.prescriptions?.[0]?.diagnosis ||
    historyState.history?.investigations?.[0]?.diagnosis ||
    "No diagnosis history yet";

  return (
    <section className="patient-action-zone">
      <div className="patient-action-zone__heading">
        <span className="workspace-pill">Patient Home</span>
        <h2>Choose what the patient wants to do next.</h2>
        <p>Consultation, appointments, and follow-up stay organized in their own paths instead of being packed into one page.</p>
      </div>

      <div className="entry-action-grid">
        {entryActions.map((item) =>
          item.key === "consultation" ? (
            <button
              key={item.key}
              className="entry-action-card"
              type="button"
              onClick={() => navigate("/patient/consultation")}
            >
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </button>
          ) : (
            <button
              key={item.key}
              className={
                activeAction === item.key
                  ? "entry-action-card entry-action-card--active"
                  : "entry-action-card"
              }
              type="button"
              onClick={() => setActiveAction(item.key)}
            >
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </button>
          ),
        )}
      </div>

      <div className="entry-panel">
        <h3>Latest Diagnosis Snapshot</h3>
        <p>{latestDiagnosis}</p>
        <div className="patient-action-links">
          <Link className="button button--secondary" to="/patient/history">
            View Past History
          </Link>
          <Link className="button button--secondary" to="/patient/account">
            Open Account
          </Link>
        </div>
      </div>

      {activeAction === "appointment" ? (
        <div className="entry-panel">
          <h3>Appointment Flow</h3>
          <p>
            Patients can self-book appointments here, choose pay now or pay later, and apply a valid payment code from a previous payment made within the last 24 hours.
          </p>
          <div className="patient-action-links">
            <Link className="button button--primary" to="/patient/appointments">
              Open Appointment Desk
            </Link>
            <Link className="button button--secondary" to="/patient/history">
              Review History First
            </Link>
          </div>
        </div>
      ) : null}

      {activeAction === "followup" ? (
        <div className="entry-panel">
          <h3>Follow-Up Flow</h3>
          <p>
            Follow-up starts from previous diagnosis and consultation context. Review prior records, then continue with a same-day valid payment code or a new returning-patient flow.
          </p>
          <div className="patient-action-links">
            <Link className="button button--primary" to="/patient/history">
              View Past History
            </Link>
            <Link className="button button--secondary" to="/patient/followup">
              Open Follow-Up
            </Link>
          </div>
        </div>
      ) : null}
    </section>
  );
}
