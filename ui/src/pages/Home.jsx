import {
  BookOpen,
  CalendarPlus,
  ChevronRight,
  Clock,
  Layers,
  ListOrdered,
  MapPin,
  MonitorPlay,
  Phone,
  Siren,
  Smartphone,
  Stethoscope,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { weekdayName } from "../format";
import { LANGS } from "../i18n";
import { COLLECTION_ICON } from "./Library";
import { useSession } from "../session";

const BEFORE_YOUR_VISIT = ["test_preparation", "insurance", "policies", "facilities"];
const STEPS = [
  { icon: CalendarPlus, title: "homeStep1Title", text: "homeStep1Text" },
  { icon: Smartphone, title: "homeStep2Title", text: "homeStep2Text" },
  { icon: ListOrdered, title: "homeStep3Title", text: "homeStep3Text" },
];

function languageNames(codes) {
  return codes.map((code) => LANGS.find((l) => l.code === code)?.label ?? code).join(", ");
}

/** A hospital's public homepage (D-134): shown at "/" on its own deployment only, to visitors not signed in.
 * Everything on it comes from Hospital setup, so it follows the admins' changes. The demo keeps its start page. */
export default function Home() {
  const { config, hospitalName, emergencyNote, lang, t } = useSession();
  const [directory, setDirectory] = useState(null);
  const hospital = config?.hospital;

  useEffect(() => {
    api("/directory")
      .then(setDirectory)
      .catch(() => setDirectory({ reception_hours: "", departments: [] }));
  }, []);

  const doctors = (directory?.departments ?? []).flatMap((d) =>
    d.doctors.map((doc) => ({ ...doc, department: d.name })),
  );
  const mapUrl =
    hospital?.address &&
    `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${hospitalName}, ${hospital.address}`)}`;

  return (
    <main className="home">
      <section className="home-hero" aria-labelledby="home-h">
        {hospital?.address && (
          <span className="eyebrow">
            <MapPin size={15} aria-hidden="true" />
            {hospital.address}
          </span>
        )}
        <h1 id="home-h">{hospitalName || t("homeFallbackName")}</h1>
        <p className="lead">{t("homeTagline")}</p>
        <div className="home-actions">
          <Link to="/book" className="button">
            <CalendarPlus size={18} aria-hidden="true" />
            {t("homeBook")}
          </Link>
          <Link to="/queue" className="button secondary">
            <ListOrdered size={18} aria-hidden="true" />
            {t("homeQueue")}
          </Link>
          <Link to="/library" className="button secondary">
            <BookOpen size={18} aria-hidden="true" />
            {t("homeInfo")}
          </Link>
        </div>
      </section>

      <section className="home-facts" aria-label={t("homeFacts")}>
        {directory?.reception_hours && (
          <div className="card fact">
            <span className="icon-tile" aria-hidden="true">
              <Clock size={20} />
            </span>
            <div>
              <h2>{t("homeHours")}</h2>
              <p>{t("homeReception", { hours: directory.reception_hours })}</p>
            </div>
          </div>
        )}
        {hospital?.address && (
          <div className="card fact">
            <span className="icon-tile" aria-hidden="true">
              <MapPin size={20} />
            </span>
            <div>
              <h2>{t("homeAddress")}</h2>
              <p>{hospital.address}</p>
              <a href={mapUrl} target="_blank" rel="noopener noreferrer" className="small">
                {t("homeMap")}
              </a>
            </div>
          </div>
        )}
        {hospital?.phone && (
          <div className="card fact">
            <span className="icon-tile" aria-hidden="true">
              <Phone size={20} />
            </span>
            <div>
              <h2>{t("homePhone")}</h2>
              <p>
                <a href={`tel:${hospital.phone.replace(/[^\d+]/g, "")}`}>{hospital.phone}</a>
              </p>
            </div>
          </div>
        )}
      </section>

      {directory && directory.departments.length > 0 && (
        <section className="home-section" aria-labelledby="home-dept-h">
          <h2 id="home-dept-h">{t("homeDepartments")}</h2>
          <ul className="home-grid">
            {directory.departments.map((d) => (
              <li key={d.name} className="card dept">
                <span className="icon-tile" aria-hidden="true">
                  <Layers size={18} />
                </span>
                <div>
                  <h3>{d.name}</h3>
                  <p className="muted small">
                    {t("homeDeptDetails", { floor: d.floor, start: d.opd_start, end: d.opd_end })}
                  </p>
                  <p className="muted small">{t("homeDoctorCount", { count: d.doctors.length })}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {doctors.length > 0 && (
        <section className="home-section" aria-labelledby="home-doc-h">
          <h2 id="home-doc-h">{t("homeDoctors")}</h2>
          <ul className="home-grid">
            {doctors.map((doc) => (
              <li key={`${doc.department}-${doc.name}`} className="card doctor">
                <div className="doctor-head">
                  <span className="icon-tile info" aria-hidden="true">
                    <Stethoscope size={18} />
                  </span>
                  <div>
                    <h3>{doc.name}</h3>
                    <p className="muted small">{doc.department}</p>
                  </div>
                </div>
                <p className="small">
                  <strong>{t("homeLanguages")}:</strong> {languageNames(doc.languages)}
                </p>
                <p className="small">
                  <strong>{t("homeOpdDays")}:</strong> {doc.opd_days.map((d) => weekdayName(d, lang)).join(", ")}
                </p>
                <Link to="/book" className="button secondary small-button">
                  <CalendarPlus size={16} aria-hidden="true" />
                  {t("homeBook")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="home-section" aria-labelledby="home-how-h">
        <h2 id="home-how-h">{t("homeHow")}</h2>
        <ol className="home-steps">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="card">
              <span className="step-number" aria-hidden="true">
                {i + 1}
              </span>
              <span className="icon-tile" aria-hidden="true">
                <Icon size={20} />
              </span>
              <h3>{t(title)}</h3>
              <p className="muted">{t(text)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-section" aria-labelledby="home-before-h">
        <h2 id="home-before-h">{t("homeBefore")}</h2>
        <ul className="home-links">
          {BEFORE_YOUR_VISIT.map((c) => {
            const Icon = COLLECTION_ICON[c] ?? BookOpen;
            return (
              <li key={c}>
                <Link to={`/library?collection=${c}`} className="role">
                  <span className="icon-tile" aria-hidden="true">
                    <Icon size={20} />
                  </span>
                  <span className="role-text">
                    <strong>{t(`collection_${c}`)}</strong>
                  </span>
                  <ChevronRight className="chev" size={18} aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="home-emergency" aria-labelledby="home-em-h">
        <span className="icon-tile danger" aria-hidden="true">
          <Siren size={22} />
        </span>
        <div>
          <h2 id="home-em-h">{t("homeEmergencyTitle")}</h2>
          <p>{t("homeEmergencyText")}</p>
          {emergencyNote && <p>{emergencyNote}</p>}
        </div>
        <a href="tel:112" className="button danger">
          <Phone size={18} aria-hidden="true" />
          {t("homeCall112")}
        </a>
      </section>

      <footer className="home-footer">
        <div>
          <strong>{hospitalName}</strong>
          {hospital?.address && <span>{hospital.address}</span>}
          {directory?.reception_hours && <span>{t("homeReception", { hours: directory.reception_hours })}</span>}
          {hospital?.phone && <span>{hospital.phone}</span>}
        </div>
        <nav aria-label={t("homeFooterLinks")}>
          <Link to="/library">{t("homeInfo")}</Link>
          <Link to="/login">{t("homeStaffLogin")}</Link>
          {config?.demo_site_url && (
            <a href={config.demo_site_url} target="_blank" rel="noopener noreferrer">
              <MonitorPlay size={15} aria-hidden="true" /> {t("tryDemoSite")}
            </a>
          )}
        </nav>
      </footer>
    </main>
  );
}
