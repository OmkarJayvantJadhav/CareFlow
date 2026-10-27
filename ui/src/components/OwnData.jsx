import { Download, FileLock2, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useSession } from "../session";
import { PasswordField } from "./AuthForms";
import ConfirmDialog from "./ConfirmDialog";
import ErrorMessage from "./ErrorMessage";

/** A patient's or caregiver's own data: download it all, or delete the account and personal details. */
export default function OwnData() {
  const { user, demo, signOut, t } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  async function download() {
    setError(null);
    try {
      const data = await api("/me/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "careflow-my-data.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err);
    }
  }

  async function erase() {
    setBusy(true);
    setDeleteError(null);
    try {
      await api("/me/erase", { method: "POST", body: { password } });
      signOut();
      navigate(demo ? "/" : "/login", { replace: true, state: { accountDeleted: true } });
    } catch (err) {
      setDeleteError(err);
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="data-h" style={{ marginTop: "1rem" }}>
      <div className="card-head">
        <h2 id="data-h">
          <FileLock2 size={18} aria-hidden="true" />
          {t("yourData")}
        </h2>
      </div>
      <p className="muted">{t("yourDataIntro")}</p>
      <div className="row">
        <button type="button" className="secondary" onClick={download}>
          <Download size={16} aria-hidden="true" />
          {t("downloadData")}
        </button>
        {user.has_password && (
          <button type="button" className="danger-outline" onClick={() => setDeleting(true)}>
            <Trash2 size={16} aria-hidden="true" />
            {t("deleteAccount")}
          </button>
        )}
      </div>
      {error !== null && <ErrorMessage error={error} />}
      <ConfirmDialog
        open={deleting}
        title={t("deleteAccount")}
        confirmLabel={t("deleteAccountConfirm")}
        cancelLabel={t("cancel")}
        busy={busy}
        danger
        confirmDisabled={password.length === 0}
        onConfirm={erase}
        onClose={() => {
          setDeleting(false);
          setPassword("");
        }}
      >
        <p>{t(user.role === "caregiver" ? "deleteCaregiverText" : "deleteAccountText")}</p>
        <PasswordField id="erase-password" value={password} onChange={setPassword} autoComplete="current-password" />
        {deleteError !== null && (
          <ErrorMessage error={deleteError} messages={{ INVALID_CREDENTIALS: "wrongPassword" }} />
        )}
      </ConfirmDialog>
    </section>
  );
}
