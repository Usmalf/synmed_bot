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

export async function fetchDoctorTranscript() {
  const response = await fetch(`${API_BASE_URL}/doctors/transcript`, {
    headers: {
      ...authHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function sendDoctorMessage(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function sendDoctorAttachment(file) {
  const response = await fetch(`${API_BASE_URL}/doctors/attachment`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      filename: file.name || "attachment",
      content_type: file.type || "application/octet-stream",
      data: await fileToDataUrl(file),
    }),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function endDoctorChat(doctorId) {
  const response = await fetch(`${API_BASE_URL}/doctors/end-chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ doctor_id: Number(doctorId) }),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function startDoctorCall(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/call/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function acceptDoctorCall(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/call/accept`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function rejectDoctorCall() {
  const response = await fetch(`${API_BASE_URL}/doctors/call/reject`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function endDoctorCall() {
  const response = await fetch(`${API_BASE_URL}/doctors/call/end`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export async function sendDoctorCallCandidate(payload) {
  const response = await fetch(`${API_BASE_URL}/doctors/call/candidate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}
