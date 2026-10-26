// Thin client for the CareFlow API (same origin). Errors carry the server's code so screens can
// show a plain-language message (docs §8: never show codes).

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

let token = null;
let onUnauthorized = null;

export function setToken(value) {
  token = value;
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export async function api(path, options = {}) {
  const headers = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
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
    // The session has ended (not a wrong password typed into a form, which is also a 401).
    if (response.status === 401 && error.code !== "INVALID_CREDENTIALS" && onUnauthorized) onUnauthorized();
    throw new ApiError(error.code || `HTTP_${response.status}`, error.message || response.statusText, response.status);
  }
  return data;
}

export function socketUrl(sessionId) {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/queue/${sessionId}?token=${encodeURIComponent(token ?? "")}`;
}
