import { CircleCheck, KeyRound } from "lucide-react";
import { useState } from "react";
import { useSession } from "../session";
import { PasswordField } from "./AuthForms";
import ErrorMessage from "./ErrorMessage";

/** Change one's own password: the current one, then the new one twice. Earlier sign-ins end; this one carries on. */
export default function PasswordForm({ idPrefix = "pw", currentLabel, onDone }) {
  const { changePassword, t } = useSession();
  const [pw, setPw] = useState({ current: "", next: "", again: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [mismatch, setMismatch] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (pw.next !== pw.again) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setBusy(true);
    try {
      const user = await changePassword(pw.current, pw.next);
      setPw({ current: "", next: "", again: "" });
      setDone(true);
      onDone?.(user);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} aria-label={t("changePassword")}>
      <PasswordField
        id={`${idPrefix}-current`}
        label={currentLabel ?? t("currentPassword")}
        value={pw.current}
        onChange={(current) => setPw({ ...pw, current })}
        autoComplete="current-password"
      />
      <PasswordField
        id={`${idPrefix}-new`}
        label={t("newPassword")}
        value={pw.next}
        onChange={(next) => setPw({ ...pw, next })}
        autoComplete="new-password"
        hint={t("passwordHint")}
      />
      <PasswordField
        id={`${idPrefix}-again`}
        label={t("newPasswordAgain")}
        value={pw.again}
        onChange={(again) => setPw({ ...pw, again })}
        autoComplete="new-password"
      />
      {mismatch && (
        <p className="error" role="alert">
          {t("passwordsDiffer")}
        </p>
      )}
      {error !== null && <ErrorMessage error={error} messages={{ INVALID_CREDENTIALS: "wrongPassword" }} />}
      {done && (
        <p className="notice" role="status">
          <CircleCheck size={18} aria-hidden="true" />
          {t("passwordChanged")}
        </p>
      )}
      <button type="submit" disabled={busy}>
        <KeyRound size={18} aria-hidden="true" />
        {busy ? t("saving") : t("changePassword")}
      </button>
    </form>
  );
}
