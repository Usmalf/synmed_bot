import { useEffect, useMemo, useState } from "react";
import BrandedLoader from "../components/BrandedLoader.jsx";
import StatusPill from "../components/StatusPill.jsx";
import { createMedicalReport } from "../api/doctorDocuments.js";
import { fetchDoctorWorkspace } from "../api/doctors.js";
import "../styles/doctor.css";

const PAGE_SIZE = 6;

export default function DoctorMedicalReportRequestsPage() {
  const [page, setPage] = useState(1);
  const [activeRequestId, setActiveRequestId] = useState("");
  const [formState, setFormState] = useState({
    diagnosis: "",
    report_note: "",
    status: "idle",
    message: "",
  });
  const [state, setState] = useState({
    status: "loading",
    message: "Loading medical report requests...",
    requests: [],
  });

  async function loadRequests({ shouldIgnore = () => false } = {}) {
    try {
      const workspace = await fetchDoctorWorkspace();
      if (!shouldIgnore()) {
        setState({
          status: "success",
          message: "",
          requests: workspace.medical_report_requests || [],
        });
      }
    } catch (error) {
      if (!shouldIgnore()) {
        setState({
          status: "error",
          message: error.message || "Unable to load medical report requests.",
          requests: [],
        });
      }
    }
  }

  useEffect(() => {
    let ignore = false;
    loadRequests({ shouldIgnore: () => ignore });
    return () => {
      ignore = true;
    };
  }, []);

  function openReportForm(item) {
    setActiveRequestId(item.request_id);
    setFormState({
      diagnosis: "",
      report_note: item.request_note || "",
      status: "idle",
      message: "",
    });
  }

  async function handleCreateReport(event) {
    event.preventDefault();
    setFormState((current) => ({
      ...current,
      status: "saving",
      message: "Creating medical report...",
    }));
    try {
      const result = await createMedicalReport({
        request_id: activeRequestId,
        diagnosis: formState.diagnosis,
        report_note: formState.report_note,
      });
      setFormState((current) => ({
        ...current,
        status: result.created ? "success" : "error",
        message: result.message,
      }));
      if (result.created) {
        setActiveRequestId("");
        setFormState({
          diagnosis: "",
          report_note: "",
          status: "success",
          message: result.message,
        });
        await loadRequests();
      }
    } catch (error) {
      setFormState((current) => ({
        ...current,
        status: "error",
        message: error.message || "Unable to create medical report right now.",
      }));
    }
  }

  const pageCount = Math.max(1, Math.ceil(state.requests.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const activeRequest = activeRequestId
    ? state.requests.find((item) => item.request_id === activeRequestId) || null
    : null;
  const visibleRequests = useMemo(() => {
    if (activeRequest) {
      return [activeRequest];
    }
    return state.requests.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  }, [activeRequest, safePage, state.requests]);

  return (
    <div className="doctor-report-page">
      <header className="doctor-page-header">
        <div>
          <p>Doctor Workspace</p>
          <h1>Medical Report Requests</h1>
          <span>Review report requests assigned to you by SynMed administration.</span>
        </div>
        <span className="doctor-unread-count">
          {state.requests.length} request{state.requests.length === 1 ? "" : "s"}
        </span>
      </header>

      <section className="doctor-portal-panel doctor-report-panel">
        <div className="doctor-portal-panel__header">
          <h2>Assigned requests</h2>
          <p>Payment and processing status are shown for each request.</p>
        </div>
        {state.status === "loading" ? (
          <div className="doctor-report-page__state">
            <BrandedLoader compact label={state.message} />
          </div>
        ) : state.status === "error" ? (
          <p className="doctor-message-page__status doctor-message-page__status--error">
            {state.message}
          </p>
        ) : visibleRequests.length ? (
          <div className="doctor-report-list">
            {visibleRequests.map((item) => (
              <article className="doctor-report-row" key={item.request_id}>
                <div className="doctor-report-row__main">
                  <div>
                    <strong>{item.request_id}</strong>
                    <span>Patient: {item.patient_id || "Not recorded"}</span>
                    <p>{item.request_note || "Medical report requested without an additional note."}</p>
                  </div>
                  {activeRequestId === item.request_id ? (
                    <form className="doctor-report-form" onSubmit={handleCreateReport}>
                      <label className="form-field">
                        <span className="form-field__label">Diagnosis</span>
                        <input
                          className="form-field__input"
                          value={formState.diagnosis}
                          onChange={(event) =>
                            setFormState((current) => ({ ...current, diagnosis: event.target.value }))
                          }
                          placeholder="Enter diagnosis"
                        />
                      </label>
                      <label className="form-field">
                        <span className="form-field__label">Referral Note</span>
                        <textarea
                          className="form-field__input"
                          value={formState.report_note}
                          onChange={(event) =>
                            setFormState((current) => ({ ...current, report_note: event.target.value }))
                          }
                          placeholder="Write the referral note or medical report details..."
                          rows={5}
                          required
                        />
                      </label>
                      <div className="doctor-report-form__actions">
                        <button
                          className="button button--secondary"
                          type="button"
                          onClick={() => setActiveRequestId("")}
                        >
                          Cancel
                        </button>
                        <button className="button" disabled={formState.status === "saving"} type="submit">
                          {formState.status === "saving" ? "Creating..." : "Send Report"}
                        </button>
                      </div>
                      {formState.message ? (
                        <p className={`doctor-report-form__message doctor-report-form__message--${formState.status}`}>
                          {formState.message}
                        </p>
                      ) : null}
                    </form>
                  ) : null}
                </div>
                {activeRequestId === item.request_id ? null : (
                  <div className="doctor-report-row__status">
                    <StatusPill
                      label={item.payment_status}
                      tone={item.payment_status === "paid" ? "success" : "warning"}
                    />
                    <StatusPill label={item.status} tone="neutral" />
                    {item.payment_status === "paid" && item.status !== "fulfilled" && !item.fulfilled_letter_id ? (
                      <button className="button button--secondary doctor-report-row__action" type="button" onClick={() => openReportForm(item)}>
                        Create Report
                      </button>
                    ) : null}
                  </div>
                )}
              </article>
            ))}
          </div>
        ) : (
          <p className="doctor-message-page__empty">No assigned medical report requests right now.</p>
        )}

        {!activeRequestId && pageCount > 1 ? (
          <div className="doctor-pager">
            <span>Page {safePage} of {pageCount}</span>
            <div>
              <button type="button" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>
                Previous
              </button>
              <button type="button" disabled={safePage >= pageCount} onClick={() => setPage(safePage + 1)}>
                Next
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
