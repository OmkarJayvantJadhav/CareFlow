import { ArrowLeft, HeartPulse, Printer } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { longDate } from "../format";
import { useSession } from "../session";

const STATUS_TONE = { booked: "ok", rescheduled: "brand", displaced: "warn", no_show: "danger" };

/** S11: a printable appointment receipt with its signed reference as a QR code (feature 20). */
export default function Receipt() {
  const { id } = useParams();
  const { lang, t } = useSession();
  const [receipt, setReceipt] = useState(null);
  const [qr, setQr] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/appointments/${id}/receipt`)
      .then(async (r) => {
        setReceipt(r);
        setQr(await QRCode.toDataURL(r.reference, { margin: 1, width: 360, errorCorrectionLevel: "M" }));
      })
      .catch(setError);
  }, [id]);

  return (
    <main className="narrow">
      <div className="page-header no-print">
        <div>
          <h1>{t("receiptTitle")}</h1>
        </div>
        <div className="row">
          <Link className="button secondary" to="/appointments">
            <ArrowLeft size={16} aria-hidden="true" />
            {t("navAppointments")}
          </Link>
          {receipt && (
            <button type="button" onClick={() => window.print()}>
              <Printer size={16} aria-hidden="true" />
              {t("printReceipt")}
            </button>
          )}
        </div>
      </div>
      {error !== null && <ErrorMessage error={error} />}
      {receipt === null && error === null && <Loading />}
      {receipt && (
        <article className="card receipt" aria-label={t("receiptTitle")}>
          <header className="receipt-head">
            <span className="brand-mark" aria-hidden="true">
              <HeartPulse size={20} />
            </span>
            <div>
              <strong>{receipt.hospital}</strong>
              <div className="muted small">{receipt.hospital_address}</div>
            </div>
            <span className={`badge ${STATUS_TONE[receipt.status] ?? ""}`}>{t(`status_${receipt.status}`)}</span>
          </header>
          <div className="receipt-body">
            <dl className="summary">
              <dt>{t("reference")}</dt>
              <dd className="ref">{receipt.reference}</dd>
              <dt>{t("patientLabel")}</dt>
              <dd>
                {receipt.patient_name} · {receipt.patient_birth_year} · {receipt.patient_phone}
              </dd>
              <dt>{t("doctorLabel")}</dt>
              <dd>
                {receipt.doctor_name} ({receipt.department}) · {t("floorLabel", { floor: receipt.floor })}
              </dd>
              <dt>{t("dateLabel")}</dt>
              <dd>{longDate(receipt.date, lang)}</dd>
              <dt>{t("timeLabel")}</dt>
              <dd>{receipt.time}</dd>
              {receipt.booked_at && (
                <>
                  <dt>{t("bookedOn")}</dt>
                  <dd>{longDate(receipt.booked_at.slice(0, 10), lang)}</dd>
                </>
              )}
              <dt>{t("feeLabel")}</dt>
              <dd>{t("feeAtDesk")}</dd>
              <dt>{t("policyLabel")}</dt>
              <dd className="policy">{receipt.cancellation_policy}</dd>
            </dl>
            {qr && (
              <figure className="qr">
                <img src={qr} alt={`${t("reference")} ${receipt.reference}`} width={180} height={180} />
                <figcaption>{t("receiptQr")}</figcaption>
              </figure>
            )}
          </div>
          <p className="notice">{t("arriveNote")}</p>
        </article>
      )}
    </main>
  );
}
