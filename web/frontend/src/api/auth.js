const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const AUTH_TOKEN_KEY = "synmed_auth_token";
const AUTH_SESSION_TOKEN_KEY = "synmed_auth_token_session";
const LOGIN_PENDING_KEY = "synmed_login_pending";
const DOCTOR_LOGIN_PENDING_KEY = "synmed_doctor_login_pending";
const DOCTOR_SIGNUP_PENDING_KEY = "synmed_doctor_signup_pending";
const DOCTOR_RECOVERY_PENDING_KEY = "synmed_doctor_recovery_pending";
const PATIENT_LOGIN_PENDING_KEY = "synmed_patient_login_pending";
const PATIENT_RECOVERY_PENDING_KEY = "synmed_patient_recovery_pending";

export function getAuthToken() {
  return (
    window.localStorage.getItem(AUTH_TOKEN_KEY) ||
    window.sessionStorage.getItem(AUTH_SESSION_TOKEN_KEY) ||
    ""
  );
}

export function setAuthToken(token, options = {}) {
  const rememberMe = options.rememberMe !== false;
  const notify = options.notify !== false;
  if (rememberMe) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    window.sessionStorage.removeItem(AUTH_SESSION_TOKEN_KEY);
    if (notify) {
      window.dispatchEvent(new Event("synmed:session-updated"));
    }
    return;
  }
  window.sessionStorage.setItem(AUTH_SESSION_TOKEN_KEY, token);
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  if (notify) {
    window.dispatchEvent(new Event("synmed:session-updated"));
  }
}

export function clearAuthToken(options = {}) {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.sessionStorage.removeItem(AUTH_SESSION_TOKEN_KEY);
  if (options.notify !== false) {
    window.dispatchEvent(new Event("synmed:session-updated"));
  }
}

export function setPendingLogin(payload) {
  window.sessionStorage.setItem(LOGIN_PENDING_KEY, JSON.stringify(payload));
}

export function getPendingLogin() {
  const raw = window.sessionStorage.getItem(LOGIN_PENDING_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearPendingLogin() {
  window.sessionStorage.removeItem(LOGIN_PENDING_KEY);
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

export async function loginWebUser(identifier, password) {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ identifier, password }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function bootstrapAdminAccount(adminId, email, displayName, password) {
  const response = await fetch(`${API_BASE_URL}/auth/admin/bootstrap`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      admin_id: Number(adminId),
      email,
      display_name: displayName,
      password,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function loginPatientWithGoogle(credential, options = {}) {
  const response = await fetch(`${API_BASE_URL}/auth/google/patient`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ credential }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token, options);
  }

  return body;
}

export async function verifyWebUserLogin(identifier, otpCode, options = {}) {
  const response = await fetch(`${API_BASE_URL}/auth/login/verify`, {
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
    setAuthToken(body.token, options);
  }

  return body;
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

export async function submitDoctorApplication(payload) {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/application`, {
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

export async function verifyDoctorApplication(identifier, otpCode) {
  const response = await fetch(`${API_BASE_URL}/auth/doctor/application/verify`, {
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

export async function setupPatientWebPassword(hospitalNumber, token, password) {
  const response = await fetch(`${API_BASE_URL}/auth/patient/setup-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      hospital_number: hospitalNumber,
      token,
      password,
    }),
  });

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function restoreSession() {
  const currentToken = getAuthToken();
  if (!currentToken) {
    throw new Error("No saved session.");
  }
  const rememberMe = Boolean(window.localStorage.getItem(AUTH_TOKEN_KEY));
  const response = await fetch(`${API_BASE_URL}/auth/session`, {
    headers: {
      Authorization: `Bearer ${currentToken}`,
    },
  });

  const body = await response.json();
  if (!response.ok) {
    clearAuthToken({ notify: false });
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  if (body.token) {
    setAuthToken(body.token, { rememberMe, notify: false });
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
