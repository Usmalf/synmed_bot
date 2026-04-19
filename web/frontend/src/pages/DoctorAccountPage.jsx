import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import SectionCard from "../components/SectionCard.jsx";
import { restoreSession } from "../api/auth.js";
import { changeDoctorPassword, fetchCurrentDoctor, updateCurrentDoctor } from "../api/doctors.js";
import "../styles/forms.css";
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
    rating_summary: "",
  };
}

export default function DoctorAccountPage() {
  const navigate = useNavigate();
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
      const result = await updateCurrentDoctor({
        name: profileForm.name,
        specialty: profileForm.specialty,
        experience: profileForm.experience,
        email: profileForm.email,
        license_id: profileForm.license_id,
        license_expiry_date: profileForm.license_expiry_date,
      });
      setProfileForm({
        doctor_id: String(result.doctor?.doctor_id || ""),
        name: result.doctor?.name || "",
        specialty: result.doctor?.specialty || "",
        experience: result.doctor?.experience || "",
        email: result.doctor?.email || "",
        license_id: result.doctor?.license_id || "",
        license_expiry_date: result.doctor?.license_expiry_date || "",
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
    } catch (error) {
      setPasswordState({
        status: "error",
        message: error.message || "Unable to change doctor password.",
      });
    }
  }

  return (
    <div className="patient-account-grid">
      <SectionCard
        title="Doctor Account"
        subtitle="Preview your SynMed doctor profile here, then open edit only when you need to update your details."
      >
        <div className="history-card">
          <div className="patient-history-preview">
            <div>
              <span className="workspace-pill">Profile Preview</span>
              <p>{profileForm.name || "Doctor profile"}</p>
            </div>
            <button
              className="patient-shell__history-link patient-shell__history-link--button"
              type="button"
              onClick={() => setIsEditingProfile((current) => !current)}
            >
              {isEditingProfile ? "Close edit" : "Edit profile"}
            </button>
          </div>

          <dl className="patient-profile-grid patient-profile-grid--account">
            <div>
              <dt>Doctor ID</dt>
              <dd>{profileForm.doctor_id || "N/A"}</dd>
            </div>
            <div>
              <dt>Specialty</dt>
              <dd>{profileForm.specialty || "N/A"}</dd>
            </div>
            <div>
              <dt>Experience</dt>
              <dd>{profileForm.experience || "N/A"}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{profileForm.email || "N/A"}</dd>
            </div>
            <div>
              <dt>Licence Number</dt>
              <dd>{profileForm.license_id || "N/A"}</dd>
            </div>
            <div>
              <dt>Licence Expiry</dt>
              <dd>{profileForm.license_expiry_date || "Not set"}</dd>
            </div>
            <div>
              <dt>Rating</dt>
              <dd>{profileForm.rating_summary || "No ratings yet"}</dd>
            </div>
          </dl>
        </div>

        {isEditingProfile ? (
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
            <button className="button button--primary" type="submit">
              Save Profile
            </button>
          </form>
        ) : null}

        <div className={`lookup-result lookup-result--${profileState.status}`}>
          <p className="lookup-result__message">{profileState.message}</p>
        </div>
      </SectionCard>

      <SectionCard
        title="Change Password"
        subtitle="Keep your doctor account current and secure without touching the medical profile itself."
      >
        <form className="form-panel" onSubmit={handlePasswordSubmit}>
          <label className="form-field">
            <span className="form-field__label">Current Password</span>
            <input className="form-field__input" type="password" value={passwordForm.currentPassword} onChange={(event) => setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))} />
          </label>
          <label className="form-field">
            <span className="form-field__label">New Password</span>
            <input className="form-field__input" type="password" value={passwordForm.newPassword} onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))} />
          </label>
          <button className="button button--primary" type="submit">
            Change Password
          </button>
        </form>

        <div className={`lookup-result lookup-result--${passwordState.status}`}>
          <p className="lookup-result__message">{passwordState.message}</p>
        </div>
      </SectionCard>
    </div>
  );
}
