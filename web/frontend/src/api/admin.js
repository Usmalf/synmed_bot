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
