import { CalendarCheck, CalendarPlus, Clock, Search, Sparkles, Stethoscope, Timer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { initials, longDate } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";

const TIMES = ["any", "morning", "afternoon"];

/** S10: find the best free times (ranked and explained in code) and book, reschedule or rebook. */
export default function Book() {
  const { user, lang, t } = useSession();
  const location = useLocation();
  // From My appointments: {reschedule: appointment} moves it; {rebook: appointment} books the same doctor again.
  const moving = location.state?.reschedule ?? null;
  const rebook = location.state?.rebook ?? null;
  const fixed = moving ?? rebook;

  const [departments, setDepartments] = useState(null);
  const [doctors, setDoctors] = useState([]);
  const [form, setForm] = useState({
    patientId: fixed?.patient_id ?? user.patients[0]?.patient_id ?? null,
    department: fixed?.department ?? "",
    doctorId: rebook ? String(rebook.doctor_id) : "",
    language: "",
    from: "",
    to: "",
    timeOfDay: "any",
  });
  const [results, setResults] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);
  const [chosen, setChosen] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    api("/departments")
      .then((d) => setDepartments(d.departments))
      .catch(setError);
  }, []);

  useEffect(() => {
    if (!form.department) {
      setDoctors([]);
      return;
    }
    api(`/doctors?specialty=${encodeURIComponent(form.department)}`)
      .then((d) => setDoctors(d.doctors))
      .catch(setError);
  }, [form.department]);

  const search = useCallback(
    async (values) => {
      if (!values.department || values.patientId === null) return;
      setSearching(true);
      setError(null);
      setDone(null);
      const params = new URLSearchParams({
        patient_id: String(values.patientId),
        time_of_day: values.timeOfDay,
        limit: "8",
      });
      if (values.doctorId) params.set("doctor_id", values.doctorId);
      else params.set("specialty", values.department);
      if (values.language) params.set("language", values.language);
      if (values.from) params.set("date_from", values.from);
      if (values.to) params.set("date_to", values.to);
      try {
        const found = await api(`/recommendations?${params}`);
        // A move must stay with a different slot than the current one.
        setResults({ ...found, slots: found.slots.filter((s) => s.slot_id !== moving?.slot_id) });
      } catch (err) {
        setError(err);
      } finally {
        setSearching(false);
      }
    },
    [moving],
  );

  // Coming from My appointments, show times straight away.
  useEffect(() => {
    if (fixed) void search(form);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only once, for the appointment we came with
  }, []);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const result = moving
        ? await api(`/appointments/${moving.appointment_id}`, {
            method: "PATCH",
            body: { new_slot_id: chosen.slot_id, confirmed: true },
          })
        : await api("/appointments", {
            method: "POST",
            body: { patient_id: form.patientId, slot_id: chosen.slot_id, confirmed: true },
          });
      setDone({ appointmentId: result.appointment_id, slot: chosen });
      setChosen(null);
      setResults(null);
    } catch (err) {
      setChosen(null);
      setError(err);
      if (err instanceof ApiError && err.code === "SLOT_TAKEN") void search(form);
    } finally {
      setBusy(false);
    }
  }

  const patientName = user.patients.find((p) => p.patient_id === form.patientId)?.name ?? user.display_name;
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{moving ? t("rescheduleTitle") : t("bookTitle")}</h1>
          <p className="lead">
            {moving
              ? t("rescheduleIntro", {
                  doctor: moving.doctor_name,
                  date: longDate(moving.date, lang),
                  time: moving.time,
                })
              : t("bookIntro")}
          </p>
        </div>
      </div>

      {done && (
        <div className="notice" role="status">
          <CalendarCheck size={18} aria-hidden="true" />
          <div>
            <strong>{moving ? t("moved") : t("booked")}</strong> {done.slot.doctor_name} ·{" "}
            {longDate(done.slot.date, lang)} · {done.slot.time}
            <div className="row" style={{ marginTop: "0.5rem" }}>
              <Link className="button" to={`/receipt/${done.appointmentId}`}>
                {t("viewReceipt")}
              </Link>
              <Link className="button secondary" to="/appointments">
                {t("navAppointments")}
              </Link>
            </div>
          </div>
        </div>
      )}

      <section className="card" aria-label={t("findSlots")}>
        {departments === null && error === null && <Loading />}
        {departments && (
          <form
            className="book-form"
            onSubmit={(e) => {
              e.preventDefault();
              void search(form);
            }}
          >
            {user.patients.length > 1 && !fixed && (
              <div className="field">
                <label htmlFor="bk-patient">{t("forPatient")}</label>
                <select
                  id="bk-patient"
                  value={form.patientId ?? ""}
                  onChange={(e) => setForm({ ...form, patientId: Number(e.target.value) })}
                >
                  {user.patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="field">
              <label htmlFor="bk-dept">{t("departmentLabel")}</label>
              <select
                id="bk-dept"
                required
                disabled={Boolean(fixed)}
                value={form.department}
                onChange={(e) => setForm({ ...form, department: e.target.value, doctorId: "" })}
              >
                <option value="">{t("chooseDepartment")}</option>
                {departments.map((d) => (
                  <option key={d.department} value={d.department}>
                    {d.department}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="bk-doctor">{t("doctorLabel")}</label>
              <select id="bk-doctor" value={form.doctorId} disabled={!form.department} onChange={set("doctorId")}>
                <option value="">{t("anyDoctor")}</option>
                {doctors.map((d) => (
                  <option key={d.doctor_id} value={d.doctor_id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="bk-lang">{t("doctorLanguage")}</label>
              <select id="bk-lang" value={form.language} onChange={set("language")}>
                <option value="">{t("anyLanguage")}</option>
                {LANGS.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="bk-from">{t("fromDate")}</label>
              <input id="bk-from" type="date" value={form.from} onChange={set("from")} />
            </div>
            <div className="field">
              <label htmlFor="bk-to">{t("toDate")}</label>
              <input id="bk-to" type="date" value={form.to} min={form.from || undefined} onChange={set("to")} />
            </div>
            <div className="field span-all">
              <span className="field-label" id="bk-tod">
                {t("timeOfDay")}
              </span>
              <div className="segmented" role="group" aria-labelledby="bk-tod">
                {TIMES.map((key) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={form.timeOfDay === key}
                    onClick={() => setForm({ ...form, timeOfDay: key })}
                  >
                    {t(`tod_${key}`)}
                  </button>
                ))}
              </div>
            </div>
            <div className="span-all">
              <button type="submit" disabled={searching || !form.department}>
                <Search size={18} aria-hidden="true" />
                {searching ? t("searching") : t("findSlots")}
              </button>
            </div>
          </form>
        )}
      </section>

      {error !== null && <ErrorMessage error={error} />}

      {results && (
        <section aria-labelledby="rec-h">
          <div className="section-title">
            <h2 id="rec-h">
              <Sparkles size={20} aria-hidden="true" style={{ verticalAlign: "-3px", marginRight: "0.375rem" }} />
              {t("recommended")}
            </h2>
          </div>
          {results.slots.length === 0 && (
            <div className="card empty">
              <span className="icon-tile" aria-hidden="true">
                <CalendarPlus size={22} />
              </span>
              <span>{t("noSlotsFound")}</span>
            </div>
          )}
          <ul className="slot-list">
            {results.slots.map((s) => (
              <li key={s.slot_id} className="card slot-card">
                <span className="avatar lg" aria-hidden="true">
                  {initials(s.doctor_name)}
                </span>
                <div className="info">
                  <strong>{s.doctor_name}</strong>
                  <div className="meta">
                    <span>
                      <Stethoscope size={15} aria-hidden="true" />
                      {s.department}
                    </span>
                    <span>
                      <Clock size={15} aria-hidden="true" />
                      {longDate(s.date, lang)} · {s.time}
                    </span>
                    <span>
                      <Timer size={15} aria-hidden="true" />
                      {t("expectedVisit", { minutes: s.expected_minutes })}
                    </span>
                  </div>
                  <div className="reasons">
                    {s.reasons.map((r) => (
                      <span key={r} className={`badge ${r === "earliest" ? "brand" : ""}`}>
                        {t(`reason_${r}`)}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={`${moving ? t("moveHere") : t("choose")}: ${s.doctor_name}, ${longDate(s.date, lang)} ${s.time}`}
                  onClick={() => setChosen(s)}
                >
                  {moving ? t("moveHere") : t("choose")}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <ConfirmDialog
        open={chosen !== null}
        title={moving ? t("confirmMove") : t("confirmBooking")}
        confirmLabel={t("confirm")}
        cancelLabel={t("back")}
        busy={busy}
        onConfirm={() => void confirm()}
        onClose={() => setChosen(null)}
      >
        {chosen && (
          <dl className="summary">
            <dt>{t("patientLabel")}</dt>
            <dd>{patientName}</dd>
            <dt>{t("doctorLabel")}</dt>
            <dd>
              {chosen.doctor_name} ({chosen.department})
            </dd>
            <dt>{t("dateLabel")}</dt>
            <dd>{longDate(chosen.date, lang)}</dd>
            <dt>{t("timeLabel")}</dt>
            <dd>{chosen.time}</dd>
            {moving && (
              <>
                <dt>{t("fromLabel")}</dt>
                <dd>
                  {moving.doctor_name}, {longDate(moving.date, lang)} {moving.time}
                </dd>
              </>
            )}
            <dt>{t("policyLabel")}</dt>
            <dd className="policy">{results?.cancellation_policy}</dd>
          </dl>
        )}
      </ConfirmDialog>
    </main>
  );
}
