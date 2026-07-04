import { authHeaders } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export async function fetchDoctorWorkspace() {
  const response = await fetch(`${API_BASE_URL}/doctors/workspace`, {
    headers: {
      ...authHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchCurrentDoctor() {
  const response = await fetch(`${API_BASE_URL}/doctors/me`, {
    headers: {
      ...authHeaders(),
    },
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function updateCurrentDoctor(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/me`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function changeDoctorPassword(currentPassword, newPassword) {
  const response = await fetch(`${API_BASE_URL}/doctors/me/password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function updateDoctorPresence(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/presence`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || body?.message || `Request failed: ${response.status}`);
  }
  if (!body?.active_consultation) {
    throw new Error(body?.message || "Unable to connect to that patient right now.");
  }
  return body;
}

export async function buildDoctorAccountPayload(form) {
  const payload = {
    name: form.name,
    specialty: form.specialty,
    experience: form.experience,
    email: form.email,
    license_id: form.license_id,
    license_expiry_date: form.license_expiry_date,
  };

  if (form.license_file) {
    payload.license_file_name = form.license_file.name;
    payload.license_file_type = form.license_file.type;
    payload.license_file_size = form.license_file.size;
    payload.license_file_data = await fileToDataUrl(form.license_file);
  }

  return payload;
}

export async function connectDoctorToPatient(runtimePatientId) {
  const response = await fetch(`${API_BASE_URL}/doctors/connect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ runtime_patient_id: Number(runtimePatientId) }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || body?.message || `Request failed: ${response.status}`);
  }
  return body;
}

export async function fetchDoctorMail() {
  const response = await fetch(`${API_BASE_URL}/doctors/mail`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function sendDoctorMail(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/mail`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function markDoctorMailRead(messageId) {
  const response = await fetch(`${API_BASE_URL}/doctors/mail/${messageId}/read`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}
