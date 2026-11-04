# WebSockets

## 30-second answer
A WebSocket is a **persistent, full-duplex connection** between browser and server over one TCP connection, opened by an HTTP "upgrade" handshake. Unlike REST (client asks, server answers), the server can **push** messages at any time. CareFlow uses WebSockets for **real-time queues**: when the front desk checks someone in or the doctor calls the next patient, every patient watching that doctor's queue gets the new positions, wait estimates and doctor status **in under 2 seconds** (an end-to-end Playwright test checks this). If the socket fails, the page falls back to **polling every 5 seconds**.

---

## Basics you must know

### Handshake
```
GET /ws/queue/42?token=... HTTP/1.1
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
→ HTTP/1.1 101 Switching Protocols
```
After that, both sides send **frames** (text, binary, ping/pong, close). `ws://` is plain, `wss://` is over TLS.

### Compared with alternatives
| Technique | Direction | Notes |
|---|---|---|
| Polling | Client asks every N s | Simple, wasteful, delayed |
| Long polling | Server holds request until data | Better, still request-per-update |
| **Server-Sent Events (SSE)** | Server → client only | Simple, over HTTP, auto-reconnect |
| **WebSocket** | Both ways | Lowest latency, needs connection management |

### Things to handle
- **Authentication** — browsers can't set custom headers on `new WebSocket()`, so pass a token in the query string (or a cookie) and verify it before `accept()`.
- **Authorisation** per channel (who may watch which queue).
- **Close codes** — 1000 normal, 1001 going away, 4000–4999 application-defined.
- **Reconnection and fallback** on the client.
- **Back-pressure** — slow clients must not block others.
- **Scaling** — connections live in one process; with several servers you need a shared pub/sub (Redis, Postgres LISTEN/NOTIFY).

---

## How I built it in CareFlow

### Endpoint (`app/api/queue_routes.py`)
```python
@ws_router.websocket("/ws/queue/{session_id}")
async def queue_socket(websocket: WebSocket, session_id: int, token: str = "") -> None:
    with session_factory()() as db:
        try:
            actor, _, _ = verify_token(db, token)
        except ToolError:
            await websocket.close(code=4401); return          # not signed in
        allowed = (actor.role in ("staff", "admin")
                   or (actor.role == "doctor" and actor.doctor_id == session.doctor_id)
                   or any(can_manage_patient(db, actor, e.patient_id) for e in entries))
        if not allowed:
            await websocket.close(code=4403); return          # not allowed
        initial = session_messages(db, session_id, now_ist())
    await websocket.accept()
    queue = broadcaster.subscribe(session_id)

    async def pump():                                         # server → client
        while True:
            await websocket.send_json(await queue.get())
    async def listen():                                       # only to notice disconnects
        while True:
            await websocket.receive_text()

    try:
        for m in initial: await websocket.send_json(m)        # current state first
        done, pending = await asyncio.wait([create_task(pump()), create_task(listen())],
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending: t.cancel()
    finally:
        broadcaster.unsubscribe(session_id, queue)
```
- Patients may follow a queue they are in (or a family member's, as caregiver); doctors only their own; staff/admins any.
- Custom close codes **4401** / **4403** mirror HTTP 401 / 403.

### Broadcaster (`app/queue/broadcast.py`) — bridging threads and asyncio
REST route handlers are sync `def` functions running in a **thread pool**, but WebSocket subscribers live on the **event loop**. Publishing must cross that boundary safely:
```python
def subscribe(self, session_id):
    queue = asyncio.Queue(maxsize=100)
    with self._lock:
        self._subscribers[session_id].add((asyncio.get_running_loop(), queue))
    return queue

def publish(self, session_id, messages):
    for loop, queue in list(self._subscribers[session_id]):
        for message in messages:
            loop.call_soon_threadsafe(_offer, queue, message)   # thread → event loop, safely

def _offer(queue, message):
    if queue.full():
        queue.get_nowait()     # a slow client gets the NEWEST state, not a growing backlog
    queue.put_nowait(message)
```

### Messages (`session_messages`)
Three events per change — and **tokens only, never patient names**:
```json
{"event": "queue.updated",      "session_id": 42, "at": "...", "entries": [{"entry_id": 1, "token": "A03", "kind": "booked", "position": 1, "status": "waiting"}]}
{"event": "prediction.updated", "session_id": 42, "at": "...", "predictions": [{"entry_id": 1, "predicted_min": 35, "low_min": 25, "high_min": 50}]}
{"event": "doctor.status",      "session_id": 42, "at": "...", "status": "delayed", "delay_minutes": 20, "busy_until": "..."}
```
Every queue action (check in, call, start, end, missed, move, break) is written to the database, wait estimates are recomputed with the LightGBM model, and then published (`_write_and_publish`).

### Client (`ui/src/pages/QueueStatus.jsx`, `ui/src/api.js`)
```js
const scheme = window.location.protocol === "https:" ? "wss" : "ws";
const ws = new WebSocket(`${scheme}://${window.location.host}/ws/queue/${sessionId}?token=${encodeURIComponent(token)}`);
ws.onopen    = () => { setLive(true); stop polling };
ws.onmessage = () => void refresh();        // re-fetch the full state via REST
ws.onerror   = () => startPolling();         // every 5 s
ws.onclose   = () => { if (!closed) startPolling(); };
// useEffect cleanup: close socket, clear interval
```
The Vite dev server proxies `/ws` to the API (`ws: true`).

### Tests
- **TC-20** (`tests/e2e/test_ui.py::test_tc20_queue_page_updates_within_two_seconds`): a staff action via the API must appear on the patient's queue page within 2 seconds.

### Known limitation (in the README)
The broadcaster is in one process; running several servers would need a shared message bus (e.g. Redis pub/sub or PostgreSQL LISTEN/NOTIFY).

---

## Interview questions

**Q: Why WebSockets and not polling?**
Updates must arrive within ~2 s for everyone watching a queue; polling every second from many phones wastes battery and server work. Polling stays as a fallback.

**Q: How do you authenticate a WebSocket?**
Browsers can't add an Authorization header to `new WebSocket`, so the bearer token goes in the query string over `wss://`; it's verified (and permissions checked) before `accept()`, closing with 4401/4403 otherwise.

**Q: How did you push from synchronous code to async WebSockets?**
Each subscriber stores its event loop; `publish` uses `loop.call_soon_threadsafe` to put the message on the subscriber's `asyncio.Queue` from the request thread.

**Q: What if a client is slow?**
Each subscriber has a bounded queue of 100; when full, the oldest message is dropped — the client always gets the latest state instead of a backlog.

**Q: How would you scale to multiple servers?**
Publish events to Redis pub/sub or PostgreSQL `LISTEN/NOTIFY` and have each server forward them to its own sockets; use sticky sessions or a dedicated realtime service.

**Q: Why does the client re-fetch over REST on each message?**
Simplicity and correctness: REST returns the patient's full, permission-checked view (including their own name), while socket messages stay anonymous (tokens only).
