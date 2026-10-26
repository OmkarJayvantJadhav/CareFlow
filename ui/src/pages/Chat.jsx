import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CalendarCheck,
  CalendarDays,
  CalendarPlus,
  CalendarRange,
  Check,
  Clock,
  FileText,
  FlaskConical,
  Headset,
  History,
  Hourglass,
  MapPin,
  Phone,
  SendHorizontal,
  ShieldCheck,
  Ticket,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import { initials } from "../format";
import { useSession } from "../session";

const NO = { en: "No, I want to change it.", hi: "नहीं, मुझे बदलना है।", mr: "नाही, मला बदलायचे आहे." };
const PERSON = {
  en: "I want to talk to a person.",
  hi: "मुझे किसी इंसान से बात करनी है।",
  mr: "मला माणसाशी बोलायचे आहे.",
};
const SUMMARY_ROWS = [
  ["patient", "patientLabel", UserRound],
  ["date", "dateLabel", CalendarDays],
  ["time", "timeLabel", Clock],
  ["dates", "datesLabel", CalendarRange],
  ["token", "token", Ticket],
  ["floor", "floorLabel", MapPin],
  ["people_ahead", "peopleAhead", UsersRound],
];
const SUGGESTIONS = [
  ["suggestBook", CalendarPlus],
  ["suggestFast", FlaskConical],
  ["suggestWait", Hourglass],
  ["suggestTimings", Clock],
];

/** Assistant text with **bold** shown as bold; everything else as plain text (never HTML). */
function formatted(text) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
    );
}

function AssistantText({ text }) {
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

function Sources({ citations }) {
  const { t } = useSession();
  const [shown, setShown] = useState(null);
  const detail = citations.find((c) => c.ref === shown);
  return (
    <div className="sources">
      <span className="sources-label" aria-hidden="true">
        {t("sources")}
      </span>
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
          <FileText size={16} aria-hidden="true" />
          <span>
            {detail.collection} · {detail.language} · {t("verified")} {detail.last_verified} · {detail.source_path}
          </span>
        </div>
      )}
    </div>
  );
}

function ConfirmCard({ card, busy, onConfirm, onChange }) {
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
      <div className="confirm-head">
        <CalendarCheck size={18} aria-hidden="true" />
        <h3>{t("confirmTitle")}</h3>
      </div>
      <div className="confirm-body">
        {s.doctor && (
          <div className="doctor">
            <span className="avatar" aria-hidden="true">
              {initials(s.doctor)}
            </span>
            <div>
              <div className="muted small">{t("doctorLabel")}</div>
              <strong>{s.department ? `${s.doctor} (${s.department})` : s.doctor}</strong>
            </div>
          </div>
        )}
        <dl>
          {s.old_doctor && (
            <>
              <dt>
                <History size={16} aria-hidden="true" />
                {t("fromLabel")}
              </dt>
              <dd>
                {s.old_doctor}, {s.old_date} {s.old_time}
              </dd>
            </>
          )}
          {SUMMARY_ROWS.filter(([key]) => s[key]).map(([key, label, Icon]) => (
            <div key={key} style={{ display: "contents" }}>
              <dt>
                <Icon size={16} aria-hidden="true" />
                {t(label)}
              </dt>
              <dd>{s[key]}</dd>
            </div>
          ))}
          {s.cancellation_policy && (
            <>
              <dt>
                <ShieldCheck size={16} aria-hidden="true" />
                {t("policyLabel")}
              </dt>
              <dd style={{ fontWeight: 400 }}>{s.cancellation_policy}</dd>
            </>
          )}
        </dl>
        <p className="expiry" aria-live="polite">
          <Clock size={14} aria-hidden="true" />
          {expired ? t("cardExpired") : t("cardExpires", { minutes: Math.max(1, Math.ceil(msLeft / 60000)) })}
        </p>
        <div className="actions">
          <button type="button" onClick={onConfirm} disabled={busy || expired}>
            <Check size={18} aria-hidden="true" />
            {t("confirm")}
          </button>
          <button type="button" className="secondary" onClick={onChange} disabled={busy}>
            {t("change")}
          </button>
        </div>
      </div>
    </section>
  );
}

