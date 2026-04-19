import { Link } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import "../styles/patient-portal.css";

export default function PatientFollowUpPage() {
  return (
    <SectionCard
      title="Follow-Up"
      subtitle="Use previous diagnosis and consultation context to continue care without starting from the beginning."
    >
      <div className="entry-panel">
        <h3>Review, then continue</h3>
        <p>
          Start follow-up from your past consultation trail, diagnosis history, and previous
          documents. After reviewing, continue with the returning-patient consultation path or book
          a review appointment.
        </p>
        <div className="patient-action-links">
          <Link className="button button--primary" to="/patient/history">
            View Past History
          </Link>
          <Link className="button button--secondary" to="/patient/returning">
            Continue as Returning Patient
          </Link>
          <Link className="button button--secondary" to="/patient/appointments">
            Book Follow-Up Appointment
          </Link>
        </div>
      </div>
    </SectionCard>
  );
}
