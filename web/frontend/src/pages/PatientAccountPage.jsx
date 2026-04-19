import { useEffect, useState } from "react";
import SectionCard from "../components/SectionCard.jsx";
import { changePatientPassword, fetchCurrentPatient, updateCurrentPatient } from "../api/patients.js";
import "../styles/forms.css";
import "../styles/patient.css";
import "../styles/patient-portal.css";

function createEmptyProfile() {
  return {
    name: "",
    age: "",
    gender: "",
    phone: "",
    email: "",
    address: "",
    allergy: "",
    medical_conditions: "",
    hospital_number: "",
  };
}

export default function PatientAccountPage() {
  const [profileForm, setProfileForm] = useState(createEmptyProfile);
  const [profileState, setProfileState] = useState({
    status: "loading",
    message: "Loading patient account...",
  });
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
  });
  const [passwordState, setPasswordState] = useState({
    status: "idle",
    message: "Change your password here if you want to secure or rotate your account access.",
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadProfile() {
      try {
        const result = await fetchCurrentPatient();
        if (!ignore) {
          setProfileForm({
            name: result.patient?.name || "",
            age: String(result.patient?.age || ""),
            gender: result.patient?.gender || "",
            phone: result.patient?.phone || "",
            email: result.patient?.email || "",
            address: result.patient?.address || "",
            allergy: result.patient?.allergy || "",
            medical_conditions: result.patient?.medical_conditions || "",
            hospital_number: result.patient?.hospital_number || "",
          });
          setProfileState({
            status: "success",
            message: "Patient account loaded.",
          });
        }
      } catch (error) {
        if (!ignore) {
          setProfileState({
            status: "error",
            message: error.message || "Unable to load patient account.",
          });
        }
      }
    }

    loadProfile();
    return () => {
      ignore = true;
    };
  }, []);

  async function handleProfileSubmit(event) {
    event.preventDefault();
    setProfileState({
      status: "loading",
      message: "Saving patient account...",
    });

    try {
      const result = await updateCurrentPatient({
        ...profileForm,
        age: Number(profileForm.age),
      });
      setProfileForm({
        name: result.patient?.name || "",
        age: String(result.patient?.age || ""),
        gender: result.patient?.gender || "",
        phone: result.patient?.phone || "",
        email: result.patient?.email || "",
        address: result.patient?.address || "",
        allergy: result.patient?.allergy || "",
        medical_conditions: result.patient?.medical_conditions || "",
        hospital_number: result.patient?.hospital_number || "",
      });
      setProfileState({
        status: "success",
        message: result.message,
      });
      setIsEditingProfile(false);
    } catch (error) {
      setProfileState({
        status: "error",
        message: error.message || "Unable to save patient account.",
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
      const result = await changePatientPassword(passwordForm.currentPassword, passwordForm.newPassword);
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
        message: error.message || "Unable to change password.",
      });
    }
  }

  return (
    <div className="patient-account-grid">
      <SectionCard
        title="Account"
        subtitle="Preview your biodata here, then open edit only when you want to update it."
      >
        <div className="history-card">
          <div className="patient-history-preview">
            <div>
              <span className="workspace-pill">Biodata Preview</span>
              <p>{profileForm.name || "Patient account"}</p>
            </div>
            <button
              className="patient-shell__history-link patient-shell__history-link--button"
              type="button"
              onClick={() => setIsEditingProfile((current) => !current)}
            >
              {isEditingProfile ? "Close edit" : "Edit biodata"}
            </button>
          </div>

          <dl className="patient-profile-grid patient-profile-grid--account">
            <div>
              <dt>Hospital Number</dt>
              <dd>{profileForm.hospital_number || "N/A"}</dd>
            </div>
            <div>
              <dt>Phone</dt>
              <dd>{profileForm.phone || "N/A"}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{profileForm.email || "N/A"}</dd>
            </div>
            <div>
              <dt>Gender</dt>
              <dd>{profileForm.gender || "N/A"}</dd>
            </div>
            <div>
              <dt>Allergies</dt>
              <dd>{profileForm.allergy || "None recorded"}</dd>
            </div>
            <div>
              <dt>Prior Conditions</dt>
              <dd>{profileForm.medical_conditions || "None recorded"}</dd>
            </div>
            <div>
              <dt>Address</dt>
              <dd>{profileForm.address || "No address recorded"}</dd>
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
              <span className="form-field__label">Age</span>
              <input className="form-field__input" type="number" value={profileForm.age} onChange={(event) => setProfileForm((current) => ({ ...current, age: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Gender</span>
              <input className="form-field__input" type="text" value={profileForm.gender} onChange={(event) => setProfileForm((current) => ({ ...current, gender: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Phone</span>
              <input className="form-field__input" type="text" value={profileForm.phone} onChange={(event) => setProfileForm((current) => ({ ...current, phone: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Email</span>
              <input className="form-field__input" type="email" value={profileForm.email} onChange={(event) => setProfileForm((current) => ({ ...current, email: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Address</span>
              <textarea className="form-field__input form-field__input--textarea" rows="3" value={profileForm.address} onChange={(event) => setProfileForm((current) => ({ ...current, address: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Allergies</span>
              <input className="form-field__input" type="text" value={profileForm.allergy} onChange={(event) => setProfileForm((current) => ({ ...current, allergy: event.target.value }))} />
            </label>
            <label className="form-field">
              <span className="form-field__label">Prior Medical Conditions</span>
              <textarea className="form-field__input form-field__input--textarea" rows="3" placeholder="Hypertension, diabetes, sickle cell, asthma..." value={profileForm.medical_conditions} onChange={(event) => setProfileForm((current) => ({ ...current, medical_conditions: event.target.value }))} />
            </label>
            <button className="button button--primary" type="submit">
              Save Biodata
            </button>
          </form>
        ) : null}

        <div className={`lookup-result lookup-result--${profileState.status}`}>
          <p className="lookup-result__message">{profileState.message}</p>
        </div>
      </SectionCard>

      <SectionCard
        title="Change Password"
        subtitle="Update the password you use for web sign in without affecting your patient record."
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
