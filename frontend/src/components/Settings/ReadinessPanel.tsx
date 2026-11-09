import React, { useEffect, useState, useRef } from 'react';
import { apiGet, ApiError } from '../../lib/backend';
import './ReadinessPanel.css';

export type ReadinessCheckState = 'ready' | 'setup_required' | 'unavailable' | 'unknown';

export interface ReadinessCheck {
  id: string;
  label: string;
  state: ReadinessCheckState;
  detail: string;
}

export interface ReadinessResponse {
  version: number;
  checks: ReadinessCheck[];
}

export const KNOWN_CHECK_IDS = new Set<string>([
  'chat',
  'dictation',
  'speech',
  'document_search',
  'google',
  'backup',
]);

export const VALID_STATES = new Set<ReadinessCheckState>([
  'ready',
  'setup_required',
  'unavailable',
  'unknown',
]);

const STATE_LABELS: Record<ReadinessCheckState, string> = {
  ready: 'Ready',
  setup_required: 'Setup required',
  unavailable: 'Unavailable',
  unknown: 'Unknown',
};

// Guidance pointing to existing controls without duplicating them
const CONTROL_HINTS: Record<string, string> = {
  chat: 'Model profiles can be inspected and selected in Model Selection below.',
  dictation: 'Microphone dictation can be enabled or disabled in the Chat screen.',
  speech: 'Voice selection and speech speed controls are in Voice settings below.',
  document_search: 'Document preparation and meaning search are managed in Workspace → Documents.',
  google: 'OAuth credentials and read-only connection are in Gmail and Google Calendar below.',
  backup: 'Encrypted backup creation and restore verification are in Encrypted backup below.',
};

/**
 * Strict validator for READINESS_API.md version 1.
 * Rejects oversized arrays (> 6 items), duplicate IDs, unknown IDs,
 * empty or non-string label/detail, and unrecognized states.
 * Returns null if valid, or a descriptive error string if invalid.
 */
export function validateReadinessResponse(data: unknown): string | null {
  if (!data || typeof data !== 'object') {
    return 'Response must be an object.';
  }
  const obj = data as Record<string, unknown>;
  if (obj.version !== 1) {
    return 'Unsupported readiness contract version (expected version 1).';
  }
  if (!Array.isArray(obj.checks)) {
    return 'Checks property must be an array.';
  }
  if (obj.checks.length > 6) {
    return `Checks array exceeds maximum allowed length of 6 (received ${obj.checks.length}).`;
  }

  const seenIds = new Set<string>();
  for (let i = 0; i < obj.checks.length; i++) {
    const item = obj.checks[i];
    if (!item || typeof item !== 'object') {
      return `Check item at index ${i} is not a valid object.`;
    }
    const check = item as Record<string, unknown>;
    if (typeof check.id !== 'string' || !KNOWN_CHECK_IDS.has(check.id)) {
      return `Check item at index ${i} has unknown or invalid ID: "${String(check.id)}".`;
    }
    if (seenIds.has(check.id)) {
      return `Duplicate check ID found in response: "${check.id}".`;
    }
    seenIds.add(check.id);

    if (typeof check.label !== 'string' || check.label.trim().length === 0 || check.label.length > 80) {
      return `Check "${check.id}" has an invalid label (must be non-empty string <= 80 characters).`;
    }
    if (typeof check.detail !== 'string' || check.detail.trim().length === 0 || check.detail.length > 400) {
      return `Check "${check.id}" has an invalid detail (must be non-empty string <= 400 characters).`;
    }
    if (typeof check.state !== 'string' || !VALID_STATES.has(check.state as ReadinessCheckState)) {
      return `Check "${check.id}" has an invalid state: "${String(check.state)}".`;
    }
  }

  return null;
}

const ReadinessPanel: React.FC = () => {
  const [checks, setChecks] = useState<ReadinessCheck[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Generation counter to guard against race conditions, out-of-order resolution, and StrictMode replay
  const requestIdRef = useRef(0);

  useEffect(() => {
    return () => {
      // Invalidate any in-flight requests when unmounting or StrictMode replaying
      requestIdRef.current += 1;
    };
  }, []);

  const fetchReadiness = async () => {
    const currentRequestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    try {
      const data = await apiGet<ReadinessResponse>('/api/workspace/readiness');
      // If a newer request was dispatched or the component unmounted, drop this response
      if (requestIdRef.current !== currentRequestId) return;

      const validationError = validateReadinessResponse(data);
      if (validationError) {
        setChecks(null);
        setError(`Invalid readiness data: ${validationError}`);
        return;
      }

      setChecks(data.checks);
    } catch (err: unknown) {
      if (requestIdRef.current !== currentRequestId) return;

      // Discard previous checks on failure so stale green badges are never presented as current
      setChecks(null);

      if (err instanceof ApiError) {
        if (err.status === 404) {
          setError('Readiness endpoint is not integrated yet in the local backend (expected during integration).');
        } else if (err.status === 423) {
          setError('Sentinel is locked. Unlock Sentinel with your PIN to view component readiness.');
        } else if (err.status === 401) {
          setError('Session token is invalid or expired. Please re-authenticate.');
        } else {
          setError(`Readiness check failed (HTTP ${err.status}).`);
        }
      } else if (err instanceof Error) {
        setError(`Could not connect to backend: ${err.message}`);
      } else {
        setError('Could not connect to the local backend.');
      }
    } finally {
      if (requestIdRef.current === currentRequestId) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void fetchReadiness();
  }, []);

  return (
    <div className="settings-section readiness-panel">
      <div className="readiness-header">
        <h3>Component Readiness</h3>
        <button
          type="button"
          className="readiness-refresh-btn"
          disabled={loading}
          onClick={() => void fetchReadiness()}
          aria-label="Refresh component readiness status"
        >
          {loading ? 'Checking…' : 'Refresh status'}
        </button>
      </div>

      <p className="settings-desc">
        Local status of Sentinel capabilities. Status indicates local component initialization and does not certify remote services or full clean-machine verification.
      </p>

      {loading && (
        <div className="readiness-message info" role="status" aria-live="polite">
          Checking component readiness…
        </div>
      )}

      {error && (
        <div className="readiness-message warning" role="alert">
          {error}
        </div>
      )}

      {!loading && !error && checks && checks.length === 0 && (
        <p className="settings-desc">No readiness checks reported by the backend.</p>
      )}

      {!loading && checks && checks.length > 0 && (
        <div className="readiness-grid">
          {checks.map(check => {
            const hint = CONTROL_HINTS[check.id];
            return (
              <div key={check.id} className="readiness-card">
                <div className="readiness-card-top">
                  <span className="readiness-label">{check.label}</span>
                  <span className={`readiness-badge badge-${check.state}`}>
                    {STATE_LABELS[check.state]}
                  </span>
                </div>
                <p className="readiness-detail">{check.detail}</p>
                {hint && <span className="readiness-link-hint">{hint}</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ReadinessPanel;
