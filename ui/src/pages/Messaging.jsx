import { CircleCheck, Mail, MessageSquareText, RotateCcw, Send, ServerCog, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

const CHANNELS = [
  { key: "sms", icon: MessageSquareText },
  { key: "email", icon: Mail },
];

function channelState(c) {
  if (c.ready) return c.real ? { tone: "ok", label: "msgReady" } : { tone: "info", label: "msgLogOnly" };
  if (c.problem === "missing_settings") return { tone: "warn", label: "msgMissing" };
  if (c.problem === "demo_mode") return { tone: "warn", label: "msgDemo" };
  if (c.problem === "unknown_provider") return { tone: "danger", label: "msgUnknown" };
  return { tone: "", label: "msgNotSet" };
}

/** Phase 7E: whether the hospital sends messages by SMS and e-mail, which kinds, a test, and what failed. */
export default function Messaging() {
  const { reloadConfig, t } = useSession();
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await api("/admin/messaging");
      setData(d);
      setForm({ enabled: d.enabled, kinds: d.enabled || d.kinds.length ? d.kinds : d.all_kinds });
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const d = await api("/admin/messaging", { method: "PUT", body: form });
      setData(d);
      setSaved(true);
      await reloadConfig();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const anyReady = data && CHANNELS.some((c) => data.channels[c.key].ready);
  const toggleKind = (kind) => (e) =>
    setForm({
      ...form,
      kinds: e.target.checked ? [...form.kinds, kind] : form.kinds.filter((k) => k !== kind),
    });

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("msgTitle")}</h1>
          <p className="lead">{t("msgIntro")}</p>
        </div>
      </div>
      {data === null && error === null && <Loading />}
      {data === null && error !== null && <ErrorMessage error={error} onRetry={load} />}
      {data && form && (
        <>
          <section className="card" aria-labelledby="msg-providers-h">
            <div className="card-head">
              <h2 id="msg-providers-h">
                <ServerCog size={20} aria-hidden="true" />
                {t("msgProviders")}
              </h2>
            </div>
            <p className="muted small card-intro">{t("msgProvidersHint")}</p>
            <ul className="plain-list channel-list">
              {CHANNELS.map(({ key, icon: Icon }) => {
                const c = data.channels[key];
                const state = channelState(c);
                return (
                  <li key={key} className="row">
                    <span className={`icon-tile ${state.tone}`} aria-hidden="true">
                      <Icon size={18} />
                    </span>
                    <div className="grow">
                      <strong>{t(`msgChannel_${key}`)}</strong>
                      <div className="muted small">{t("msgProvider", { name: c.provider })}</div>
                    </div>
                    <span className={`badge ${state.tone}`}>{t(state.label, { names: c.missing.join(", ") })}</span>
                  </li>
                );
              })}
            </ul>
          </section>

          <form className="card" onSubmit={save} aria-labelledby="msg-send-h">
            <div className="card-head">
              <h2 id="msg-send-h">
                <SlidersHorizontal size={20} aria-hidden="true" />
                {t("msgSending")}
              </h2>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={form.enabled}
                disabled={!anyReady && !form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              {t("msgEnabled")}
            </label>
            {!anyReady && <p className="hint">{t("msgNoChannel")}</p>}
            <fieldset className="plain kind-choices">
              <legend>{t("msgKinds")}</legend>
              {data.all_kinds.map((kind) => (
                <label className="check" key={kind}>
                  <input type="checkbox" checked={form.kinds.includes(kind)} onChange={toggleKind(kind)} />
                  <span>
                    {t(`kind_${kind}`)}
                    <span className="muted small"> – {t(`msgKind_${kind}`)}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {error !== null && <ErrorMessage error={error} />}
            {saved && (
              <p className="notice" role="status">
                <CircleCheck size={18} aria-hidden="true" />
                {data.enabled ? t("msgSavedOn") : t("msgSavedOff")}
              </p>
            )}
            <button type="submit" disabled={busy}>
              {t("save")}
            </button>
          </form>

          {anyReady && <TestMessage channels={data.channels} />}
          <Delivery data={data} onChange={load} />
        </>
      )}
    </main>
  );
}

function TestMessage({ channels }) {
  const { t } = useSession();
  const ready = CHANNELS.filter((c) => channels[c.key].ready).map((c) => c.key);
  const [channel, setChannel] = useState(ready[0]);
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(null);

  async function send(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      setSent(await api("/admin/messaging/test", { method: "POST", body: { channel, to } }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={send} aria-labelledby="msg-test-h">
      <div className="card-head">
        <h2 id="msg-test-h">
          <Send size={20} aria-hidden="true" />
          {t("msgTest")}
        </h2>
      </div>
      <p className="muted small card-intro">{t("msgTestHint")}</p>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "0 1 10rem" }}>
          <label htmlFor="msg-test-channel">{t("msgVia")}</label>
          <select id="msg-test-channel" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {ready.map((key) => (
              <option key={key} value={key}>
                {t(`msgChannel_${key}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: "1 1 14rem" }}>
          <label htmlFor="msg-test-to">{channel === "sms" ? t("mobile") : t("emailAddress")}</label>
          <input
            id="msg-test-to"
            required
            type={channel === "sms" ? "tel" : "email"}
            inputMode={channel === "sms" ? "tel" : "email"}
            maxLength={254}
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {sent && (
        <p className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {t("msgTestSent", { to: sent.to })}
        </p>
      )}
      <button type="submit" disabled={busy}>
        <Send size={16} aria-hidden="true" />
        {t("msgTestSend")}
      </button>
    </form>
  );
}

function Delivery({ data, onChange }) {
  const { t } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [queued, setQueued] = useState(null);
  const week = data.last_7_days;

  async function retry() {
    setBusy(true);
    setError(null);
    try {
      setQueued((await api("/admin/messaging/retry", { method: "POST" })).queued);
      await onChange();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="msg-week-h">
      <div className="card-head">
        <h2 id="msg-week-h">{t("msgWeek")}</h2>
        {week.failed > 0 && (
          <button type="button" className="secondary" disabled={busy} onClick={() => void retry()}>
            <RotateCcw size={16} aria-hidden="true" />
            {t("msgRetry")}
          </button>
        )}
      </div>
      <div className="stat-row">
        {["sent", "pending", "failed", "skipped"].map((status) => (
          <div className="stat-box" key={status}>
            <div className="label">{t(`delivery_${status}`)}</div>
            <div className="value">{week[status]}</div>
          </div>
        ))}
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {queued !== null && (
        <p className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {t("msgRetried", { count: queued })}
        </p>
      )}
      <h3 className="section-title">{t("msgProblems")}</h3>
      {data.problems.length === 0 ? (
        <p className="muted small">{t("msgNoProblems")}</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("msgColTime")}</th>
                <th scope="col">{t("msgColKind")}</th>
                <th scope="col">{t("msgColStatus")}</th>
                <th scope="col">{t("msgColReason")}</th>
              </tr>
            </thead>
            <tbody>
              {data.problems.map((p) => (
                <tr key={p.notification_id}>
                  <td>{new Date(p.at).toLocaleString()}</td>
                  <td>{t(`kind_${p.kind}`)}</td>
                  <td>
                    <span className={`badge ${p.status === "failed" ? "danger" : ""}`}>
                      {t(`delivery_${p.status}`)}
                    </span>
                  </td>
                  <td className="small">{p.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
