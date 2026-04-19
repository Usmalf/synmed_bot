const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const AUTH_TOKEN_KEY = "synmed_auth_token";
const DOCTOR_LOGIN_PENDING_KEY = "synmed_doctor_login_pending";
const DOCTOR_SIGNUP_PENDING_KEY = "synmed_doctor_signup_pending";
const DOCTOR_RECOVERY_PENDING_KEY = "synmed_doctor_recovery_pending";
const PATIENT_LOGIN_PENDING_KEY = "synmed_patient_login_pending";
const PATIENT_RECOVERY_PENDING_KEY = "synmed_patient_recovery_pending";

export function getAuthToken() {
  return window.localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export function setAuthToken(token) {
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function setPendingDoctorLoginIdentifier(identifier) {
  window.sessionStorage.setItem(DOCTOR_LOGIN_PENDING_KEY, identifier);
}

export function getPendingDoctorLoginIdentifier() {
  return window.sessionStorage.getItem(DOCTOR_LOGIN_PENDING_KEY) || "";
}

export function clearPendingDoctorLoginIdentifier() {
  window.sessionStorage.removeItem(DOCTOR_LOGIN_PENDING_KEY);
}

export function setPendingDoctorSignupIdentifier(identifier) {
  window.sessionStorage.setItem(DOCTOR_SIGNUP_PENDING_KEY, identifier);
}

export function getPendingDoctorSignupIdentifier() {
  return window.sessionStorage.getItem(DOCTOR_SIGNUP_PENDING_KEY) || "";
}

export function clearPendingDoctorSignupIdentifier() {
  window.sessionStorage.removeItem(DOCTOR_SIGNUP_PENDING_KEY);
}

export function setPendingDoctorRecoveryIdentifier(identifier) {
  window.sessionStorage.setItem(DOCTOR_RECOVERY_PENDING_KEY, identifier);
}

export function getPendingDoctorRecoveryIdentifier() {
  return window.sessionStorage.getItem(DOCTOR_RECOVERY_PENDING_KEY) || "";
}

export function clearPendingDoctorRecoveryIdentifier() {
  window.sessionStorage.removeItem(DOCTOR_RECOVERY_PENDING_KEY);
}

export function setPendingPatientLoginIdentifier(identifier) {
  window.sessionStorage.setItem(PATIENT_LOGIN_PENDING_KEY, identifier);
}

export function getPendingPatientLoginIdentifier() {
  return window.sessionStorage.getItem(PATIENT_LOGIN_PENDING_KEY) || "";
}

export function clearPendingPatientLoginIdentifier() {
  window.sessionStorage.removeItem(PATIENT_LOGIN_PENDING_KEY);
}

export function setPendingPatientRecoveryIdentifier(identifier) {
  window.sessionStorage.setItem(PATIENT_RECOVERY_PENDING_KEY, identifier);
}

export function getPendingPatientRecoveryIdentifier() {
  return window.sessionStorage.getItem(PATIENT_RECOVERY_PENDING_KEY) || "";
}

export function clearPendingPatientRecoveryIdentifier() {
  window.sessionStorage.removeItem(PATIENT_RECOVERY_PENDING_KEY);
}

export function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function requestOtp(payload) {
  const response = await fetch(`${API_BASE_URL}/auth/request-otp`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function verifyOtp(payload) {
  const response = await fetch(`${API_BASE_URL}/auth/verify-otp`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function loginDoctor(identifier, password, otpChannel = "telegram") {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ identifier, password, otp_channel: otpChannel }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function verifyDoctorLogin(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/login/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      otp_code: otpCode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function signupDoctor(identifier, email, password, otpChannel = "telegram") {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/signup`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      email,
      password,
      otp_channel: otpChannel,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function verifyDoctorSignup(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/signup/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      otp_code: otpCode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function requestDoctorRecovery(identifier, email, newPassword, otpChannel = "email") {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/recovery/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      email,
      new_password: newPassword,
      otp_channel: otpChannel,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function verifyDoctorRecovery(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/recovery/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      otp_code: otpCode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function loginAdmin(adminId) {
  const response = await fetch(`${API_BASE_URL}/auth/admin/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ admin_id: Number(adminId) }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function loginPatient(identifier, password, otpChannel = "email") {
  const response = await fetch(`${API_BASE_URL}/auth/patient/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      password,
      otp_channel: otpChannel,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function verifyPatientLogin(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/patient/login/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      otp_code: otpCode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function requestPatientRecovery(identifier, email, newPassword) {
  const response = await fetch(`${API_BASE_URL}/auth/patient/recovery/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      email,
      new_password: newPassword,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function verifyPatientRecovery(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/patient/recovery/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      identifier,
      otp_code: otpCode,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function restoreSession() {
  const response = await fetch(`${API_BASE_URL}/auth/session`, {
    headers: {
      ...authHeaders(),
    },
  });

  const body = await response.json();
  if (!response.ok) {
    clearAuthToken();
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token);
  }

  return body;
}

export async function fetchDeliveryStatus() {
  const response = await fetch(`${API_BASE_URL}/auth/delivery-status`);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}
