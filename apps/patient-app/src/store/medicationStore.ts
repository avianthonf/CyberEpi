import {create} from 'zustand';
import {Medication} from '@/types';
import {mmkv} from '@/lib/storage';
import {getPatientSession, SessionChangedError} from '@/lib/patientSession';

interface MedicationState {
  ownerId: string | null;
  medications: Medication[];
  activeMedications: Medication[];
  isLoading: boolean;
  error: string | null;
  bindPatient: (patientId: string | null) => void;
  setMedications: (patientId: string, medications: Medication[]) => void;
  addMedication: (patientId: string, medication: Medication) => void;
  updateMedication: (patientId: string, id: string, updates: Partial<Medication>) => void;
  removeMedication: (patientId: string, id: string) => void;
}

function isOwnedMedication(value: unknown): value is Medication {
  if (!value || typeof value !== 'object') return false;
  const medication = value as Partial<Medication>;
  return (
    typeof medication.patient_id === 'string' &&
    /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(medication.patient_id) &&
    typeof medication.id === 'string' &&
    medication.id.trim().length > 0 &&
    typeof medication.drug_name === 'string' &&
    typeof medication.is_active === 'boolean' &&
    typeof medication.adherence_rate === 'number'
  );
}

function readMedications(patientId: string): Medication[] {
  const raw = mmkv.getString(`medications:${patientId}`);
  if (!raw) return [];
  const records: unknown = JSON.parse(raw);
  if (
    !Array.isArray(records) ||
    !records.every(item => isOwnedMedication(item) && item.patient_id === patientId)
  ) {
    throw new Error('Saved medications do not have a matching patient owner.');
  }
  return records;
}

function migrateLegacyMedications(): void {
  const raw = mmkv.getString('medication-storage');
  if (!raw) return;
  const legacy = JSON.parse(raw);
  const records: unknown = legacy?.state?.medications;
  if (!Array.isArray(records)) return; // Leave unrecognised legacy data untouched.
  const groups = new Map<string, Medication[]>();
  const remaining: unknown[] = [];
  for (const record of records) {
    if (!isOwnedMedication(record)) {
      remaining.push(record);
      continue;
    }
    const group = groups.get(record.patient_id) || [];
    if (!group.some(item => item.id === record.id)) group.push(record);
    groups.set(record.patient_id, group);
  }
  if (!groups.size) return;
  // Commit every destination before changing the legacy source. On a partial
  // write failure, a retry keeps the newer destination record for each ID.
  for (const [owner, medications] of groups) {
    const existing = readMedications(owner);
    const ids = new Set(existing.map(item => item.id));
    mmkv.set(
      `medications:${owner}`,
      JSON.stringify([...existing, ...medications.filter(item => !ids.has(item.id))]),
    );
  }
  const remainingActive = Array.isArray(legacy.state.activeMedications)
    ? legacy.state.activeMedications.filter((item: unknown) => !isOwnedMedication(item))
    : [];
  if (remaining.length || remainingActive.length) {
    mmkv.set('medication-storage', JSON.stringify({
      ...legacy,
      state: {...legacy.state, medications: remaining, activeMedications: remainingActive},
    }));
  } else {
    mmkv.delete('medication-storage');
  }
}

export const useMedicationStore = create<MedicationState>((set, get) => {
  const save = (patientId: string, medications: Medication[]) => {
    if (get().ownerId !== patientId || getPatientSession().patientId !== patientId) {
      throw new SessionChangedError();
    }
    if (!medications.every(item => isOwnedMedication(item) && item.patient_id === patientId)) {
      throw new Error('Medication patient owner does not match the signed-in patient.');
    }
    mmkv.set(`medications:${patientId}`, JSON.stringify(medications));
    set({
      medications,
      activeMedications: medications.filter(item => item.is_active),
      error: null,
    });
  };

  return {
    ownerId: null,
    medications: [],
    activeMedications: [],
    isLoading: false,
    error: null,

    bindPatient: patientId => {
      set({
        ownerId: patientId,
        medications: [],
        activeMedications: [],
        isLoading: false,
        error: null,
      });
      if (!patientId) return;
      try {
        migrateLegacyMedications();
      } catch {
        set({error: 'Legacy medication migration could not finish. Existing records were retained.'});
      }
      try {
        const medications = readMedications(patientId);
        set({medications, activeMedications: medications.filter(item => item.is_active)});
      } catch {
        set({error: 'Saved medications could not be loaded. No records were removed.'});
      }
    },

    setMedications: save,
    addMedication: (patientId, medication) => {
      const medications = get().medications;
      const existing = medications.find(item => item.id === medication.id);
      save(patientId, existing
        ? medications.map(item => item.id === medication.id ? medication : item)
        : [...medications, medication]);
    },
    updateMedication: (patientId, id, updates) => {
      save(patientId, get().medications.map(item =>
        item.id === id ? {...item, ...updates, id, patient_id: patientId} : item,
      ));
    },
    removeMedication: (patientId, id) => {
      save(patientId, get().medications.filter(item => item.id !== id));
    },
  };
});

// Helper function to calculate overall adherence rate
export function calculateOverallAdherence(medications: Medication[]): number {
  if (medications.length === 0) return 100;

  const totalAdherence = medications.reduce(
    (sum, med) => sum + med.adherence_rate,
    0,
  );
  return Math.round(totalAdherence / medications.length);
}

// Helper function to get next dose time
export function getNextDoseTime(medication: Medication): string | null {
  if (!medication.is_active || !medication.next_dose) {
    return null;
  }

  const nextDose = new Date(medication.next_dose);
  const now = new Date();

  // If next dose is in the past, return null
  if (nextDose < now) {
    return null;
  }

  // Format time as HH:MM AM/PM
  return nextDose.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

// Helper function to check if dose is due soon (within 30 minutes)
export function isDoseDueSoon(medication: Medication): boolean {
  if (!medication.is_active || !medication.next_dose) {
    return false;
  }

  const nextDose = new Date(medication.next_dose);
  const now = new Date();
  const thirtyMinutesFromNow = new Date(now.getTime() + 30 * 60 * 1000);

  return nextDose >= now && nextDose <= thirtyMinutesFromNow;
}

// Helper function to check if dose is overdue
export function isDoseOverdue(medication: Medication): boolean {
  if (!medication.is_active || !medication.next_dose) {
    return false;
  }

  const nextDose = new Date(medication.next_dose);
  const now = new Date();
  const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);

  return nextDose < now && nextDose > oneHourAgo;
}
