import {MMKV} from 'react-native-mmkv';
import {randomUUID} from 'expo-crypto';
import {SymptomReport, SymptomResponse} from '@/types';
import {mmkv} from './storage';
import {
  PatientSession,
  assertPatientSession,
  isPatientSessionCurrent,
} from './patientSession';
import {apiClient} from '@/services/api';
import {useRiskStore} from '@/store/riskStore';

interface QueuedReport extends SymptomReport {
  id: string;
  queued_at: string;
}

const legacyStorage = new MMKV({
  id: 'offline-queue',
  encryptionKey: 'offline-encryption-key',
});
const flushes = new Map<string, {session: PatientSession; promise: Promise<number>}>();
const listeners = new Set<() => void>();
let queueRevision = 0;

export function subscribeQueueChanges(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function getQueueRevision(): number {
  return queueRevision;
}

function queueChanged(): void {
  ++queueRevision;
  for (const listener of listeners) listener();
}

function isQueuedReport(value: unknown): value is QueuedReport {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<QueuedReport>;
  return (
    typeof item.patient_id === 'string' &&
    /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(item.patient_id) &&
    typeof item.id === 'string' &&
    /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(item.id) &&
    typeof item.queued_at === 'string' &&
    Number.isFinite(Date.parse(item.queued_at)) &&
    Array.isArray(item.symptoms) &&
    item.symptoms.every(symptom => typeof symptom === 'string')
  );
}

function readQueue(patientId: string): QueuedReport[] {
  const raw = mmkv.getString(`offline_queue:${patientId}`);
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error('Pending reports could not be read safely. No reports were removed.');
  }
  if (
    !Array.isArray(parsed) ||
    !parsed.every(item => isQueuedReport(item) && item.patient_id === patientId)
  ) {
    throw new Error('Pending reports could not be read safely. No reports were removed.');
  }
  const ids = new Set<string>();
  return parsed.filter(item => {
    if (ids.has(item.id)) return false;
    ids.add(item.id);
    return true;
  });
}

// Synchronous all the way through commit: no flush may start until every
// destination and the remaining legacy source have been written successfully.
export function migrateLegacySymptomQueue(): void {
  const raw = legacyStorage.getString('offline_queue');
  if (!raw) return;
  let entries: unknown;
  try {
    entries = JSON.parse(raw);
  } catch {
    throw new Error('Legacy pending reports could not be read. No reports were removed.');
  }
  if (!Array.isArray(entries)) {
    throw new Error('Legacy pending reports have an unknown format. No reports were removed.');
  }
  const groups = new Map<string, QueuedReport[]>();
  const remaining: unknown[] = [];
  for (const item of entries) {
    if (!isQueuedReport(item)) {
      remaining.push(item); // Unowned/malformed records remain quarantined.
      continue;
    }
    const group = groups.get(item.patient_id) || [];
    if (!group.some(existing => existing.id === item.id)) group.push(item);
    groups.set(item.patient_id, group);
  }
  if (!groups.size && remaining.length) return;
  try {
    for (const [owner, items] of groups) {
      const existing = readQueue(owner);
      const ids = new Set(existing.map(item => item.id));
      mmkv.set(`offline_queue:${owner}`, JSON.stringify([
        ...existing, ...items.filter(item => !ids.has(item.id)),
      ]));
    }
    // Write remaining legacy data before deletion, including the empty case.
    // A failed write leaves the original source retryable and destination IDs
    // are deduplicated on retry, before anything is allowed onto the network.
    legacyStorage.set('offline_queue', JSON.stringify(remaining));
    if (!remaining.length) legacyStorage.delete('offline_queue');
  } catch {
    throw new Error('Pending report migration failed. Reports were retained; sync has not started.');
  }
  queueChanged();
}

export function queueSymptomReport(report: SymptomReport, session: PatientSession): void {
  assertPatientSession(session);
  if (!session.patientId || report.patient_id !== session.patientId) {
    throw new Error('Cannot save a report without a matching signed-in patient.');
  }
  migrateLegacySymptomQueue();
  const queue = readQueue(session.patientId);
  const queued: QueuedReport = {
    ...report, id: randomUUID(), queued_at: new Date().toISOString(),
  };
  if (!isQueuedReport(queued)) throw new Error('The pending report has an invalid owner or ID.');
  if (queue.some(item => item.id === queued.id)) {
    throw new Error('A unique pending report ID could not be created. The report was not saved.');
  }
  queue.push(queued);
  // Do not report an offline save until this synchronous write succeeds.
  try {
    mmkv.set(`offline_queue:${session.patientId}`, JSON.stringify(queue));
  } catch {
    throw new Error('The report could not be saved on this device. No offline save was confirmed.');
  }
  queueChanged();
}

export function getPendingReportCount(session: PatientSession): number {
  if (!session.patientId || !isPatientSessionCurrent(session)) return 0;
  return readQueue(session.patientId).length;
}

export function applySymptomRisk(data: SymptomResponse, session: PatientSession): void {
  assertPatientSession(session);
  if (!session.patientId || data.patient_id !== session.patientId) {
    throw new Error('The report response did not match the signed-in patient.');
  }
  const risk = useRiskStore.getState();
  if (data.risk_score !== null && data.risk_tier) {
    risk.setRiskScore(session.patientId, data.risk_score, data.risk_tier);
  } else {
    risk.setInsufficientData(session.patientId,
      data.message || 'Insufficient data: Need at least 3 symptom reports');
  }
}

export function flushSymptomQueue(session: PatientSession): Promise<number> {
  assertPatientSession(session);
  if (!session.patientId) return Promise.resolve(0);
  const patientId = session.patientId;
  const existing = flushes.get(patientId);
  if (existing) {
    if (isPatientSessionCurrent(existing.session)) return existing.promise;
    // A return to the same patient waits for the old session's request to
    // settle rather than starting a parallel replay under new credentials.
    return existing.promise.then(
      () => flushSymptomQueue(session),
      () => flushSymptomQueue(session),
    );
  }
  const promise = (async () => {
    migrateLegacySymptomQueue();
    const pending = readQueue(patientId);
    let synced = 0;
    for (const queued of pending) {
      assertPatientSession(session);
      const {id, queued_at, ...report} = queued;
      const response = await apiClient.post<SymptomResponse>('/symptoms', report, {
        patientSession: session,
      });
      assertPatientSession(session);
      if (response.data.patient_id !== patientId) {
        throw new Error('The synced report response did not match the signed-in patient.');
      }
      // Read AFTER the acknowledgement. Appends while HTTP was in flight must
      // survive. A storage failure leaves the item pending and propagates.
      const latest = readQueue(patientId);
      try {
        mmkv.set(`offline_queue:${patientId}`, JSON.stringify(latest.filter(item => item.id !== id)));
      } catch {
        throw new Error('The server accepted a pending report but its local acknowledgement could not be saved. It remains pending and may be sent again.');
      }
      queueChanged();
      ++synced;
      applySymptomRisk(response.data, session);
    }
    return synced;
  })().finally(() => {
    if (flushes.get(patientId)?.promise === promise) flushes.delete(patientId);
  });
  flushes.set(patientId, {session, promise});
  // HTTP acceptance followed by a lost connection/failed local acknowledgement
  // is inherently at-least-once: the existing backend has no idempotency API.
  return promise;
}
