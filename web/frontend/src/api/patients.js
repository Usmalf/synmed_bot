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
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed: ${response.status}`);
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

export async function fetchMedicalReportRequests() {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/medical-report-requests`,
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

export async function createMedicalReportRequest(payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/medical-report-requests`,
    {
      method: "POST",
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

export async function initializeMedicalReportPayment(requestId, payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/medical-report-requests/${requestId}/pay`,
    {
      method: "POST",
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

export async function verifyMedicalReportPayment(requestId, paymentReference) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/medical-report-requests/${requestId}/verify/${paymentReference}`,
    {
      method: "POST",
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

export async function sendPatientSupportAiMessage(payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/support/ai`,
    {
      method: "POST",
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

export async function fetchPatientSupportTicket(ticketId) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/support-tickets/${encodeURIComponent(ticketId)}`,
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

export async function sendPatientSupportTicketMessage(ticketId, messageText) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/support-tickets/${encodeURIComponent(ticketId)}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({ message_text: messageText }),
    },
  );
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function submitPatientSupportTicketFeedback(ticketId, payload) {
  const response = await fetch(
    `${import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}/patients/support-tickets/${encodeURIComponent(ticketId)}/feedback`,
    {
      method: "POST",
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
