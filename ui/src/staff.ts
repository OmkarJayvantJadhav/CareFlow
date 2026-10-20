import { socketUrl } from "./api";

export interface Booking {
  appointment_id: number;
  time: string;
  patient_name: string;
  status: string;
  entry_id: number | null;
  token: string | null;
  entry_status: string | null;
}

export interface DutyDoctor {
  doctor_id: number;
  doctor_name: string;
  department: string;
  session_id: number | null;
  session_status: string | null;
  doctor_status: string;
  delay_minutes: number;
  bookings: Booking[];
}

export interface Entry {
  entry_id: number;
  token: string;
  kind: string;
  status: string;
  position: number | null;
  priority: number;
  patient_name: string;
  estimate: { display: string } | null;
}

/** Re-run `onChange` whenever the doctor's queue changes (staff may follow any session). */
export function followSession(sessionId: number, onChange: () => void): () => void {
  let ws: WebSocket | null = null;
  try {
    ws = new WebSocket(socketUrl(sessionId));
    ws.onmessage = () => onChange();
  } catch {
    /* the page still refreshes after each action */
  }
  return () => ws?.close();
}
