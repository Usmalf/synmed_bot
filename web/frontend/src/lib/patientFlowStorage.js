const STORAGE_KEY = "synmed_patient_flow";

const DEFAULT_FLOW = {
  lookupIdentifier: "",
  returningEmail: "",
  lookupPatient: null,
  returningPayment: null,
  registrationPatient: null,
  newPayment: null,
  consultationReference: "",
  selectedAppointmentReference: "",
};

export function loadPatientFlow() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { ...DEFAULT_FLOW };
    }
    return { ...DEFAULT_FLOW, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_FLOW };
  }
}

export function savePatientFlow(patch) {
  const next = { ...loadPatientFlow(), ...patch };
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function clearPatientFlow() {
  window.localStorage.removeItem(STORAGE_KEY);
}
