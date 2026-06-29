import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCurrentPatient, updateCurrentPatient } from "../api/patients.js";
import "../styles/forms.css";
import "../styles/account.css";
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
  const [savedProfile, setSavedProfile] = useState(createEmptyProfile);
  const [profileState, setProfileState] = useState({
    status: "loading",
    message: "Loading patient account...",
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);

  useEffect(() => {
    let ignore = false;

    async function loadProfile() {
      try {
        const result = await fetchCurrentPatient();
        if (!ignore) {
          const nextProfile = {
            name: result.patient?.name || "",
            age: String(result.patient?.age || ""),
            gender: result.patient?.gender || "",
            phone: result.patient?.phone || "",
            email: result.patient?.email || "",
            address: result.patient?.address || "",
            allergy: result.patient?.allergy || "",
            medical_conditions: result.patient?.medical_conditions || "",
            hospital_number: result.patient?.hospital_number || "",
          };
          setProfileForm(nextProfile);
          setSavedProfile(nextProfile);
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
      const nextProfile = {
        name: result.patient?.name || "",
        age: String(result.patient?.age || ""),
        gender: result.patient?.gender || "",
        phone: result.patient?.phone || "",
        email: result.patient?.email || "",
        address: result.patient?.address || "",
        allergy: result.patient?.allergy || "",
        medical_conditions: result.patient?.medical_conditions || "",
        hospital_number: result.patient?.hospital_number || "",
      };
      setProfileForm(nextProfile);
      setSavedProfile(nextProfile);
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

  function handleStartEditing() {
    setProfileForm(savedProfile);
    setIsEditingProfile(true);
  }

  function handleCancelEditing() {
    setProfileForm(savedProfile);
    setIsEditingProfile(false);
    setProfileState({
      status: "success",
      message: "Biodata preview restored.",
    });
  }

  return (
    <div className="account-layout">
      <div className="account-grid">
        <div className="account-column">
          <div className="account-preview">
            {isEditingProfile ? (
              <div className="account-preview__edit">
                <div className="account-preview__top">
                  <div>
                    <span className="workspace-pill">Biodata</span>
                    <p className="account-preview__name">Edit biodata</p>
                  </div>
                </div>
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
                  <div className="account-edit-actions">
                    <button className="button button--primary" type="submit">
                      Save Biodata
                    </button>
                    <button className="button button--secondary" type="button" onClick={handleCancelEditing}>
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <>
                <div className="account-preview__top">
                  <div>
                    <span className="workspace-pill">Biodata</span>
                    <p className="account-preview__name">{profileForm.name || "Patient account"}</p>
                  </div>
                  <button
                    className="patient-shell__history-link patient-shell__history-link--button"
                    type="button"
                    onClick={handleStartEditing}
                  >
                    Edit biodata
                  </button>
                </div>

                <dl className="account-stat-grid">
                  <div className="account-detail-card">
                    <dt>Hospital Number</dt>
                    <dd>{profileForm.hospital_number || "N/A"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Phone</dt>
                    <dd>{profileForm.phone || "N/A"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Email</dt>
                    <dd>{profileForm.email || "N/A"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Gender</dt>
                    <dd>{profileForm.gender || "N/A"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Allergies</dt>
                    <dd>{profileForm.allergy || "None recorded"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Prior Conditions</dt>
                    <dd>{profileForm.medical_conditions || "None recorded"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Address</dt>
                    <dd>{profileForm.address || "No address recorded"}</dd>
                  </div>
                  <div className="account-detail-card">
                    <dt>Age</dt>
                    <dd>{profileForm.age || "N/A"}</dd>
                  </div>
                </dl>

                <div className="account-preview__links">
                  <Link className="account-inline-link" to="/patient/recover">
                    Change password
                  </Link>
                </div>
              </>
            )}

            {profileState.status !== "success" ? (
              <div className={`lookup-result lookup-result--${profileState.status}`}>
                <p className="lookup-result__message">{profileState.message}</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
