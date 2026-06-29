import { authHeaders } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export function fetchCustomerCareDesk() {
  return request("/customer-care/desk");
}

export function searchCustomerCareRecords(query) {
  return request(`/customer-care/search?query=${encodeURIComponent(query)}`);
}

export function fetchCustomerCarePatientDetail(patientId) {
  return request(`/customer-care/patients/${encodeURIComponent(patientId)}`);
}

export function sendCustomerCarePatientDocument(patientId, payload) {
  return request(`/customer-care/patients/${encodeURIComponent(patientId)}/documents/send`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function grantCustomerCareConsultationAccess(payload) {
  return request("/customer-care/payments/access-grant", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokeCustomerCareConsultationAccess(reference) {
  return request(`/customer-care/payments/access-grant/${encodeURIComponent(reference)}/revoke`, {
    method: "POST",
  });
}

export function verifyCustomerCarePayment(reference) {
  return request(`/customer-care/payments/${encodeURIComponent(reference)}/verify`, {
    method: "POST",
  });
}

export function deleteCustomerCarePaymentAttention(payload) {
  return request("/customer-care/payments/attention/delete", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function clearCustomerCarePaymentAttention() {
  return request("/customer-care/payments/attention/clear", {
    method: "POST",
  });
}

export function fetchCustomerCareAccounts() {
  return request("/customer-care/accounts");
}

export function fetchCustomerCareSupportTickets(status = "open") {
  return request(`/customer-care/support-tickets?status=${encodeURIComponent(status)}`);
}

export function fetchCustomerCareSupportTicket(ticketId) {
  return request(`/customer-care/support-tickets/${encodeURIComponent(ticketId)}`);
}

export function sendCustomerCareSupportTicketMessage(ticketId, messageText) {
  return request(`/customer-care/support-tickets/${encodeURIComponent(ticketId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ message_text: messageText }),
  });
}

export function updateCustomerCareSupportTicketStatus(ticketId, status) {
  return request(`/customer-care/support-tickets/${encodeURIComponent(ticketId)}/status`, {
    method: "POST",
    body: JSON.stringify(typeof status === "string" ? { status } : status),
  });
}

export function fetchCustomerCareMail() {
  return request("/customer-care/mail");
}

export function sendCustomerCareMail(payload) {
  return request("/customer-care/mail", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function markCustomerCareMailRead(messageId) {
  return request(`/customer-care/mail/${messageId}/read`, {
    method: "POST",
  });
}

export function createCustomerCareAccount(payload) {
  return request("/customer-care/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCustomerCareAccountStatus(accountId, status) {
  return request(`/customer-care/accounts/${accountId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}
