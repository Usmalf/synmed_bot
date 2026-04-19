import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { fetchPatientHistory } from "../api/patients.js";
import "../styles/patient-portal.css";

export default function PatientHistoryPage() {
  const [historyState, setHistoryState] = useState({
    status: "loading",
    message: "Loading patient history...",
    history: null,
  });
  const [selectedConsultationId, setSelectedConsultationId] = useState("");

  useEffect(() => {
    let ignore = false;

    async function loadHistory() {
      try {
        const result = await fetchPatientHistory();
        if (!ignore) {
          const firstConsultationId = result.history?.consultations?.[0]?.consultation_id || "";
          setHistoryState({
            status: result.found ? "success" : "empty",
            message: result.message,
            history: result.history,
          });
          setSelectedConsultationId(firstConsultationId);
        }
      } catch {
        if (!ignore) {
          setHistoryState({
            status: "error",
            message: "Sign in to view patient history and previous consultations.",
            history: null,
          });
        }
      }
    }

    loadHistory();
    return () => {
      ignore = true;
    };
  }, []);

  const history = historyState.history;

  const diagnosisByConsultation = useMemo(() => {
    const map = new Map();
    (history?.prescriptions || []).forEach((item) => {
      if (!map.has(item.consultation_id)) {
        map.set(item.consultation_id, item.diagnosis);
      }
    });
    (history?.investigations || []).forEach((item) => {
      if (!map.has(item.consultation_id)) {
        map.set(item.consultation_id, item.diagnosis);
      }
    });
    return map;
  }, [history]);

  const selectedConsultation = history?.consultations?.find(
    (item) => item.consultation_id === selectedConsultationId,
  );
  const selectedDiagnosis = diagnosisByConsultation.get(selectedConsultationId) || "No diagnosis recorded";
  const selectedPrescription = (history?.prescriptions || []).find(
    (item) => item.consultation_id === selectedConsultationId,
  );
  const selectedInvestigation = (history?.investigations || []).find(
    (item) => item.consultation_id === selectedConsultationId,
  );

  return (
    <div className="patient-account-grid">
      <SectionCard
        title="Past History"
        subtitle="Each previous consultation is listed with date and diagnosis, with a preview option for more detail."
      >
        <div className={`lookup-result lookup-result--${historyState.status}`}>
          <p className="lookup-result__message">{historyState.message}</p>
        </div>

        {history?.consultations?.length ? (
          <div className="history-table">
            {history.consultations.map((item) => (
              <article key={item.consultation_id} className="history-table__row">
                <div>
                  <span className="history-table__label">Date</span>
                  <strong>{item.created_at}</strong>
                </div>
                <div>
                  <span className="history-table__label">Diagnosis</span>
                  <strong>{diagnosisByConsultation.get(item.consultation_id) || "No diagnosis recorded"}</strong>
                </div>
                <div>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => setSelectedConsultationId(item.consultation_id)}
                  >
                    View
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </SectionCard>

      <SectionCard
        title="History Preview"
        subtitle="Preview the selected consultation summary, diagnosis, prescription note, and investigation request."
      >
        {selectedConsultation ? (
          <div className="history-preview">
            <div className="history-preview__grid">
              <div>
                <span className="history-table__label">Date</span>
                <strong>{selectedConsultation.created_at}</strong>
              </div>
              <div>
                <span className="history-table__label">Status</span>
                <strong>{selectedConsultation.status}</strong>
              </div>
              <div>
                <span className="history-table__label">Diagnosis</span>
                <strong>{selectedDiagnosis}</strong>
              </div>
            </div>

            <div className="history-preview__section">
              <span className="history-table__label">Consultation Summary</span>
              <p>{selectedConsultation.summary}</p>
            </div>

            <div className="history-preview__section">
              <span className="history-table__label">Prescription Note</span>
              <p>{selectedPrescription?.notes || "No prescription note recorded."}</p>
            </div>

            <div className="history-preview__section">
              <span className="history-table__label">Investigation Request</span>
              <p>{selectedInvestigation?.tests_text || "No investigation request recorded."}</p>
            </div>
          </div>
        ) : (
          <p className="workspace-copy">Select a consultation row to preview its history.</p>
        )}

        <div className="patient-action-links">
          <Link className="button button--secondary" to="/patient/followup">
            Open Follow-Up
          </Link>
          <Link className="button button--primary" to="/patient/consultation">
            Start Consultation
          </Link>
        </div>
      </SectionCard>
    </div>
  );
}
