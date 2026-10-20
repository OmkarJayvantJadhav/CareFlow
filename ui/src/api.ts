// Thin client for the CareFlow API (same origin). Errors carry the server's code so screens can
// show a plain-language message (docs §8: never show codes).

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

let token: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(value: string | null) {
  token = value;
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError("NETWORK", "network error", 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = (data && data.error) || {};
    if (response.status === 401 && onUnauthorized) onUnauthorized();
    throw new ApiError(error.code || `HTTP_${response.status}`, error.message || response.statusText, response.status);
  }
  return data as T;
}

export function socketUrl(sessionId: number): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/queue/${sessionId}?token=${encodeURIComponent(token ?? "")}`;
}

// ---------------------------------------------------------------- response types

export type Role = "patient" | "caregiver" | "staff" | "admin";

export interface User {
  user_id: number;
  username: string;
  display_name: string;
  role: Role;
  patient_id: number | null;
  patients: { patient_id: number; name: string }[];
}

export interface Citation {
  ref: number;
  title: string;
  section: string;
  collection: string;
  language: string;
  source_path: string;
  last_verified: string;
}

export interface Confirmation {
  action_id: string;
  tool: string;
  summary: Record<string, string>;
  expires_at: string;
  expires_in_seconds: number;
}

export interface ChatReply {
  conversation_id: string;
  reply: string;
  language: string;
  citations: Citation[];
  actions: { tool: string; ok: boolean; label: string; error?: string }[];
  needs_confirmation: boolean;
  confirmation: Confirmation | null;
  handoff: boolean;
  ticket_id: number | null;
  emergency: boolean;
  offer_handoff: boolean;
}

export interface Appointment {
  appointment_id: number;
  patient_name: string;
  doctor_name: string;
  department: string;
  date: string;
  time: string;
  status: string;
}

export interface Estimate {
  predicted_min: number;
  low_min: number;
  high_min: number;
  display: string;
}

export interface QueueStatus {
  entry_id: number;
  session_id: number;
  token: string;
  status: string;
  position: number | null;
  ahead: number | null;
  estimate: Estimate | null;
  doctor_name: string;
  doctor_status: string;
  delay_minutes: number;
  patient_name?: string;
}
