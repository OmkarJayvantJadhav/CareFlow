import { CircleCheck, Eye, EyeOff, FilePlus2, FileText, Languages, RotateCcw, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import ConfirmDialog from "../components/ConfirmDialog";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { longDate } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";

const COLLECTIONS = ["policies", "insurance", "departments", "doctors", "test_preparation", "facilities"];
const NEW_BODY = "## \n\n";
const ORIGIN_TONE = { edited: "warn", added: "info" };
const DONE = { hide: "documentHidden", restore: "documentRestored", revert: "documentReverted" };

/** Which placeholders exist, with the number each stands for now. */
function Placeholders({ placeholders }) {
  const { t } = useSession();
  return (
    <details className="placeholders">
      <summary>{t("placeholdersTitle")}</summary>
      <p className="muted small">{t("placeholdersHelp")}</p>
      <ul className="plain-list small">
        {Object.entries(placeholders).map(([key, { value, unit }]) => (
          <li key={key}>
            <code>{`{{${key}}}`}</code> = {value} {t(`unit_${unit}`)}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Edit one document, or write a new one / a translation (`draft` holds the fields being written). */
function Editor({ draft, setDraft, placeholders, onSave, onClose, busy, error }) {
  const { t } = useSession();
  const isNew = draft.document_id === undefined;
  return (
    <form
      className="card stack"
      aria-label={isNew ? t("newDocument") : t("editDocument")}
      onSubmit={(e) => {
        e.preventDefault();
        onSave();
      }}
    >
      <div className="card-head">
        <h2>
          <FileText size={20} aria-hidden="true" />
          {draft.translation_of ? t("addTranslation") : isNew ? t("newDocument") : t("editDocument")}
        </h2>
        <button type="button" className="quiet" onClick={onClose}>
          {t("close")}
        </button>
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="doc-title">{t("documentTitle")}</label>
          <input
            id="doc-title"
            required
            minLength={3}
            maxLength={200}
            lang={draft.language}
            value={draft.title}
            onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          />
        </div>
        <div className="field">
          <label htmlFor="doc-collection">{t("documentCollection")}</label>
          <select
            id="doc-collection"
            disabled={!isNew || Boolean(draft.translation_of)}
            value={draft.collection}
            onChange={(e) => setDraft({ ...draft, collection: e.target.value })}
          >
            {COLLECTIONS.map((c) => (
              <option key={c} value={c}>
                {t(`collection_${c}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="doc-language">{t("documentLanguage")}</label>
          <select
            id="doc-language"
            disabled={!isNew}
            value={draft.language}
            onChange={(e) => setDraft({ ...draft, language: e.target.value })}
          >
            {LANGS.filter((l) => !draft.languages || draft.languages.includes(l.code)).map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field">
        <label htmlFor="doc-body">{t("documentText")}</label>
        <textarea
          id="doc-body"
          className="doc-body"
          rows={18}
          required
          lang={draft.language}
          spellCheck
          aria-describedby="doc-body-hint"
          value={draft.body}
          onChange={(e) => setDraft({ ...draft, body: e.target.value })}
        />
        <p id="doc-body-hint" className="hint">
          {t("documentTextHint")}
        </p>
      </div>
      <Placeholders placeholders={placeholders} />
      {!isNew && (
        <label className="check">
          <input
            type="checkbox"
            checked={draft.checked_today}
            onChange={(e) => setDraft({ ...draft, checked_today: e.target.checked })}
          />
          {t("checkedToday")}
        </label>
      )}
      {error !== null && <ErrorMessage error={error} />}
      <div className="row">
        <button type="submit" disabled={busy}>
          {busy ? t("savingIndex") : t("save")}
        </button>
      </div>
    </form>
  );
}

/** Admins keep the hospital's information documents: what the library shows and the assistant answers from. */
export default function Documents() {
  const { lang, t } = useSession();
  const [filters, setFilters] = useState({ language: lang, collection: "", q: "" });
  const [query, setQuery] = useState(filters);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [current, setCurrent] = useState(null); // the stored document being edited
  const [busy, setBusy] = useState(false);
  const [editError, setEditError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [confirm, setConfirm] = useState(null); // {kind: "hide" | "revert"}

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v) params.set(k, v);
    try {
      setData(await api(`/admin/documents?${params}`));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [query]);
  useEffect(() => {
    void load();
  }, [load]);

  async function open(id) {
    setNotice(null);
    setEditError(null);
    try {
      const doc = await api(`/admin/documents/${id}`);
      setCurrent(doc);
      setDraft({ ...doc, checked_today: true });
    } catch (err) {
      setError(err);
    }
  }

  function startNew() {
    setNotice(null);
    setEditError(null);
    setCurrent(null);
    setDraft({ title: "", body: NEW_BODY, collection: "policies", language: lang });
  }

  function startTranslation() {
    setEditError(null);
    setDraft({
      title: current.title,
      body: current.body,
      collection: current.collection,
      language: current.missing_languages[0],
      languages: current.missing_languages,
      translation_of: current.document_id,
    });
    setCurrent(null);
  }

  async function save() {
    setBusy(true);
    setEditError(null);
    try {
      const saved =
        draft.document_id === undefined
          ? await api("/admin/documents", {
              method: "POST",
              body: {
                title: draft.title,
                body: draft.body,
                collection: draft.collection,
                language: draft.language,
                translation_of: draft.translation_of ?? null,
              },
            })
          : await api(`/admin/documents/${draft.document_id}`, {
              method: "PUT",
              body: { title: draft.title, body: draft.body, checked_today: draft.checked_today },
            });
      setCurrent(saved);
      setDraft({ ...saved, checked_today: true });
      setNotice(t("documentSaved", { title: saved.title }));
      await load();
    } catch (err) {
      setEditError(err);
    } finally {
      setBusy(false);
    }
  }

  async function act(kind) {
    setBusy(true);
    setEditError(null);
    try {
      const path = { hide: "hide", restore: "restore", revert: "revert" }[kind];
      const result = await api(`/admin/documents/${current.document_id}/${path}`, { method: "POST" });
      setConfirm(null);
      if (result.deleted) {
        setCurrent(null);
        setDraft(null);
        setNotice(t("documentDeleted", { title: current.title }));
      } else {
        await open(current.document_id);
        setNotice(t(DONE[kind], { title: current.title }));
      }
      await load();
    } catch (err) {
      setEditError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("documentsTitle")}</h1>
          <p className="lead">{t("documentsIntro")}</p>
        </div>
        <button type="button" onClick={startNew}>
          <FilePlus2 size={18} aria-hidden="true" />
          {t("newDocument")}
        </button>
      </div>
      <div className="stack">
        {notice && (
          <p className="notice" role="status">
            <CircleCheck size={18} aria-hidden="true" />
            {notice}
          </p>
        )}
        {draft && data && (
          <>
            {current && (
              <div className="card row doc-actions">
                <span className={`badge ${ORIGIN_TONE[current.origin] ?? ""}`}>{t(`origin_${current.origin}`)}</span>
                {current.hidden && <span className="badge danger">{t("hiddenBadge")}</span>}
                <span className="muted small">
                  {t("verifiedOn", { date: longDate(current.last_verified, lang) })}
                  {current.edited_by && ` · ${t("editedBy", { name: current.edited_by })}`}
                </span>
                {!current.hidden && (
                  <Link
                    className="button secondary"
                    to={`/library/${current.collection}/${current.slug}`}
                    target="_blank"
                    rel="noopener"
                  >
                    <Eye size={16} aria-hidden="true" />
                    {t("viewInLibrary")}
                  </Link>
                )}
                {current.missing_languages.length > 0 && (
                  <button type="button" className="secondary" onClick={startTranslation}>
                    <Languages size={16} aria-hidden="true" />
                    {t("addTranslation")}
                  </button>
                )}
                {current.origin === "edited" && (
                  <button type="button" className="secondary" onClick={() => setConfirm({ kind: "revert" })}>
                    <RotateCcw size={16} aria-hidden="true" />
                    {t("revertDocument")}
                  </button>
                )}
                {current.hidden ? (
                  <button type="button" className="secondary" disabled={busy} onClick={() => act("restore")}>
                    <Eye size={16} aria-hidden="true" />
                    {t("restoreDocument")}
                  </button>
                ) : (
                  <button type="button" className="danger-outline" onClick={() => setConfirm({ kind: "hide" })}>
                    <EyeOff size={16} aria-hidden="true" />
                    {current.origin === "added" ? t("deleteDocument") : t("hideDocument")}
                  </button>
                )}
              </div>
            )}
            <Editor
              key={draft.document_id ?? `new-${draft.translation_of ?? ""}`}
              draft={draft}
              setDraft={setDraft}
              placeholders={data.placeholders}
              busy={busy}
              error={editError}
              onSave={save}
              onClose={() => {
                setDraft(null);
                setCurrent(null);
              }}
            />
          </>
        )}

        <section className="card" aria-labelledby="docs-h">
          <div className="card-head">
            <h2 id="docs-h">{t("allDocuments")}</h2>
            {data && (
              <span className="muted small">
                {t("documentCounts", {
                  edited: data.counts.edited,
                  added: data.counts.added,
                  hidden: data.counts.hidden,
                })}
              </span>
            )}
          </div>
          <form
            className="row account-filters"
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(filters);
            }}
          >
            <div className="field">
              <label htmlFor="docs-language">{t("documentLanguage")}</label>
              <select
                id="docs-language"
                value={filters.language}
                onChange={(e) => setFilters({ ...filters, language: e.target.value })}
              >
                {LANGS.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="docs-collection">{t("documentCollection")}</label>
              <select
                id="docs-collection"
                value={filters.collection}
                onChange={(e) => setFilters({ ...filters, collection: e.target.value })}
              >
                <option value="">{t("allCollections")}</option>
                {COLLECTIONS.map((c) => (
                  <option key={c} value={c}>
                    {t(`collection_${c}`)}
                  </option>
                ))}
              </select>
            </div>
            <div className="field grow">
              <label htmlFor="docs-q">{t("documentSearch")}</label>
              <input
                id="docs-q"
                type="search"
                maxLength={100}
                value={filters.q}
                onChange={(e) => setFilters({ ...filters, q: e.target.value })}
              />
            </div>
            <button type="submit" className="secondary">
              <Search size={16} aria-hidden="true" />
              {t("search")}
            </button>
          </form>
          {error !== null && <ErrorMessage error={error} onRetry={load} />}
          {data === null && error === null && <Loading />}
          {data && data.documents.length === 0 && <p className="muted">{t("noDocumentsFound")}</p>}
          {data && data.documents.length > 0 && (
            <ul className="patient-results">
              {data.documents.map((d) => (
                <li key={d.document_id}>
                  <button
                    type="button"
                    className="patient-result"
                    aria-pressed={current?.document_id === d.document_id}
                    onClick={() => open(d.document_id)}
                  >
                    <FileText size={18} aria-hidden="true" />
                    <span>
                      <strong lang={d.language}>{d.title}</strong>
                      <span className="muted small"> · {t(`collection_${d.collection}`)}</span>
                      {d.origin !== "template" && (
                        <span className={`badge ${ORIGIN_TONE[d.origin] ?? ""}`}> {t(`origin_${d.origin}`)}</span>
                      )}
                      {d.hidden && <span className="badge danger">{t("hiddenBadge")}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {data?.more && <p className="muted small">{t("documentsMore")}</p>}
        </section>
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm?.kind === "revert"
            ? t("revertDocument")
            : current?.origin === "added"
              ? t("deleteDocument")
              : t("hideDocument")
        }
        confirmLabel={
          confirm?.kind === "revert"
            ? t("revertDocument")
            : current?.origin === "added"
              ? t("deleteDocument")
              : t("hideDocument")
        }
        cancelLabel={t("cancel")}
        busy={busy}
        danger={confirm?.kind === "hide"}
        onConfirm={() => act(confirm.kind)}
        onClose={() => setConfirm(null)}
      >
        <p>
          {confirm?.kind === "revert"
            ? t("revertText")
            : current?.origin === "added"
              ? t("deleteDocumentText")
              : t("hideText")}
        </p>
      </ConfirmDialog>
    </main>
  );
}
