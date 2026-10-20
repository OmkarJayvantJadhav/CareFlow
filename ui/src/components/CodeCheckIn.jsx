import { Monitor, QrCode, ScanLine } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { longDate } from "../format";
import { useSession } from "../session";
import ConfirmDialog from "./ConfirmDialog";
import ErrorMessage from "./ErrorMessage";
import { CategoryBadges } from "./Registration";

/** Read a QR code with the camera where the browser can (BarcodeDetector); typing always works. */
function useScanner(onCode) {
  const videoRef = useRef(null);
  const latest = useRef(onCode);
  latest.current = onCode;
  const [scanning, setScanning] = useState(false);
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window;

  useEffect(() => {
    if (!scanning) return;
    let stream;
    let timer;
    let stopped = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (stopped) return;
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        const detector = new window.BarcodeDetector({ formats: ["qr_code"] });
        timer = window.setInterval(async () => {
          const found = await detector.detect(videoRef.current).catch(() => []);
          if (found.length) {
            setScanning(false);
            latest.current(found[0].rawValue);
          }
        }, 400);
      } catch {
        setScanning(false);
      }
    })();
    return () => {
      stopped = true;
      window.clearInterval(timer);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [scanning]);

  return { supported, scanning, setScanning, videoRef };
}

/** Front desk: check a patient in from the code on their receipt (feature 21). */
export default function CodeCheckIn({ onDone }) {
  const { lang, t } = useSession();
  const [code, setCode] = useState("");
  const [found, setFound] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function lookUp(value) {
    setError(null);
    setDone(null);
    setFound(null);
    try {
      setFound(await api(`/staff/check-in/lookup?code=${encodeURIComponent(value.trim())}`));
    } catch (err) {
      setError(err);
    }
  }
  const scanner = useScanner((value) => {
    setCode(value);
    void lookUp(value);
  });

  async function checkIn() {
    setBusy(true);
    setError(null);
    try {
      const entry = await api("/staff/check-in/by-code", { method: "POST", body: { code: code.trim() } });
      setDone(entry.token);
      setFound(null);
      setCode("");
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <section className="card code-check-in" aria-labelledby="code-h">
      <div className="card-head">
        <h2 id="code-h">
          <QrCode size={20} aria-hidden="true" />
          {t("checkInByCode")}
        </h2>
        <Link className="button quiet" to="/kiosk">
          <Monitor size={16} aria-hidden="true" />
          {t("openKiosk")}
        </Link>
      </div>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          void lookUp(code);
        }}
      >
        <label htmlFor="ci-code" className="sr-only">
          {t("receiptCode")}
        </label>
        <input
          id="ci-code"
          className="code-input"
          required
          maxLength={32}
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="CF-000123-ABC123"
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <button type="submit" className="secondary">
          {t("lookUp")}
        </button>
        {scanner.supported && (
          <button type="button" className="quiet" onClick={() => scanner.setScanning(!scanner.scanning)}>
            <ScanLine size={16} aria-hidden="true" />
            {scanner.scanning ? t("stopScan") : t("scanQr")}
          </button>
        )}
      </form>
      {scanner.scanning && (
        <video ref={scanner.videoRef} className="scanner" muted playsInline aria-label={t("scanQr")} />
      )}
      {error !== null && <ErrorMessage error={error} />}
      {done && (
        <p className="notice" role="status">
          {t("checkedInToken", { token: done })}
        </p>
      )}
      {found && (
        <div className="code-result">
          <div>
            <strong>{found.patient_name}</strong> <CategoryBadges categories={found.categories} />
            <div className="muted small">
              {found.doctor_name} ({found.department}) · {longDate(found.date, lang)} · {found.time}
            </div>
          </div>
          {found.checked_in ? (
            <span className="badge ok">{t("checkedInToken", { token: found.token })}</span>
          ) : found.today && ["booked", "rescheduled"].includes(found.status) ? (
            <button type="button" disabled={busy} onClick={() => setConfirming(true)}>
              {t("checkIn")}
            </button>
          ) : (
            <span className="badge warn">{found.today ? t(`status_${found.status}`) : t("notToday")}</span>
          )}
        </div>
      )}
      <ConfirmDialog
        open={confirming}
        title={t("checkIn")}
        confirmLabel={t("checkIn")}
        cancelLabel={t("back")}
        busy={busy}
        onConfirm={() => void checkIn()}
        onClose={() => setConfirming(false)}
      >
        {found && (
          <p>
            {found.patient_name} · {found.doctor_name} · {found.time}
          </p>
        )}
      </ConfirmDialog>
    </section>
  );
}
