import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import BrandedLoader from "../components/BrandedLoader.jsx";
import PasswordInput from "../components/PasswordInput.jsx";
import SectionCard from "../components/SectionCard.jsx";
import { loginPatientWithGoogle, loginWebUser, restoreSession, setPendingLogin } from "../api/auth.js";
import "../styles/forms.css";
import "../styles/login.css";

function getRedirectPathForRole(role) {
  if (role === "doctor") {
    return "/doctor";
  }
  if (role === "admin") {
    return "/admin";
  }
  if (role === "customer_care") {
    return "/customer-care";
  }
  return "/patient";
}

export default function WebSignInPage() {
  const navigate = useNavigate();
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
  const [credentials, setCredentials] = useState({
    identifier: "",
    password: "",
    rememberMe: true,
  });
  const [googleReady, setGoogleReady] = useState(false);
  const [signInState, setSignInState] = useState({
    status: "idle",
    message: "",
  });

  useEffect(() => {
    let ignore = false;

    async function bootstrapSession() {
      try {
        const session = await restoreSession();
        if (!ignore && session.user?.role) {
          navigate(getRedirectPathForRole(session.user.role), { replace: true });
        }
      } catch {}
    }

    bootstrapSession();
    return () => {
      ignore = true;
    };
  }, [navigate]);

  useEffect(() => {
    if (!googleClientId) {
      return undefined;
    }

    let cancelled = false;
    let script = document.querySelector('script[data-google-identity="true"]');

    function renderGoogleButton() {
      if (cancelled || !window.google?.accounts?.id) {
        return;
      }

      const buttonHost = document.getElementById("synmed-google-signin");
      if (!buttonHost) {
        return;
      }

      buttonHost.innerHTML = "";
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: async (response) => {
          try {
            setSignInState({
              status: "loading",
              message: "Signing you in with Google...",
            });
            const session = await loginPatientWithGoogle(response.credential, {
              rememberMe: credentials.rememberMe,
            });
            navigate(session.next_path || "/patient", { replace: true });
          } catch (error) {
            setSignInState({
              status: "error",
              message: error.message || "Unable to continue with Google right now.",
            });
          }
        },
      });
      window.google.accounts.id.renderButton(buttonHost, {
        theme: document.body.dataset.backgroundTheme === "light" ? "outline" : "filled_black",
        size: "large",
        width: 320,
        text: "continue_with",
        shape: "pill",
      });
      setGoogleReady(true);
    }

    if (window.google?.accounts?.id) {
      renderGoogleButton();
      return undefined;
    }

    if (!script) {
      script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.dataset.googleIdentity = "true";
      script.onload = renderGoogleButton;
      document.head.appendChild(script);
    } else {
      script.addEventListener("load", renderGoogleButton);
    }

    return () => {
      cancelled = true;
      if (script) {
        script.removeEventListener("load", renderGoogleButton);
      }
    };
  }, [credentials.rememberMe, googleClientId, navigate]);

  async function handleSignIn(event) {
    event.preventDefault();
    setSignInState({
      status: "loading",
      message: "Sending your sign-in code...",
    });

    try {
      const identifier = credentials.identifier.trim();
      const result = await loginWebUser(identifier, credentials.password);
      setPendingLogin({
        identifier,
        password: credentials.password,
        role: result.role,
        deliveryTarget: result.delivery_target,
        otpChannel: result.otp_channel,
        debugCode: result.debug_code || "",
        rememberMe: credentials.rememberMe,
      });
      setSignInState({
        status: "success",
        message: `Code sent to ${result.delivery_target}. Redirecting to verification...`,
      });
      navigate("/login-otp", { replace: true });
    } catch (error) {
      setSignInState({
        status: "error",
        message: error.message || "Unable to sign in right now.",
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <SectionCard title="Welcome back" subtitle="Sign in to continue">
          <form className="form-panel" onSubmit={handleSignIn}>
            <label className="form-field">
              <span className="form-field__label">Email, Hospital Number, or Phone</span>
              <input
                className="form-field__input"
                type="text"
                value={credentials.identifier}
                onChange={(event) =>
                  setCredentials((current) => ({ ...current, identifier: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Password</span>
              <PasswordInput
                value={credentials.password}
                onChange={(event) =>
                  setCredentials((current) => ({ ...current, password: event.target.value }))
                }
              />
            </label>
            <label className="login-page__checkbox">
              <input
                className="login-page__checkbox-input"
                type="checkbox"
                checked={credentials.rememberMe}
                onChange={(event) =>
                  setCredentials((current) => ({ ...current, rememberMe: event.target.checked }))
                }
              />
              <span>Remember me</span>
            </label>
            <button className="button button--primary login-page__button" type="submit">
              Sign In
            </button>
            <Link className="button login-page__button login-page__button--recovery" to="/patient/recover">
              Forgot password?
            </Link>
          </form>

          {googleClientId ? (
            <div className="login-page__oauth">
              <span className="login-page__oauth-divider">or</span>
              <div id="synmed-google-signin" className="login-page__google-button" />
              {!googleReady ? (
                <p className="login-page__oauth-note">Preparing Google sign-in...</p>
              ) : null}
            </div>
          ) : null}

          {signInState.message && signInState.status !== "loading" ? (
            <div className={`lookup-result lookup-result--${signInState.status}`}>
              <p className="lookup-result__message">{signInState.message}</p>
            </div>
          ) : null}

          <div className="login-page__links">
            <p>
              New here? <Link to="/patient/register">Register/Signup</Link>
            </p>
            <p>
              Doctor access? <Link to="/doctor/signup">Apply as a doctor</Link>
            </p>
          </div>
        </SectionCard>
      </div>
      {signInState.status === "loading"
        ? createPortal(
            <div className="login-page__overlay">
              <div className="login-page__overlay-card">
                <BrandedLoader label={signInState.message} />
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