function EmergencyPanel({ onBack }) {
  const { t } = useSession();
  return (
    <section className="emergency" role="alert" aria-live="assertive">
      <div className="em-head">
        <AlertTriangle size={28} aria-hidden="true" />
        <h2>{t("emergencyTitle")}</h2>
      </div>
      <div className="em-body">
        <a className="call" href="tel:112">
          <Phone size={24} aria-hidden="true" />
          {t("emergencyCall")}
        </a>
        <div className="where">
          <MapPin size={20} aria-hidden="true" />
          <div>
            <strong>{t("emergencyWhere")}</strong>
            <p>{t("emergencyBody")}</p>
          </div>
        </div>
        <div>
          <button type="button" className="quiet" onClick={onBack}>
            <ArrowLeft size={18} aria-hidden="true" />
            {t("emergencyBack")}
          </button>
        </div>
      </div>
    </section>
  );
}

function AssistantAvatar() {
  return (
    <span className="avatar" aria-hidden="true">
      <Bot size={18} />
    </span>
  );
}

/** S2 patient chat, with the S5 emergency panel taking over when an emergency is detected. */
export default function Chat() {
  const { t, lang, user } = useSession();
  const location = useLocation();
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [draft, setDraft] = useState(() => location.state?.prefill ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [emergency, setEmergency] = useState(false);
  const nextId = useRef(1);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  // Follow the conversation, but leave the page where it is before anything has been said.
  useEffect(() => {
    if (messages.length > 0 || busy) endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, busy]);

  async function exchange(body, shown) {
    setBusy(true);
    setError(null);
    if (shown) setMessages((m) => [...m, { id: nextId.current++, role: "user", text: shown }]);
    try {
      const reply = await api("/chat", {
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

  function send(text) {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    void exchange({ message }, message);
  }

  function onSubmit(e) {
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
  const firstName = (user?.display_name ?? "").split(" ")[0];
  return (
    <main className="narrow">
      <div className="page-header">
        <div>
          <h1>{t("chatTitle")}</h1>
          <p className="lead">{t("chatIntro")}</p>
        </div>
      </div>
      <div className="chat-shell">
        <div className="chat-head">
          <AssistantAvatar />
          <div className="who">
            <strong>{t("assistantName")}</strong>
            <span>
              <span className="dot" aria-hidden="true" />
              {t("assistantStatus")}
            </span>
          </div>
          <button
            type="button"
            className={lastAssistant?.offerHandoff ? undefined : "secondary"}
            disabled={busy}
            onClick={() => send(PERSON[lang])}
          >
            <Headset size={18} aria-hidden="true" />
            {t("talkToPerson")}
          </button>
        </div>
        <div className="messages" aria-live="polite" aria-relevant="additions">
          {messages.length === 0 && (
            <div className="welcome">
              <span className="avatar lg" aria-hidden="true">
                <Bot size={22} />
              </span>
              <h2>{t("greeting", { name: firstName })}</h2>
              <p className="muted">{t("suggestions")}</p>
              <div className="suggest-grid">
                {SUGGESTIONS.map(([key, Icon]) => (
                  <button key={key} type="button" className="suggest" onClick={() => send(t(key))}>
                    <span className="icon-tile" aria-hidden="true">
                      <Icon size={18} />
                    </span>
                    {t(key)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg-row ${m.role}`}>
              {m.role === "assistant" && <AssistantAvatar />}
              <div className="msg-col">
                <div className={`msg ${m.role}`}>
                  {m.role === "assistant" ? <AssistantText text={m.text} /> : m.text}
                  {m.steps && m.steps.length > 0 && (
                    <div className="steps">
                      {m.steps.map((step, i) => (
                        <span key={i}>
                          <Check size={14} aria-hidden="true" />
                          {step}
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
                    onConfirm={() => void exchange({ confirm_action_id: m.confirmation.action_id }, t("confirm"))}
                    onChange={() => {
                      void exchange({ message: NO[lang] }, NO[lang]);
                      inputRef.current?.focus();
                    }}
                  />
                )}
              </div>
            </div>
          ))}
          {busy && (
            <div className="msg-row assistant">
              <AssistantAvatar />
              <div className="msg assistant typing" role="status">
                <span className="typing-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
                <span className="sr-only">{t("working")}</span>
              </div>
            </div>
          )}
          {error !== null && <ErrorMessage error={error} />}
          <div ref={endRef} />
        </div>
        <div className="chat-bottom">
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
            <button type="submit" aria-label={t("send")} title={t("send")} disabled={busy || !draft.trim()}>
              <SendHorizontal size={20} aria-hidden="true" />
            </button>
          </form>
          <p className="chat-foot">{t("chatDisclaimer")}</p>
        </div>
      </div>
    </main>
  );
}
