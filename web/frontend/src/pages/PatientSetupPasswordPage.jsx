import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { setupPatientWebPassword } from "../api/auth.js";
import "../styles/forms.css";
import "../styles/login.css";

export default function PatientSetupPasswordPage() {
  const [searchParams] = useSearchParams();
  const hospitalNumber = searchParams.get("hospital_number") || "";
  const token = searchParams.get("token") || "";
  const linkReady = useMemo(() => Boolean(hospitalNumber && token), [hospitalNumber, token]);
  const [form, setForm] = useState({ password: "", confirmPassword: "" });
  const [state, setState] = useState({ status: "idle", message: "" });

  async function handleSubmit(event) {
    event.preventDefault();
    if (!linkReady) {
      setState({ status: "error", message: "This setup link is incomplete. Please open the latest SynMed email." });
      return;
    }
    if (form.password.trim().length < 6) {
      setState({ status: "error", message: "Password must be at least 6 characters long." });
      return;
    }
    if (form.password !== form.confirmPassword) {
      setState({ status: "error", message: "Passwords do not match." });
      return;
    }

    setState({ status: "loading", message: "Setting up your web access..." });
    try {
      const result = await setupPatientWebPassword(hospitalNumber, token, form.password);
      setState({ status: "success", message: result.message || "Web access is ready." });
      setForm({ password: "", confirmPassword: "" });
    } catch (error) {
      setState({ status: "error", message: error.message || "Unable to set up web access right now." });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <form className="login-page__plain-form" onSubmit={handleSubmit}>
          <h1 className="login-page__inline-title">Set up web access</h1>
          <p className="login-page__plain-subtitle">
            Create a password for your SynMed patient dashboard.
          </p>

          {!linkReady ? (
            <div className="form-notice form-notice--error">This setup link is incomplete. Please open the latest SynMed email.</div>
          ) : null}
          {state.message ? <div className={`form-notice form-notice--${state.status}`}>{state.message}</div> : null}

          {state.status === "success" ? (
            <Link className="button button--primary login-page__button" to="/signin">
              Continue to sign in
            </Link>
          ) : (
            <>
              <label className="form-field">
                <span className="form-field__label">New password</span>
                <input
                  className="form-field__input"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                  disabled={!linkReady || state.status === "loading"}
                  required
                />
              </label>
              <label className="form-field">
                <span className="form-field__label">Confirm password</span>
                <input
                  className="form-field__input"
                  type="password"
                  autoComplete="new-password"
                  value={form.confirmPassword}
                  onChange={(event) => setForm((current) => ({ ...current, confirmPassword: event.target.value }))}
                  disabled={!linkReady || state.status === "loading"}
                  required
                />
              </label>
              <button className="button button--primary login-page__button" type="submit" disabled={!linkReady || state.status === "loading"}>
                {state.status === "loading" ? "Setting up..." : "Create password"}
              </button>
            </>
          )}
        </form>
      </div>
    </div>
  );
}
