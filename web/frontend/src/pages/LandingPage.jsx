import { Link } from "react-router-dom";
import "../styles/landing.css";

const carePillars = [
  {
    title: "Rapid patient intake",
    body: "Move from registration to payment, triage, and consultation without sending patients through a crowded chat-only flow.",
  },
  {
    title: "Doctor-ready coordination",
    body: "Keep doctor availability, queue management, prescriptions, investigations, and follow-up actions in one connected workspace.",
  },
  {
    title: "Bot plus web continuity",
    body: "Patients and clinicians can keep using Telegram while the website grows into a polished care experience around the same logic.",
  },
];

const workflowSteps = [
  "Patient enters through the portal, looks up or creates a record, and completes payment or reuses a valid payment code.",
  "A verified consultation request reaches the shared queue, and the next available doctor is assigned cleanly.",
  "Chat, documents, prescriptions, and follow-up actions continue across Telegram and the website without starting from scratch.",
];

const proofPoints = [
  { value: "24 hrs", label: "Payment validity window for same-day returns" },
  { value: "Web + Bot", label: "Shared consultation pathway across both channels" },
  { value: "Live", label: "Doctor replies and clinical documents flow back into the care room" },
];

const faqs = [
  {
    question: "Can SynMed keep using the Telegram bot while the website grows?",
    answer:
      "Yes. The site is designed to sit beside the existing bot so you can keep operations running while the web experience becomes more polished.",
  },
  {
    question: "Can returning patients avoid paying again the same day?",
    answer:
      "Yes. A successful payment generates a reusable code that remains valid for 24 hours for that same patient record.",
  },
  {
    question: "Will doctors have to abandon Telegram immediately?",
    answer:
      "No. Doctors can continue working in Telegram while web dashboards and consultation tools mature alongside it.",
  },
];

export default function LandingPage() {
  return (
    <div className="landing-page">
      <section className="landing-hero">
        <div className="landing-hero__copy">
          <p className="landing-hero__eyebrow">SynMed Telehealth Platform</p>
          <h1 className="landing-hero__title">
            Clinical care coordination that feels like a real healthcare product, not a long chat thread.
          </h1>
          <p className="landing-hero__body">
            SynMed brings patient intake, same-day consultation access, doctor coordination, prescriptions,
            investigations, and follow-up continuity into a calmer digital front door built around your
            existing telehealth workflow.
          </p>
          <div className="landing-hero__actions">
            <Link className="button button--primary" to="/patient">
              Enter Patient Portal
            </Link>
            <Link className="button button--secondary" to="/doctor">
              Open Doctor Workspace
            </Link>
          </div>
          <div className="landing-auth-links">
            <Link to="/patient/signin">Patient Login</Link>
            <Link to="/patient/register">Patient Sign Up</Link>
            <Link to="/patient/history">Past History</Link>
          </div>
          <div className="landing-hero__trust">
            <span>Patient registration and returning access</span>
            <span>Live consultation continuity</span>
            <span>Prescription and investigation delivery</span>
          </div>
        </div>

        <div className="landing-hero__panel">
          <div className="landing-hero__panel-card landing-hero__panel-card--primary">
            <p className="landing-kicker">Care Pathway</p>
            <h2>From triage to follow-up without losing the patient context.</h2>
            <p>
              Built for same-day telehealth care, result review, appointment booking, and handoff between
              website and Telegram.
            </p>
          </div>

          <div className="landing-hero__stack">
            {proofPoints.map((item) => (
              <article key={item.label} className="landing-stat-card">
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-band">
        <p>
          SynMed is designed for fast digital consultations, repeat result reviews, doctor responsiveness,
          and operational continuity across both web and Telegram.
        </p>
      </section>

      <section className="landing-section">
        <div className="landing-section__heading">
          <p className="landing-kicker">Built Around Real Use</p>
          <h2>Three connected experiences, one care system.</h2>
        </div>
        <div className="landing-pillar-grid">
          {carePillars.map((pillar) => (
            <article key={pillar.title} className="landing-pillar-card">
              <h3>{pillar.title}</h3>
              <p>{pillar.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section landing-section--split">
        <div className="landing-section__heading">
          <p className="landing-kicker">How It Works</p>
          <h2>A care flow that is easier to understand at a glance.</h2>
        </div>
        <div className="landing-flow">
          {workflowSteps.map((step, index) => (
            <article key={step} className="landing-flow-card">
              <span className="landing-flow-card__index">0{index + 1}</span>
              <p>{step}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-section__heading">
          <p className="landing-kicker">Choose Your Entry</p>
          <h2>Start from the part of SynMed that matches the person using it.</h2>
        </div>
        <div className="landing-entry-grid">
          <article className="landing-entry-card">
            <h3>Patients</h3>
            <p>
              Register, return with a valid payment code, request consultation, receive doctor messages, and
              view prescriptions or investigations in one place.
            </p>
            <Link className="landing-inline-link" to="/patient">
              Go to patient portal
            </Link>
          </article>
          <article className="landing-entry-card">
            <h3>Doctors</h3>
            <p>
              Stay available, manage active consultations, issue prescriptions, request investigations, and
              continue working alongside Telegram when needed.
            </p>
            <Link className="landing-inline-link" to="/doctor">
              Open doctor workspace
            </Link>
          </article>
          <article className="landing-entry-card">
            <h3>Operations</h3>
            <p>
              Track verified doctors, maintain system oversight, and keep the migration from bot to website
              organized rather than disruptive.
            </p>
            <Link className="landing-inline-link" to="/admin">
              View admin area
            </Link>
          </article>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-section__heading">
          <p className="landing-kicker">Questions</p>
          <h2>Common things patients and operators will want to know.</h2>
        </div>
        <div className="landing-faq-grid">
          {faqs.map((item) => (
            <article key={item.question} className="landing-faq-card">
              <h3>{item.question}</h3>
              <p>{item.answer}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <div>
          <p className="landing-kicker">SynMed Telehealth</p>
          <h2>Move patients into care faster with a cleaner digital front door.</h2>
        </div>
        <div className="landing-cta__actions">
          <Link className="button button--primary" to="/patient">
            Start Patient Flow
          </Link>
          <Link className="button button--secondary" to="/consultation">
            Open Consultation Room
          </Link>
        </div>
      </section>
    </div>
  );
}
