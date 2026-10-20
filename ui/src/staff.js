import { socketUrl } from "./api";

/** Re-run `onChange` whenever the doctor's queue changes (staff may follow any session). */
export function followSession(sessionId, onChange) {
  let ws = null;
  try {
    ws = new WebSocket(socketUrl(sessionId));
    ws.onmessage = () => onChange();
  } catch {
    /* the page still refreshes after each action */
  }
  return () => ws?.close();
}
