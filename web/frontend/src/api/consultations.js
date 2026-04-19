const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function requestConsultation(payload) {
  const response = await fetch(`${API_BASE_URL}/consultations/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchConsultationStatus(reference) {
  const response = await fetch(`${API_BASE_URL}/consultations/status/${reference}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchConsultationTranscript(reference) {
  const response = await fetch(`${API_BASE_URL}/consultations/transcript/${reference}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchConsultationDocuments(reference) {
  const response = await fetch(`${API_BASE_URL}/consultations/documents/${reference}`);

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function sendConsultationMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/consultations/message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function endConsultation(reference) {
  const response = await fetch(`${API_BASE_URL}/consultations/end`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ reference }),
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export async function submitConsultationFeedback(payload) {
  const response = await fetch(`${API_BASE_URL}/consultations/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export function createConsultationEventSource(reference) {
  return new EventSource(`${API_BASE_URL}/consultations/stream/${reference}`);
}
