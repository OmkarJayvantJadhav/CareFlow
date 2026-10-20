import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { api, type ChatReply, type Citation, type Confirmation } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import type { Key, Lang } from "../i18n";
import { useSession } from "../session";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  steps?: string[];
  confirmation?: Confirmation | null;
  offerHandoff?: boolean;
}

const NO: Record<Lang, string> = { en: "No, I want to change it.", hi: "नहीं, मुझे बदलना है।", mr: "नाही, मला बदलायचे आहे." };
const PERSON: Record<Lang, string> = {
  en: "I want to talk to a person.",
  hi: "मुझे किसी इंसान से बात करनी है।",
  mr: "मला माणसाशी बोलायचे आहे.",
};
const SUMMARY_LABELS: [string, Key][] = [
  ["patient", "patientLabel"],
  ["doctor", "doctorLabel"],
  ["date", "dateLabel"],
  ["time", "timeLabel"],
  ["dates", "datesLabel"],
];

/** Assistant text with **bold** shown as bold; everything else as plain text (never HTML). */
function formatted(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

function AssistantText({ text }: { text: string }) {
  const { t } = useSession();
  const long = text.split("\n").length > 6 || text.length > 480;
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className={long && !open ? "collapsed" : undefined}>{formatted(text)}</div>
      {long && (
        <button type="button" className="link-button" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? t("showLess") : t("showMore")}
        </button>
      )}
    </>
  );
}

function Sources({ citations }: { citations: Citation[] }) {
  const { t } = useSession();
  const [shown, setShown] = useState<number | null>(null);
  const detail = citations.find((c) => c.ref === shown);
  return (
    <div>
      <ul className="chips" aria-label={t("sources")}>
        {citations.map((c) => (
          <li key={c.ref}>
            <button
              type="button"
              className="chip"
              aria-expanded={shown === c.ref}
              onClick={() => setShown(shown === c.ref ? null : c.ref)}
            >
              [{c.ref}] {c.title} — {c.section}
            </button>
          </li>
        ))}
      </ul>
      {detail && (
        <div className="source-detail">
          {detail.collection} · {detail.language} · {t("verified")} {detail.last_verified} · {detail.source_path}
        </div>
      )}
    </div>
  );
}

function ConfirmCard({
  card,
  busy,
  onConfirm,
  onChange,
}: {
  card: Confirmation;
  busy: boolean;
  onConfirm: () => void;
  onChange: () => void;
}) {
  const { t } = useSession();
  // Count down from when the card arrived, using the server's remaining time (not the device clock).
  const [deadline] = useState(() => Date.now() + card.expires_in_seconds * 1000);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15000);
    return () => window.clearInterval(timer);
  }, []);
  const msLeft = deadline - now;
  const expired = msLeft <= 0;
  const s = card.summary;
  return (
    <section className="confirm-card" aria-label={t("confirmTitle")}>
      <h3>{t("confirmTitle")}</h3>
      <dl>
        {s.old_doctor && (
          <>
            <dt>{t("fromLabel")}</dt>
            <dd>
              {s.old_doctor}, {s.old_date} {s.old_time}
            </dd>
          </>
        )}
        {SUMMARY_LABELS.filter(([key]) => s[key]).map(([key, label]) => (
          <div key={key} style={{ display: "contents" }}>
            <dt>{t(label)}</dt>
            <dd>{key === "doctor" && s.department ? `${s.doctor} (${s.department})` : s[key]}</dd>
          </div>
        ))}
        {s.cancellation_policy && (
          <>
            <dt>{t("policyLabel")}</dt>
            <dd style={{ fontWeight: 400 }}>{s.cancellation_policy}</dd>
          </>
        )}
      </dl>
      <p className="muted" aria-live="polite">
        {expired ? t("cardExpired") : t("cardExpires", { minutes: Math.max(1, Math.ceil(msLeft / 60000)) })}
      </p>
      <div className="row">
        <button type="button" onClick={onConfirm} disabled={busy || expired}>
          {t("confirm")}
        </button>
        <button type="button" className="secondary" onClick={onChange} disabled={busy}>
          {t("change")}
        </button>
      </div>
    </section>
  );
}

