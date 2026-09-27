// Small client for the local Sentinel backend.
// The port and the per-boot session token come from the Electron preload bridge.
// The token always travels in a header, never in a URL (URLs end up in logs).
type Bridge = { auth?: { getSessionToken(): Promise<string>; getBackendPort(): Promise<number> } };

export async function backendInfo(): Promise<{ port: number; token: string }> {
  const bridge = (window as unknown as { sentinel?: Bridge }).sentinel;
  if (bridge?.auth) {
    const [port, token] = await Promise.all([bridge.auth.getBackendPort(), bridge.auth.getSessionToken()]);
    return { port: Number(port) || 8000, token: token ?? '' };
  }
  return { port: 8000, token: 'dev_fallback_token' }; // browser dev mode without Electron
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const { port, token } = await backendInfo();
  const headers: Record<string, string> = { 'X-Sentinel-Session': token };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} failed: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return call<T>('GET', path);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return call<T>('POST', path, body);
}

// Shapes returned by the backend
export type GpuSnapshot = {
  available: boolean; name: string | null; source: string;
  vram_used_mb: number | null; vram_total_mb: number | null; vram_percent: number | null;
  util_percent: number | null; temp_c: number | null;
};
export type GovernorStatus = {
  state: string; cpu_percent: number; ram_percent: number;
  ram_used_gb?: number; ram_total_gb?: number; manual_override: boolean; gpu?: GpuSnapshot;
};
export type EgressEvent = {
  ts: string; tool: string | null; method: string; host: string;
  decision: 'allowed' | 'blocked'; reason: string; status?: number; bytes_in?: number; ms?: number;
};
export type EgressStatus = {
  offline: boolean; allowed_total: number; blocked_total: number; last: EgressEvent | null; allowlist: string[];
};

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return `${Math.round(s)} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}
