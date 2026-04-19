import { useEffect, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import { fetchPatientDocuments } from "../api/patients.js";
import "../styles/consultation.css";
import "../styles/patient-portal.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function PatientDocumentsPage() {
  const [documentsState, setDocumentsState] = useState({
    status: "loading",
    message: "Loading active prescriptions and investigations...",
    documents: [],
  });

  useEffect(() => {
    let ignore = false;

    async function loadDocuments() {
      try {
        const result = await fetchPatientDocuments();
        if (!ignore) {
          setDocumentsState({
            status: result.found ? "success" : "empty",
            message: result.message,
            documents: result.documents || [],
          });
        }
      } catch (error) {
        if (!ignore) {
          setDocumentsState({
            status: "error",
            message: error.message || "Unable to load prescription and investigation files.",
            documents: [],
          });
        }
      }
    }

    loadDocuments();
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <SectionCard
      title="Prescriptions And Investigations"
      subtitle="Only currently active consultation documents remain visible here within the 24-hour payment window."
    >
      <div className={`lookup-result lookup-result--${documentsState.status}`}>
        <p className="lookup-result__message">{documentsState.message}</p>
      </div>

      <div className="document-gallery">
        {documentsState.documents.length ? (
          documentsState.documents.map((item) => (
            <article key={`${item.kind}-${item.document_id}`} className="document-card">
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
          ))
        ) : null}
      </div>
    </SectionCard>
  );
}