function EmergencyPanel({ onBack }: { onBack: () => void }) {
  const { t } = useSession();
  return (
    <section className="emergency" role="alert" aria-live="assertive">
      <h2>{t("emergencyTitle")}</h2>
      <a className="call" href="tel:112">
        {t("emergencyCall")}
      </a>
      <p>{t("emergencyBody")}</p>
      <button type="button" className="quiet" onClick={onBack}>
        {t("emergencyBack")}
      </button>
    </section>
  );
}

/** S2 patient chat, with the S5 emergency panel taking over when an emergency is detected. */
export default function Chat() {
  const { t, lang } = useSession();
  const location = useLocation();
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>(() => (location.state as { prefill?: string } | null)?.prefill ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [emergency, setEmergency] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, busy]);

  async function exchange(body: { message?: string; confirm_action_id?: string }, shown?: string) {
    setBusy(true);
    setError(null);
    if (shown) setMessages((m) => [...m, { id: nextId.current++, role: "user", text: shown }]);
    try {
      const reply = await api<ChatReply>("/chat", {
        method: "POST",
        body: { ...body, conversation_id: conversationId, language: lang },
      });
      setConversationId(reply.conversation_id);
      // A new reply replaces any earlier card: only the latest card can be confirmed.
      setMessages((m) => [
        ...m.map((msg) => ({ ...msg, confirmation: null })),
        {
          id: nextId.current++,
          role: "assistant",
          text: reply.reply,
          citations: reply.citations,
          steps: reply.actions.map((a) => a.label),
          confirmation: reply.confirmation,
          offerHandoff: reply.offer_handoff,
        },
      ]);
      if (reply.emergency) setEmergency(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    void exchange({ message }, message);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  if (emergency) {
    return (
      <main className="narrow">
        <EmergencyPanel onBack={() => setEmergency(false)} />
      </main>
    );
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  return (
    <main className="narrow">
      <h1>{t("chatTitle")}</h1>
      <p className="lead">{t("chatIntro")}</p>
      <div className="chat">
        <div className="messages" aria-live="polite" aria-relevant="additions">
          {messages.length === 0 && (
            <div className="card">
              <p style={{ marginTop: 0 }}>{t("suggestions")}</p>
              <div className="row">
                {(["suggestBook", "suggestFast", "suggestWait"] as Key[]).map((k) => (
                  <button key={k} type="button" className="secondary" onClick={() => send(t(k))}>
                    {t(k)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} style={{ display: "contents" }}>
              <div className={`msg ${m.role}`}>
                {m.role === "assistant" ? <AssistantText text={m.text} /> : m.text}
                {m.steps && m.steps.length > 0 && (
                  <div className="steps">
                    {m.steps.map((s, i) => (
                      <span key={i} className="pill">
                        ✓ {s}
                      </span>
                    ))}
                  </div>
                )}
                {m.citations && m.citations.length > 0 && <Sources citations={m.citations} />}
              </div>
              {m.confirmation && (
                <ConfirmCard
                  card={m.confirmation}
                  busy={busy}
                  onConfirm={() => void exchange({ confirm_action_id: m.confirmation!.action_id }, t("confirm"))}
                  onChange={() => {
                    void exchange({ message: NO[lang] }, NO[lang]);
                    inputRef.current?.focus();
                  }}
                />
              )}
            </div>
          ))}
          {busy && (
            <div className="msg assistant typing" role="status">
              {t("working")}
            </div>
          )}
          {error !== null && <ErrorMessage error={error} />}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={onSubmit}>
          <label htmlFor="chat-input" className="sr-only">
            {t("chatPlaceholder")}
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            rows={1}
            value={draft}
            maxLength={1000}
            placeholder={t("chatPlaceholder")}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
          />
          <button type="submit" disabled={busy || !draft.trim()}>
            {t("send")}
          </button>
        </form>
        <div>
          <button
            type="button"
            className={lastAssistant?.offerHandoff ? undefined : "secondary"}
            disabled={busy}
            onClick={() => send(PERSON[lang])}
          >
            {t("talkToPerson")}
          </button>
        </div>
      </div>
    </main>
  );
}
