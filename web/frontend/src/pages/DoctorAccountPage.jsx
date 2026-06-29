import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import PasswordInput from "../components/PasswordInput.jsx";
import SectionCard from "../components/SectionCard.jsx";
import { restoreSession } from "../api/auth.js";
import {
  buildDoctorAccountPayload,
  changeDoctorPassword,
  fetchCurrentDoctor,
  updateCurrentDoctor,
} from "../api/doctors.js";
import "../styles/forms.css";
import "../styles/account.css";
import "../styles/doctor.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

function createEmptyProfile() {
  return {
    doctor_id: "",
    name: "",
    specialty: "",
    experience: "",
    email: "",
    license_id: "",
    license_expiry_date: "",
    license_file: null,
    license_file_url: "",
    license_file_name: "",
    license_file_size: "",
    rating_summary: "",
  };
}

function formatFileSize(bytes) {
  const size = Number(bytes || 0);
  if (!size) {
    return "";
  }
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DoctorAccountPage() {
  const navigate = useNavigate();
  const licenceInputRef = useRef(null);
  const [profileForm, setProfileForm] = useState(createEmptyProfile);
  const [profileState, setProfileState] = useState({
    status: "loading",
    message: "Loading doctor account...",
  });
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
  });
  const [passwordState, setPasswordState] = useState({
    status: "idle",
    message: "Update the password you use for doctor web sign in whenever you need to rotate access.",
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [showPasswordOverlay, setShowPasswordOverlay] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadProfile() {
      try {
        const session = await restoreSession();
        if (session.user?.role !== "doctor") {
          navigate("/doctor/signin", { replace: true });
          return;
        }
        const result = await fetchCurrentDoctor();
        if (!ignore) {
          setProfileForm({
            doctor_id: String(result.doctor?.doctor_id || ""),
            name: result.doctor?.name || "",
            specialty: result.doctor?.specialty || "",
            experience: result.doctor?.experience || "",
            email: result.doctor?.email || "",
            license_id: result.doctor?.license_id || "",
            license_expiry_date: result.doctor?.license_expiry_date || "",
            license_file: null,
            license_file_url: result.doctor?.license_file_url || "",
            license_file_name: result.doctor?.license_file_name || "",
            license_file_size: result.doctor?.license_file_size || "",
            rating_summary: result.doctor?.rating_summary || "",
          });
          setProfileState({
            status: "success",
            message: "Doctor account loaded.",
          });
        }
      } catch (error) {
        if (!ignore) {
          setProfileState({
            status: "error",
            message: error.message || "Unable to load doctor account.",
          });
        }
      }
    }

    loadProfile();
    return () => {
      ignore = true;
    };
  }, [navigate]);

  async function handleProfileSubmit(event) {
    event.preventDefault();
    setProfileState({
      status: "loading",
      message: "Saving doctor account...",
    });

    try {
      const result = await updateCurrentDoctor(await buildDoctorAccountPayload(profileForm));
      setProfileForm({
        doctor_id: String(result.doctor?.doctor_id || ""),
        name: result.doctor?.name || "",
        specialty: result.doctor?.specialty || "",
        experience: result.doctor?.experience || "",
        email: result.doctor?.email || "",
        license_id: result.doctor?.license_id || "",
        license_expiry_date: result.doctor?.license_expiry_date || "",
        license_file: null,
        license_file_url: result.doctor?.license_file_url || "",
        license_file_name: result.doctor?.license_file_name || "",
        license_file_size: result.doctor?.license_file_size || "",
        rating_summary: result.doctor?.rating_summary || "",
      });
      setProfileState({
        status: "success",
        message: result.message,
      });
      setIsEditingProfile(false);
    } catch (error) {
      setProfileState({
        status: "error",
        message: error.message || "Unable to save doctor account.",
      });
    }
  }

  async function handlePasswordSubmit(event) {
    event.preventDefault();
    setPasswordState({
      status: "loading",
      message: "Changing password...",
    });

    try {
      const result = await changeDoctorPassword(passwordForm.currentPassword, passwordForm.newPassword);
      setPasswordForm({
        currentPassword: "",
        newPassword: "",
      });
      setPasswordState({
        status: "success",
        message: result.message,
      });
      setShowPasswordOverlay(false);
    } catch (error) {
      setPasswordState({
        status: "error",
        message: error.message || "Unable to change doctor password.",
      });
    }
  }

  function handleLicenceSelection(event) {
    const file = event.target.files?.[0] || null;
    if (!file) return;
    const allowedTypes = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
    if (!allowedTypes.includes(file.type)) {
      event.target.value = "";
      setProfileState({
        status: "error",
        message: "Choose a PDF, JPG, PNG, or WEBP licence file.",
      });
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      event.target.value = "";
      setProfileState({
        status: "error",
        message: "The licence file must be 10 MB or smaller.",
      });
      return;
    }
    setProfileForm((current) => ({ ...current, license_file: file }));
    setProfileState({
      status: "success",
      message: `${file.name} is ready to upload when you save the profile.`,
    });
  }

  const passwordOverlay = showPasswordOverlay
    ? createPortal(
        <div className="account-modal-overlay">
          <div className="account-modal-card">
            <div className="account-modal-card__header">
              <span className="consultation-call-stage__mode">Change Password</span>
              <button
                className="consultation-call-overlay__toggle"
                type="button"
                onClick={() => setShowPasswordOverlay(false)}
              >
                Close
              </button>
            </div>

            <div className="account-modal-card__body">
              <p className="account-modal-card__copy">
                Rotate account access while keeping the professional record and licence details intact.
              </p>

              <form className="form-panel" onSubmit={handlePasswordSubmit}>
                <label className="form-field">
                  <span className="form-field__label">Current Password</span>
                  <PasswordInput
                    value={passwordForm.currentPassword}
                    onChange={(event) =>
                      setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))
                    }
                  />
                </label>
                <label className="form-field">
                  <span className="form-field__label">New Password</span>
                  <PasswordInput
                    value={passwordForm.newPassword}
                    onChange={(event) =>
                      setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))
                    }
                  />
                </label>
                <button className="button button--primary" type="submit">
                  Change Password
                </button>
              </form>

              <div className={`lookup-result lookup-result--${passwordState.status} account-status`}>
                <p className="lookup-result__message">{passwordState.message}</p>
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <div className="account-layout">
        <div className="account-grid">
          <div className="account-column">
            <SectionCard
              title="Profile Preview"
              subtitle="Review the professional profile first, then open edit only when details need updating."
            >
              {isEditingProfile ? (
                <div className="account-preview account-preview--editing">
                  <form className="form-panel" onSubmit={handleProfileSubmit}>
                    <label className="form-field">
                      <span className="form-field__label">Full Name</span>
                      <input className="form-field__input" type="text" value={profileForm.name} onChange={(event) => setProfileForm((current) => ({ ...current, name: event.target.value }))} />
                    </label>
                    <label className="form-field">
                      <span className="form-field__label">Specialty</span>
                      <input className="form-field__input" type="text" value={profileForm.specialty} onChange={(event) => setProfileForm((current) => ({ ...current, specialty: event.target.value }))} />
                    </label>
                    <label className="form-field">
                      <span className="form-field__label">Years of Experience</span>
                      <input className="form-field__input" type="text" value={profileForm.experience} onChange={(event) => setProfileForm((current) => ({ ...current, experience: event.target.value }))} />
                    </label>
                    <label className="form-field">
                      <span className="form-field__label">Email</span>
                      <input className="form-field__input" type="email" value={profileForm.email} onChange={(event) => setProfileForm((current) => ({ ...current, email: event.target.value }))} />
                    </label>
                    <label className="form-field">
                      <span className="form-field__label">Licence Number</span>
                      <input className="form-field__input" type="text" value={profileForm.license_id} onChange={(event) => setProfileForm((current) => ({ ...current, license_id: event.target.value }))} />
                    </label>
                    <label className="form-field">
                      <span className="form-field__label">Licence Expiry Date</span>
                      <input className="form-field__input" type="date" value={profileForm.license_expiry_date} onChange={(event) => setProfileForm((current) => ({ ...current, license_expiry_date: event.target.value }))} />
                    </label>
                    <div className="form-field">
                      <span className="form-field__label">Renewed Annual Licence</span>
                      <input
                        className="account-file-input"
                        type="file"
                        ref={licenceInputRef}
                        accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
                        onChange={handleLicenceSelection}
                      />
                      <div className="account-file-picker">
                        <button className="button button--secondary" type="button" onClick={() => licenceInputRef.current?.click()}>
                          Choose licence file
                        </button>
                        <div>
                          <strong>{profileForm.license_file?.name || profileForm.license_file_name || "No file selected"}</strong>
                          <span>
                            {profileForm.license_file
                              ? formatFileSize(profileForm.license_file.size)
                              : profileForm.license_file_size
                              ? formatFileSize(profileForm.license_file_size)
                              : "PDF or image, up to 10 MB"}
                          </span>
                        </div>
                        {profileForm.license_file ? (
                          <button
                            className="account-file-picker__clear"
                            type="button"
                            onClick={() => {
                              if (licenceInputRef.current) licenceInputRef.current.value = "";
                              setProfileForm((current) => ({ ...current, license_file: null }));
                            }}
                          >
                            Clear
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <div className="account-edit-actions">
                      <button className="button button--primary" disabled={profileState.status === "loading"} type="submit">
                        Save Profile
                      </button>
                      <button
                        className="button button--secondary"
                        type="button"
                        onClick={() => setIsEditingProfile(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                </div>
              ) : (
                <div className="account-preview">
                  <div className="account-preview__top">
                    <div>
                      <span className="workspace-pill">Doctor Record</span>
                      <p className="account-preview__name">{profileForm.name || "Doctor profile"}</p>
                    </div>
                    <button
                      className="patient-shell__history-link patient-shell__history-link--button"
                      type="button"
                      onClick={() => setIsEditingProfile(true)}
                    >
                      Edit profile
                    </button>
                  </div>

                  <dl className="account-stat-grid">
                    <div className="account-detail-card">
                      <dt>Doctor ID</dt>
                      <dd>{profileForm.doctor_id || "N/A"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Specialty</dt>
                      <dd>{profileForm.specialty || "N/A"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Experience</dt>
                      <dd>{profileForm.experience || "N/A"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Email</dt>
                      <dd>{profileForm.email || "N/A"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Licence Number</dt>
                      <dd>{profileForm.license_id || "N/A"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Licence Expiry</dt>
                      <dd>{profileForm.license_expiry_date || "Not set"}</dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Annual Licence</dt>
                      <dd>
                        {profileForm.license_file_url ? (
                          <a
                            href={`${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}${profileForm.license_file_url}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {profileForm.license_file_name || "Open licence"}
                            {profileForm.license_file_size ? ` (${formatFileSize(profileForm.license_file_size)})` : ""}
                          </a>
                        ) : (
                          "Not uploaded"
                        )}
                      </dd>
                    </div>
                    <div className="account-detail-card">
                      <dt>Rating</dt>
                      <dd>{profileForm.rating_summary || "No ratings yet"}</dd>
                    </div>
                  </dl>

                  <div className="account-preview__links">
                    <button
                      className="account-inline-link account-inline-link--button"
                      type="button"
                      onClick={() => setShowPasswordOverlay(true)}
                    >
                      Change password
                    </button>
                  </div>
                </div>
              )}

            </SectionCard>
          </div>
        </div>
      </div>
      {passwordOverlay}
    </>
  );
}
