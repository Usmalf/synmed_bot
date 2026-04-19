import { authHeaders } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function parseResponse(response) {
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function fetchPatientFollowups() {
  const response = await fetch(`${API_BASE_URL}/followups/upcoming`, {
    headers: {
      ...authHeaders(),
    },
  });
  return parseResponse(response);
}

export async function fetchFollowup(reference) {
  const response = await fetch(`${API_BASE_URL}/followups/${encodeURIComponent(reference)}`, {
    headers: {
      ...authHeaders(),
    },
  });
  return parseResponse(response);
}

export async function bookFollowup(payload) {
  const response = await fetch(`${API_BASE_URL}/followups/book`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function initializeFollowupPayment(reference, payload = {}) {
  const response = await fetch(
    `${API_BASE_URL}/followups/${encodeURIComponent(reference)}/payment/initialize`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
    },
  );
  return parseResponse(response);
}

export async function verifyFollowupPayment(reference, paymentReference) {
  const response = await fetch(
    `${API_BASE_URL}/followups/${encodeURIComponent(reference)}/payment/verify/${encodeURIComponent(paymentReference)}`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
      },
    },
  );
  return parseResponse(response);
}

export async function markFollowupPayLater(reference) {
  const response = await fetch(
    `${API_BASE_URL}/followups/${encodeURIComponent(reference)}/payment/pay-later`,
    {
      method: "POST",
      headers: {
        ...authHeaders(),
      },
    },
  );
  return parseResponse(response);
}

export async function redeemFollowupPaymentCode(reference, paymentCode) {
  const response = await fetch(
    `${API_BASE_URL}/followups/${encodeURIComponent(reference)}/payment/redeem`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({ payment_code: paymentCode }),
    },
  );
  return parseResponse(response);
}
