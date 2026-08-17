import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { Medication } from '@/types';
import { mmkvStorage } from '@/lib/storage';

interface MedicationState {
  medications: Medication[];
  activeMedications: Medication[];
  isLoading: boolean;
  error: string | null;
  setMedications: (medications: Medication[]) => void;
  addMedication: (medication: Medication) => void;
  updateMedication: (id: string, updates: Partial<Medication>) => void;
  removeMedication: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearMedications: () => void;
}

export const useMedicationStore = create<MedicationState>()(
  persist(
    (set, get) => ({
      // Initial state
      medications: [],
      activeMedications: [],
      isLoading: false,
      error: null,

      // Actions
      setMedications: (medications) => {
        const activeMeds = medications.filter(med => med.is_active);
        set({
          medications,
          activeMedications: activeMeds,
        });
      },

      addMedication: (medication) => {
        const { medications } = get();
        const updated = [...medications, medication];
        const activeMeds = updated.filter(med => med.is_active);
        set({
          medications: updated,
          activeMedications: activeMeds,
        });
      },

      updateMedication: (id, updates) => {
        const { medications } = get();
        const updated = medications.map(med => 
          med.id === id ? { ...med, ...updates } : med
        );
        const activeMeds = updated.filter(med => med.is_active);
        set({
          medications: updated,
          activeMedications: activeMeds,
        });
      },

      removeMedication: (id) => {
        const { medications } = get();
        const updated = medications.filter(med => med.id !== id);
        const activeMeds = updated.filter(med => med.is_active);
        set({
          medications: updated,
          activeMedications: activeMeds,
        });
      },

      setLoading: (isLoading) => {
        set({ isLoading });
      },

      setError: (error) => {
        set({ error });
      },

      clearMedications: () => {
        set({
          medications: [],
          activeMedications: [],
          error: null,
        });
      },
    }),
    {
      name: 'medication-storage',
      storage: createJSONStorage(() => mmkvStorage),
    }
  )
);

// Helper function to calculate overall adherence rate
export function calculateOverallAdherence(medications: Medication[]): number {
  if (medications.length === 0) return 100;
  
  const totalAdherence = medications.reduce((sum, med) => sum + med.adherence_rate, 0);
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
