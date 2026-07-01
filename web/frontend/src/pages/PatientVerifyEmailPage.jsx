import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import "../styles/forms.css";
import "../styles/login.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export default function PatientVerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState({
    kind: "loading",
    title: "Checking your email link",
    message: "Please wait while SynMed confirms this email address.",
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
            title: "This link is incomplete",
            message: "Open the latest verification email from SynMed and try again.",
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
          throw new Error(text || "Unable to verify this email right now.");
        }

        if (!ignore) {
          setStatus({
            kind: "success",
            title: "Your email has been verified",
            message: "You can now sign in and continue your care on SynMed Telehealth.",
          });
        }
      } catch (error) {
        if (!ignore) {
          setStatus({
            kind: "error",
            title: "We could not verify this link",
            message: error.message || "Please use the latest verification email or request a new link.",
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
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <div className={`login-page__verification login-page__verification--${status.kind}`}>
          <p className="login-page__verification-kicker">
            {status.kind === "success" ? "Success" : status.kind === "loading" ? "Verifying" : "Action needed"}
          </p>
          <h1 className="login-page__inline-title">{status.title}</h1>
          <p className="login-page__plain-subtitle">{status.message}</p>
          <Link className="button button--primary login-page__button" to="/signin">
            Continue to sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
