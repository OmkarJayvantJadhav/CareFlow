// Consent and caregiver access (features 34, 35): the patient decides; nothing is shared by default.
import { Check, ShieldCheck, UserPlus, Users, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useSession } from "../session";
import ErrorMessage from "./ErrorMessage";

const PURPOSES = ["reuse_registration", "reminders"];

/** For patients: their consents, caregiver requests to answer and the people who can act for them. */
export function PatientPrivacy() {
  const { t } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api("/me/consents"));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function act(fn) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  // The switch moves at once; the server's answer (or a reload after an error) settles it.
  async function toggle(purpose, granted) {
    setData((d) => ({ ...d, consents: { ...d.consents, [purpose]: granted } }));
    await act(() => api(`/me/consents/${purpose}`, { method: "PUT", body: { granted } }));
  }

  const pending = data?.requests.filter((r) => r.status === "pending") ?? [];
  return (
    <>
      <section className="card" aria-labelledby="consent-h" style={{ marginTop: "1rem" }}>
        <div className="card-head">
          <h2 id="consent-h">
            <ShieldCheck size={18} aria-hidden="true" />
            {t("consentTitle")}
          </h2>
        </div>
        {error !== null && <ErrorMessage error={error} />}
        {data && (
          <>
            {PURPOSES.map((purpose) => (
              <div key={purpose} className="consent-row">
                <div>
                  <strong>{t(`consent_${purpose}`)}</strong>
                  <p className="muted small">{t(`consentHint_${purpose}`)}</p>
                </div>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={data.consents[purpose]}
                    disabled={busy}
                    onChange={(e) => void toggle(purpose, e.target.checked)}
                  />
                  <span className="sr-only">{t(`consent_${purpose}`)}</span>
                  {data.consents[purpose] ? t("consentOn") : t("consentOff")}
                </label>
              </div>
            ))}
            {data.history.length > 0 && (
              <details>
                <summary>{t("consentHistory")}</summary>
                <ul className="booking-list">
                  {data.history.map((h, i) => (
                    <li key={i}>
                      <span>{t(`consent_${h.purpose}`)}</span>
                      <span className="muted small">
                        {h.granted ? t("consentOn") : t("consentOff")} · {new Date(h.at).toLocaleString()}
                      </span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>
      {data && (
        <section className="card" aria-labelledby="carers-h" style={{ marginTop: "1rem" }}>
          <div className="card-head">
            <h2 id="carers-h">
              <Users size={18} aria-hidden="true" />
              {t("caregiversTitle")}
            </h2>
          </div>
          {pending.length > 0 && (
            <ul className="booking-list" aria-label={t("pendingRequests")}>
              {pending.map((r) => (
                <li key={r.request_id}>
                  <span className="booking-who">
                    <strong>{r.caregiver_name}</strong>
                    <span className="muted small">{t("asksToManage")}</span>
                  </span>
                  <span className="row">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          api(`/me/caregiver-requests/${r.request_id}`, { method: "POST", body: { approve: true } }),
                        )
                      }
                    >
                      <Check size={16} aria-hidden="true" />
                      {t("approve")}
                    </button>
                    <button
                      type="button"
                      className="danger-outline"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          api(`/me/caregiver-requests/${r.request_id}`, { method: "POST", body: { approve: false } }),
                        )
                      }
                    >
                      <X size={16} aria-hidden="true" />
                      {t("decline")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {data.caregivers.length === 0 && pending.length === 0 && <p className="muted">{t("noCaregivers")}</p>}
          {data.caregivers.length > 0 && (
            <ul className="booking-list" aria-label={t("caregiversTitle")}>
              {data.caregivers.map((c) => (
                <li key={c.caregiver_user_id}>
                  <strong>{c.name}</strong>
                  <button
                    type="button"
                    className="danger-outline"
                    disabled={busy}
                    onClick={() => void act(() => api(`/me/caregivers/${c.caregiver_user_id}`, { method: "DELETE" }))}
                  >
                    {t("removeAccess")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </>
  );
}

/** For caregivers: ask a patient (by their username) for permission to manage their appointments. */
export function CaregiverAccess() {
  const { t } = useSession();
  const [username, setUsername] = useState("");
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  const load = useCallback(async () => {
    try {
      setRequests((await api("/caregiver/requests")).requests);
    } catch (err) {
      setError(err);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setSent(false);
    try {
      await api("/caregiver/requests", { method: "POST", body: { patient_username: username.trim() } });
      setUsername("");
      setSent(true);
      await load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card" aria-labelledby="access-h">
      <div className="card-head">
        <h2 id="access-h">
          <UserPlus size={18} aria-hidden="true" />
          {t("requestAccessTitle")}
        </h2>
      </div>
      <p className="muted" style={{ marginBottom: "1rem" }}>
        {t("requestAccessIntro")}
      </p>
      <form className="row" onSubmit={submit}>
        <div className="field" style={{ flex: "1 1 14rem", margin: 0 }}>
          <label htmlFor="ra-username">{t("patientUsername")}</label>
          <input
            id="ra-username"
            required
            minLength={3}
            maxLength={60}
            autoCapitalize="none"
            spellCheck={false}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <button type="submit" style={{ alignSelf: "flex-end" }}>
          {t("sendRequest")}
        </button>
      </form>
      {sent && (
        <p className="notice" role="status">
          {t("requestSent")}
        </p>
      )}
      {error !== null && <ErrorMessage error={error} />}
      {requests.length > 0 && (
        <ul className="booking-list" style={{ marginTop: "1rem" }} aria-label={t("myRequests")}>
          {requests.map((r) => (
            <li key={r.request_id}>
              <strong>{r.patient_name ?? t("awaitingPatient")}</strong>
              <span className={`badge ${r.status === "approved" ? "ok" : r.status === "declined" ? "danger" : ""}`}>
                {t(`requestStatus_${r.status}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
