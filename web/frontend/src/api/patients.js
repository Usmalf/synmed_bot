import { authHeaders } from "./auth.js";
import { apiGet } from "./client";

export function lookupPatient(identifier) {
  const params = new URLSearchParams({ identifier });
  return apiGet(`/patients/lookup?${params.toString()}`);
}

export async function registerPatient(payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/register`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchCurrentPatient() {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/me`,
    {
      headers: {
        ...authHeaders(),
      },
    },
  );

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function fetchPatientHistory() {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/history`,
    {
      headers: {
        ...authHeaders(),
      },
    },
  );

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function fetchPatientDocuments() {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/documents`,
    {
      headers: {
        ...authHeaders(),
      },
    },
  );

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function updateCurrentPatient(payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/me`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    },
  );

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return body;
}

export async function changePatientPassword(currentPassword, newPassword) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/me/password`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    },
  );

  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || body?.message || `Request failed: ${response.status}`);
  }
  if (body.success === false) {
    throw new Error(body.message || "Unable to change password.");
  }

  return body;
}
