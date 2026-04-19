import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function PatientVerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState({
    kind: "loading",
    message: "Verifying your email address...",
  });

  useEffect(() => {
    let ignore = false;

    async function verifyEmail() {
      const hospitalNumber = searchParams.get("hospital_number") || "";
      const token = searchParams.get("token") || "";
      if (!hospitalNumber || !token) {
        if (!ignore) {
          setStatus({
            kind: "error",
            message: "Verification link is incomplete. Open the latest email link again.",
          });
        }
        return;
      }

      try {
        const response = await fetch(
          `${API_BASE_URL}/auth/verify-email?hospital_number=${encodeURIComponent(hospitalNumber)}&token=${encodeURIComponent(token)}`,
          {
            headers: {
              Accept: "application/json,text/html",
            },
          },
        );

        const text = await response.text();
        if (!response.ok) {
          throw new Error(text || "Unable to verify email right now.");
        }

        if (!ignore) {
          setStatus({
            kind: "success",
            message: "Email verified successfully. You can now sign in to SynMed Web.",
          });
        }
      } catch (error) {
        if (!ignore) {
          setStatus({
            kind: "error",
            message: error.message || "Unable to verify email right now.",
          });
        }
      }
    }

    verifyEmail();
    return () => {
      ignore = true;
    };
  }, [searchParams]);

  return (
    <SectionCard
      title="Verify Email"
      subtitle="This completes your patient web registration before sign in."
    >
      <div className={`lookup-result lookup-result--${status.kind}`}>
        <p className="lookup-result__message">{status.message}</p>
      </div>

      <p className="patient-auth-link">
        Continue to <Link to="/patient/signin">patient sign in</Link>
      </p>
    </SectionCard>
  );
}
