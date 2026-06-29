import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import SectionCard from "../components/SectionCard.jsx";
import { setPendingDoctorSignupIdentifier, submitDoctorApplication } from "../api/auth.js";
import "../styles/forms.css";
import "../styles/login.css";

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export default function DoctorSignupPage() {
  const navigate = useNavigate();
  const [formState, setFormState] = useState({
    name: "",
    email: "",
    phone: "",
    specialty: "",
    experience: "",
    licenseId: "",
    licenseExpiryDate: "",
    licenseFile: null,
    password: "",
  });
  const [status, setStatus] = useState({
    kind: "idle",
    message: "Create a doctor web application. We will verify your email before sending it to admin review.",
    debugCode: "",
  });

  async function handleSubmit(event) {
    event.preventDefault();
    setStatus({
      kind: "loading",
      message: "Sending doctor application OTP by email...",
      debugCode: "",
    });

    try {
      const licenseFileData = formState.licenseFile ? await fileToDataUrl(formState.licenseFile) : "";
      const result = await submitDoctorApplication({
        name: formState.name.trim(),
        email: formState.email.trim(),
        phone: formState.phone.trim(),
        specialty: formState.specialty.trim(),
        experience: formState.experience.trim(),
        license_id: formState.licenseId.trim(),
        license_expiry_date: formState.licenseExpiryDate,
        license_file_name: formState.licenseFile?.name || "",
        license_file_type: formState.licenseFile?.type || "",
        license_file_size: formState.licenseFile?.size || null,
        license_file_data: licenseFileData,
        password: formState.password,
      });
      setPendingDoctorSignupIdentifier(formState.email.trim().toLowerCase());
      setStatus({
        kind: "success",
        message: "Application OTP sent. Redirecting to verification...",
        debugCode: result.debug_code || "",
      });
      navigate("/doctor/signup-verify", { replace: true });
    } catch (error) {
      setStatus({
        kind: "error",
        message: error.message || "Unable to submit doctor application right now.",
        debugCode: "",
      });
    }
  }

  return (
    <div className="login-page">
      <div className="login-page__wrap">
        <div className="login-page__brand">
          <img className="login-page__brand-logo" src="/logo-removebg-preview.png" alt="SynMed Telehealth" />
        </div>

        <SectionCard title="Doctor web signup" subtitle="Submit your details, verify your email, then wait for admin approval.">
          <form className="form-panel" onSubmit={handleSubmit}>
            <label className="form-field">
              <span className="form-field__label">Full Name</span>
              <input
                className="form-field__input"
                type="text"
                value={formState.name}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, name: event.target.value }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Email Address</span>
              <input
                className="form-field__input"
                type="email"
                value={formState.email}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, email: event.target.value }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Phone Number</span>
              <input
                className="form-field__input"
                type="tel"
                value={formState.phone}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, phone: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Specialty</span>
              <input
                className="form-field__input"
                type="text"
                value={formState.specialty}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, specialty: event.target.value }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Years of Experience</span>
              <input
                className="form-field__input"
                type="text"
                value={formState.experience}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, experience: event.target.value }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">License ID</span>
              <input
                className="form-field__input"
                type="text"
                value={formState.licenseId}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, licenseId: event.target.value }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">License Expiry Date</span>
              <input
                className="form-field__input"
                type="date"
                value={formState.licenseExpiryDate}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, licenseExpiryDate: event.target.value }))
                }
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Latest Annual Licence</span>
              <input
                className="form-field__input"
                type="file"
                accept="image/*,application/pdf"
                onChange={(event) =>
                  setFormState((current) => ({
                    ...current,
                    licenseFile: event.target.files?.[0] || null,
                  }))
                }
                required
              />
            </label>
            <label className="form-field">
              <span className="form-field__label">Create Password</span>
              <PasswordInput
                value={formState.password}
                onChange={(event) =>
                  setFormState((current) => ({ ...current, password: event.target.value }))
                }
                minLength={8}
                required
              />
            </label>
            <button className="button button--primary login-page__button" type="submit">
              Submit Application
            </button>
          </form>

          {status.message ? (
            <div className={`lookup-result lookup-result--${status.kind}`}>
              <p className="lookup-result__message">{status.message}</p>
              {status.debugCode ? <p className="lookup-result__message">Dev OTP: {status.debugCode}</p> : null}
            </div>
          ) : null}

          <div className="login-page__links">
            <p>
              Already approved? <Link to="/doctor/signin">Sign in here</Link>
            </p>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
