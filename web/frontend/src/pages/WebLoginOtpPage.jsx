import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { clearPendingLogin, getPendingLogin, loginWebUser, setPendingLogin, verifyWebUserLogin } from "../api/auth.js";
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

export default function WebLoginOtpPage() {
  const navigate = useNavigate();
  const [pendingLogin, setPendingLoginState] = useState(null);
  const [otpCode, setOtpCode] = useState("");
  const [otpState, setOtpState] = useState({
    status: "idle",
    message: "Enter the sign-in code we just sent to continue.",
  });
  const [resendState, setResendState] = useState({
    status: "idle",
    message: "",
  });
  const [resendCountdown, setResendCountdown] = useState(10);

  useEffect(() => {
    const pending = getPendingLogin();
    if (!pending?.identifier) {
      navigate("/signin", { replace: true });
      return;
    }
    setPendingLoginState(pending);
  }, [navigate]);

  useEffect(() => {
    setResendCountdown(10);
  }, [pendingLogin?.identifier]);

  useEffect(() => {
    if (!pendingLogin?.identifier || resendCountdown <= 0) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setResendCountdown((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearTimeout(timeoutId);
  }, [pendingLogin?.identifier, resendCountdown]);

  async function handleVerify(event) {
    event.preventDefault();
    if (!pendingLogin?.identifier) {
      navigate("/signin", { replace: true });
      return;
    }

    if (!otpCode.trim()) {
      setOtpState({
        status: "error",
        message: "Enter the OTP code before continuing.",
      });
      return;
    }

    setOtpState({
      status: "loading",
      message: "Verifying sign-in code...",
    });

    try {
      const session = await verifyWebUserLogin(pendingLogin.identifier, otpCode.trim(), {
        rememberMe: pendingLogin.rememberMe,
      });
      clearPendingLogin();
      setOtpState({
        status: "success",
        message: "Verification successful. Redirecting now...",
      });
      navigate(getRedirectPathForRole(session.user?.role), { replace: true });
    } catch (error) {
      setOtpState({
        status: "error",
        message: error.message || "Unable to verify the sign-in code right now.",
      });
    }
  }

  async function handleResendOtp() {
    if (!pendingLogin?.identifier || !pendingLogin?.password || resendCountdown > 0) {
      return;
    }

    setResendState({
      status: "loading",
      message: "Sending a new code...",
    });

    try {
      const result = await loginWebUser(pendingLogin.identifier, pendingLogin.password);
      setPendingLogin({
        ...pendingLogin,
        role: result.role,
        deliveryTarget: result.delivery_target,
        otpChannel: result.otp_channel,
        debugCode: result.debug_code || "",
      });
      setPendingLoginState((current) =>
        current
          ? {
              ...current,
              role: result.role,
              deliveryTarget: result.delivery_target,
              otpChannel: result.otp_channel,
              debugCode: result.debug_code || "",
            }
          : current,
      );
      setResendCountdown(10);
      setResendState({
        status: "success",
        message: `A new code was sent to ${result.delivery_target}.`,
      });
    } catch (error) {
      setResendState({
        status: "error",
        message: error.message || "Unable to resend the code right now.",
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <SectionCard
          title="Verify your sign-in"
          subtitle={
            pendingLogin?.deliveryTarget
              ? `We sent a one-time code through ${pendingLogin.otpChannel || "your delivery channel"} to ${pendingLogin.deliveryTarget}.`
              : "Enter the one-time code we sent to your registered delivery channel."
          }
        >
          <form className="form-panel" onSubmit={handleVerify}>
            <label className="form-field">
              <span className="form-field__label">One-Time Code</span>
              <input
                className="form-field__input"
                type="text"
                value={otpCode}
                onChange={(event) => setOtpCode(event.target.value)}
                autoComplete="one-time-code"
              />
            </label>
            <button className="button button--primary login-page__button" type="submit">
              Verify And Continue
            </button>
          </form>

          <div className="login-page__otp-tools">
            <button
              className="button login-page__button login-page__button--secondary"
              type="button"
              onClick={handleResendOtp}
              disabled={resendCountdown > 0 || resendState.status === "loading"}
            >
              {resendCountdown > 0 ? `Resend OTP in ${resendCountdown}s` : "Resend OTP"}
            </button>
          </div>

          <div className={`lookup-result lookup-result--${otpState.status}`}>
            <p className="lookup-result__message">{otpState.message}</p>
            {pendingLogin?.debugCode ? (
              <p className="lookup-result__message">Dev OTP: {pendingLogin.debugCode}</p>
            ) : null}
          </div>

          {resendState.message ? (
            <div className={`lookup-result lookup-result--${resendState.status}`}>
              <p className="lookup-result__message">{resendState.message}</p>
            </div>
          ) : null}

          <div className="login-page__links">
            <p>
              Need to change your details? <Link to="/signin">Back to sign in</Link>
            </p>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
