import { Link } from "react-router-dom";
import "../styles/legal.css";

const termsSections = [
  {
    title: "Using SynMed",
    body: "SynMed Telehealth provides online access to healthcare support, doctor consultations, prescriptions, investigations, medical reports, follow-up booking, and customer support. You agree to provide accurate information and to use the service responsibly.",
  },
  {
    title: "Medical Advice",
    body: "Online consultations do not replace emergency care. If you have severe symptoms, difficulty breathing, chest pain, loss of consciousness, heavy bleeding, or any urgent condition, seek immediate emergency medical help.",
  },
  {
    title: "Accounts And Payments",
    body: "Patients, doctors, customer care agents, and administrators are responsible for keeping login details secure. Fees, payment verification, consultation access, appointments, and medical report requests are handled through SynMed's approved payment and access workflows.",
  },
  {
    title: "Documents And Communication",
    body: "Clinical documents issued through SynMed are based on the consultation information available to the doctor at the time. Messages, uploads, voice notes, and documents should only contain information relevant to care or support.",
  },
  {
    title: "Service Availability",
    body: "We work to keep SynMed available, but service may be interrupted by maintenance, network issues, payment gateway downtime, or third-party service limitations.",
  },
];

const privacySections = [
  {
    title: "Information We Collect",
    body: "We collect account details, contact information, health information you provide, consultation messages, documents, payment references, support tickets, ratings, and technical information needed to run the service.",
  },
  {
    title: "How We Use Information",
    body: "We use your information to provide consultations, verify payments, create medical documents, support your account, improve service quality, notify you about important activity, and maintain safety and audit records.",
  },
  {
    title: "Sharing And Access",
    body: "Relevant information may be visible to doctors, administrators, and customer care agents only when needed for care delivery, support, payment tracing, compliance, or service management.",
  },
  {
    title: "Data Security",
    body: "SynMed uses access controls and service safeguards to reduce unauthorized access. No online system is completely risk-free, so users should keep account details private and report suspicious activity quickly.",
  },
  {
    title: "Your Choices",
    body: "You may update your account details, request support, review available clinical documents, and contact SynMed about privacy questions through the support channels on the website.",
  },
];

function LegalPage({ eyebrow, title, intro, sections }) {
  return (
    <main className="legal-page">
      <section className="legal-hero">
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        <p>{intro}</p>
        <Link className="button button--secondary" to="/">
          Back to home
        </Link>
      </section>

      <section className="legal-content">
        {sections.map((section) => (
          <article key={section.title} className="legal-card">
            <h2>{section.title}</h2>
            <p>{section.body}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

export function TermsPage() {
  return (
    <LegalPage
      eyebrow="SynMed Telehealth"
      title="Terms and Conditions of Use"
      intro="These terms explain the basic conditions for using SynMed Telehealth. They are written to help patients and visitors understand how the service should be used."
      sections={termsSections}
    />
  );
}

export function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="SynMed Telehealth"
      title="Privacy Policy"
      intro="This policy explains the types of information SynMed may collect and how that information supports care, payments, documents, communication, and service safety."
      sections={privacySections}
    />
  );
}
