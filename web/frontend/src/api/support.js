const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function sendPublicSupportAiMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/customer-care/support/ai`, {
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

export async function fetchPublicSupportTicket(ticketId, contactEmail) {
  const response = await fetch(
    `${API_BASE_URL}/customer-care/support/public-tickets/${encodeURIComponent(ticketId)}?contact_email=${encodeURIComponent(contactEmail)}`,
  );
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function sendPublicSupportTicketMessage(ticketId, messageText, contactEmail) {
  const response = await fetch(`${API_BASE_URL}/customer-care/support/public-tickets/${encodeURIComponent(ticketId)}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message_text: messageText, contact_email: contactEmail }),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return body;
}

export async function submitPublicSupportTicketFeedback(ticketId, payload) {
  const response = await fetch(`${API_BASE_URL}/customer-care/support/public-tickets/${encodeURIComponent(ticketId)}/feedback`, {
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
