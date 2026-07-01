import { authHeaders } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchAdminSummary() {
  const response = await fetch(`${API_BASE_URL}/admin/summary`, {
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

export async function fetchAdminAlerts() {
  const response = await fetch(`${API_BASE_URL}/admin/alerts`, {
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

export async function markAdminAlertReviewed(alertId) {
  const response = await fetch(`${API_BASE_URL}/admin/alerts/${encodeURIComponent(alertId)}/review`, {
    method: "POST",
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

export async function dismissAdminAlert(alertId) {
  const response = await fetch(`${API_BASE_URL}/admin/alerts/${encodeURIComponent(alertId)}`, {
    method: "DELETE",
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

export async function fetchAdminAuditLogs(limit = 100) {
  const response = await fetch(`${API_BASE_URL}/admin/audit-logs?limit=${encodeURIComponent(limit)}`, {
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

export async function fetchAdminErrorLogs(limit = 100, severity = "all") {
  const response = await fetch(
    `${API_BASE_URL}/admin/error-logs?limit=${encodeURIComponent(limit)}&severity=${encodeURIComponent(severity)}`,
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

export async function fetchAdminMail() {
  const response = await fetch(`${API_BASE_URL}/admin/mail`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function sendAdminMail(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/mail`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function markAdminMailRead(messageId) {
  const response = await fetch(`${API_BASE_URL}/admin/mail/${messageId}/read`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function fetchAdminSupportTickets(status = "all") {
  const response = await fetch(`${API_BASE_URL}/admin/support-tickets?status=${encodeURIComponent(status)}`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function fetchAdminSupportTicket(ticketId) {
  const response = await fetch(`${API_BASE_URL}/admin/support-tickets/${encodeURIComponent(ticketId)}`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function updateAdminSupportTicketStatus(ticketId, payload) {
  const response = await fetch(`${API_BASE_URL}/admin/support-tickets/${encodeURIComponent(ticketId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function fetchAdminPatients(query = "") {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("query", query.trim());
  }
  const response = await fetch(`${API_BASE_URL}/admin/patients?${params.toString()}`, {
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

export async function fetchAdminPayments() {
  const response = await fetch(`${API_BASE_URL}/admin/payments`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function grantAdminConsultationAccess(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/payments/access-grant`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function revokeAdminConsultationAccess(reference) {
  const response = await fetch(`${API_BASE_URL}/admin/payments/access-grant/${encodeURIComponent(reference)}/revoke`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function verifyAdminPayment(reference) {
  const response = await fetch(`${API_BASE_URL}/admin/payments/${encodeURIComponent(reference)}/verify`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function deleteAdminPaymentAttention(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/payments/attention/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function clearAdminPaymentAttention() {
  const response = await fetch(`${API_BASE_URL}/admin/payments/attention/clear`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function searchAdminRecords(query) {
  const response = await fetch(`${API_BASE_URL}/admin/search?query=${encodeURIComponent(query)}`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function fetchAdminPatientDetail(patientId) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}`, {
    headers: { ...authHeaders() },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body?.detail || `Request failed: ${response.status}`);
  return body;
}

export async function sendAdminPatientDocument(patientId, payload) {
  const response = await fetch(`${API_BASE_URL}/admin/patients/${encodeURIComponent(patientId)}/documents/send`, {
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

export async function fetchAdminConsultations() {
  const response = await fetch(`${API_BASE_URL}/admin/consultations`, {
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

export async function fetchAdminConsultation(consultationId) {
  const response = await fetch(`${API_BASE_URL}/admin/consultations/${encodeURIComponent(consultationId)}`, {
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

export async function fetchAdminRatings() {
  const response = await fetch(`${API_BASE_URL}/admin/ratings`, {
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

export async function fetchAdminDeliverySettings() {
  const response = await fetch(`${API_BASE_URL}/admin/delivery-settings`, {
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

export async function fetchAdminBackupStatus() {
  const response = await fetch(`${API_BASE_URL}/admin/backups/status`, {
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

function filenameFromDisposition(disposition, fallback) {
  const match = /filename="?([^"]+)"?/i.exec(disposition || "");
  return match?.[1] || fallback;
}

export async function downloadAdminBackup(kind = "database") {
  const safeKind = kind === "full" ? "full" : "database";
  const response = await fetch(`${API_BASE_URL}/admin/backups/${safeKind}`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
  });
  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const body = await response.json();
      message = body?.detail || message;
    } catch {}
    throw new Error(message);
  }
  const blob = await response.blob();
  const filename = filenameFromDisposition(
    response.headers.get("Content-Disposition"),
    safeKind === "full" ? "synmed_full_backup.zip" : "synmed_backup.db",
  );
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  return { filename, size: blob.size };
}

export async function testAdminDelivery(channel, target) {
  const response = await fetch(`${API_BASE_URL}/admin/delivery-settings/test`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ channel, target }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function updateAdminPaymentSettings(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/settings/payments`, {
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

export async function updateAdminEmailBranding(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/settings/email-branding`, {
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

export async function approveDoctorApplication(doctorId) {
  const response = await fetch(`${API_BASE_URL}/admin/doctor-applications/${doctorId}/approve`, {
    method: "POST",
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

export async function rejectDoctorApplication(doctorId, reason = "") {
  const response = await fetch(`${API_BASE_URL}/admin/doctor-applications/${doctorId}/reject`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ reason }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function suspendDoctorAccount(doctorId, reason = "") {
  const response = await fetch(`${API_BASE_URL}/admin/doctors/${doctorId}/suspend`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ reason }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function reactivateDoctorAccount(doctorId) {
  const response = await fetch(`${API_BASE_URL}/admin/doctors/${doctorId}/reactivate`, {
    method: "POST",
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

export async function sendDoctorLicenseReminder(doctorId) {
  const response = await fetch(`${API_BASE_URL}/admin/doctors/${doctorId}/license-reminder`, {
    method: "POST",
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

export async function fetchHealthTips(audience = "landing") {
  const response = await fetch(`${API_BASE_URL}/health-tips?audience=${encodeURIComponent(audience)}`);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function fetchAdminHealthTips() {
  const response = await fetch(`${API_BASE_URL}/admin/health-tips`, {
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

export async function createAdminHealthTip(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/health-tips`, {
    method: "POST",
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

export async function updateAdminHealthTip(tipId, payload) {
  const response = await fetch(`${API_BASE_URL}/admin/health-tips/${tipId}`, {
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

export async function deleteAdminHealthTip(tipId) {
  const response = await fetch(`${API_BASE_URL}/admin/health-tips/${tipId}`, {
    method: "DELETE",
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

export async function fetchAdminMedicalReportRequests() {
  const response = await fetch(`${API_BASE_URL}/admin/medical-report-requests`, {
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

export async function assignAdminMedicalReportRequest(requestId, doctorId) {
  const response = await fetch(`${API_BASE_URL}/admin/medical-report-requests/${requestId}/assign`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ doctor_id: doctorId }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function fetchAdminPartners() {
  const response = await fetch(`${API_BASE_URL}/admin/partners`, {
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

export async function createAdminPartner(payload) {
  const response = await fetch(`${API_BASE_URL}/admin/partners`, {
    method: "POST",
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

export async function updateAdminPartnerStatus(partnerId, status) {
  const response = await fetch(`${API_BASE_URL}/admin/partners/${encodeURIComponent(partnerId)}/status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ status }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}
