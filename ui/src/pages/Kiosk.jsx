import { ArrowLeft, HeartPulse, Info, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useErrorText } from "../components/ErrorMessage";
import { LANGS } from "../i18n";
import { useSession } from "../session";

const RESET_MS = 20000;

/** S15: a self-service check-in screen at reception (feature 27). Staff open it on a tablet; patients
 * type the code from their receipt. Only the first name, doctor and time are shown, never other data. */
export default function Kiosk() {
  const { lang, setLang, t } = useSession();
  const errorText = useErrorText();
  const [code, setCode] = useState("");
  const [found, setFound] = useState(null);
  const [token, setToken] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setCode("");
    setFound(null);
    setToken(null);
    setError(null);
  };

  // Start again by itself, so the next patient never sees the previous one.
  useEffect(() => {
    if (!found && !token && !error) return;
    const timer = window.setTimeout(reset, RESET_MS);
    return () => window.clearTimeout(timer);
  }, [found, token, error]);

  async function lookUp(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api(`/staff/check-in/lookup?code=${encodeURIComponent(code.trim())}`);
      if (r.checked_in) setToken(r.token);
      else setFound(r);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function checkIn() {
    setBusy(true);
    setError(null);
    try {
      setToken((await api("/staff/check-in/by-code", { method: "POST", body: { code: code.trim() } })).token);
      setFound(null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const bookable = found && found.today && ["booked", "rescheduled"].includes(found.status);
  return (
    <div className="kiosk">
      <div className="banner" role="note">
        <Info size={15} aria-hidden="true" />
        {t("banner")}
      </div>
      <header className="kiosk-head">
        <span className="brand-mark" aria-hidden="true">
          <HeartPulse size={24} />
        </span>
        <strong>{t("hospital")}</strong>
        <div className="segmented" role="group" aria-label={t("chooseLanguage")}>
          {LANGS.map((l) => (
            <button
              key={l.code}
              type="button"
              aria-pressed={lang === l.code}
              onClick={() => setLang(l.code)}
              lang={l.code}
            >
              {l.label}
            </button>
          ))}
        </div>
        <Link className="button quiet" to="/desk" aria-label={t("exitKiosk")}>
          <LogOut size={18} aria-hidden="true" />
        </Link>
      </header>
      <main className="kiosk-main">
        <h1>{t("kioskTitle")}</h1>
        {token ? (
          <section className="kiosk-card" role="status">
            <p className="kiosk-lead">{t("kioskDone")}</p>
            <div className="kiosk-token">
              <small>{t("yourToken")}</small>
              <strong>{token}</strong>
            </div>
            <p>{t("kioskWait")}</p>
            <button type="button" className="kiosk-button secondary" onClick={reset}>
              {t("kioskNext")}
            </button>
          </section>
        ) : found ? (
          <section className="kiosk-card" aria-live="polite">
            <p className="kiosk-lead">{t("kioskHello", { name: found.first_name })}</p>
            <p>
              {found.doctor_name} · {found.department} · {t("floorLabel", { floor: found.floor })}
            </p>
            <p className="kiosk-time">{found.time}</p>
            {bookable ? (
              <button type="button" className="kiosk-button" disabled={busy} onClick={() => void checkIn()}>
                {t("checkIn")}
              </button>
            ) : (
              <p className="notice warn">{found.today ? t("kioskAskDesk") : t("notToday")}</p>
            )}
            <button type="button" className="kiosk-button quiet" onClick={reset}>
              <ArrowLeft size={20} aria-hidden="true" />
              {t("back")}
            </button>
          </section>
        ) : (
          <form className="kiosk-card" onSubmit={lookUp}>
            <label htmlFor="kiosk-code" className="kiosk-lead">
              {t("kioskEnterCode")}
            </label>
            <input
              id="kiosk-code"
              className="kiosk-input"
              required
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={32}
              placeholder="CF-000123-ABC123"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            <button type="submit" className="kiosk-button" disabled={busy || !code.trim()}>
              {t("kioskContinue")}
            </button>
            <p className="muted">{t("kioskHelp")}</p>
          </form>
        )}
        {error !== null && (
          <p className="error kiosk-error" role="alert">
            {errorText(error)}
          </p>
        )}
      </main>
    </div>
  );
}
