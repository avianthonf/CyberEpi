export interface PatientSession {
  readonly patientId: string | null;
  readonly generation: number;
}

let currentSession: PatientSession = {patientId: null, generation: 0};

export class SessionChangedError extends Error {
  constructor() {
    super('The signed-in patient changed. Please try again in the current account.');
    this.name = 'SessionChangedError';
  }
}

export function getPatientSession(): PatientSession {
  return currentSession;
}

// Only authStore changes this boundary, synchronously before publishing auth state.
export function changePatientSession(patientId: string | null): PatientSession {
  currentSession = {patientId, generation: currentSession.generation + 1};
  return currentSession;
}

export function isPatientSessionCurrent(session: PatientSession): boolean {
  return (
    session.patientId === currentSession.patientId &&
    session.generation === currentSession.generation
  );
}

export function requirePatientSession(): PatientSession & {patientId: string} {
  const session = currentSession;
  if (!session.patientId) {
    throw new Error('Please sign in before accessing patient records.');
  }
  return session as PatientSession & {patientId: string};
}

export function assertPatientSession(session: PatientSession): void {
  if (!isPatientSessionCurrent(session)) {
    throw new SessionChangedError();
  }
}
