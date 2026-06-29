import { useEffect, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import { fetchPatientDocuments } from "../api/patients.js";
import "../styles/consultation.css";
import "../styles/patient-portal.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function PatientDocumentsPage() {
  const [documentsState, setDocumentsState] = useState({
    status: "loading",
    message: "Loading active clinical documents...",
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
            message: error.message || "Unable to load clinical document files.",
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

  const prescriptions = documentsState.documents.filter((item) => item.kind === "prescription");
  const investigations = documentsState.documents.filter((item) => item.kind === "investigation");
  const medicalReports = documentsState.documents.filter((item) => item.kind === "medical_report");
  const shouldShowStatusMessage = ["loading", "error"].includes(documentsState.status);

  function getDownloadName(item) {
    const extension = item.asset_type === "application/pdf" ? "pdf" : "png";
    return `${item.kind}-${item.document_id}.${extension}`;
  }

  function renderDocumentGroup(items, emptyMessage) {
    if (!items.length) {
      return <p className="doctor-state__message">{emptyMessage}</p>;
    }

    return (
      <div className="document-gallery">
        {items.map((item) => (
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
                download={getDownloadName(item)}
              >
                Download
              </a>
            </div>
          </article>
        ))}
      </div>
    );
  }

  return (
    <div className="patient-documents-page">
      <SectionCard
        title="Clinical Documents"
        subtitle="Only currently active consultation documents remain visible here within the 24-hour payment window."
      >
        {shouldShowStatusMessage ? (
          <div className={`lookup-result lookup-result--${documentsState.status}`}>
            <p className="lookup-result__message">{documentsState.message}</p>
          </div>
        ) : null}

        <div className="patient-documents__groups">
          <section className="patient-documents__group">
            <div className="patient-documents__heading">
              <span className="landing-kicker">Prescription Files</span>
              <h3>Prescriptions</h3>
            </div>
            {renderDocumentGroup(prescriptions, "No active prescription files are available right now.")}
          </section>

          <section className="patient-documents__group">
            <div className="patient-documents__heading">
              <span className="landing-kicker">Investigation Files</span>
              <h3>Investigations</h3>
            </div>
            {renderDocumentGroup(
              investigations,
              "No active investigation files are available right now.",
            )}
          </section>

          <section className="patient-documents__group">
            <div className="patient-documents__heading">
              <span className="landing-kicker">Medical Report Files</span>
              <h3>Medical Reports</h3>
            </div>
            {renderDocumentGroup(
              medicalReports,
              "No active medical report files are available right now.",
            )}
          </section>
        </div>
      </SectionCard>
    </div>
  );
}
