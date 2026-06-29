import { authHeaders } from "./auth.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchPaymentConfig() {
  const response = await fetch(`${API_BASE_URL}/payments/config`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function initializePayment(payload) {
  const response = await fetch(`${API_BASE_URL}/payments/initialize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

export async function verifyPayment(reference) {
  const response = await fetch(`${API_BASE_URL}/payments/verify/${reference}`, {
    method: "POST",
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchCurrentPaymentStatus() {
  const response = await fetch(`${API_BASE_URL}/payments/current`, {
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
