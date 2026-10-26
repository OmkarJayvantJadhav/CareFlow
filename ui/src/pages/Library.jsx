// The hospital's information library (open to everyone, signed in or not): every document the assistant
// answers from, in the interface language.
import { BookOpen, Building2, FileText, FlaskConical, Search, ShieldCheck, Stethoscope, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { useSession } from "../session";

export const COLLECTION_ICON = {
  policies: ShieldCheck,
  insurance: Wallet,
  departments: Building2,
  doctors: Stethoscope,
  test_preparation: FlaskConical,
  facilities: FileText,
};

export default function Library() {
  const { lang, t } = useSession();
  const [params, setParams] = useSearchParams();
  const collection = params.get("collection") ?? "";
  const query = params.get("q") ?? "";
  const [text, setText] = useState(query);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let current = true;
    const search = new URLSearchParams({ language: lang });
    if (collection) search.set("collection", collection);
    if (query) search.set("q", query);
    setError(null);
    api(`/library?${search}`)
      .then((result) => current && setData(result))
      .catch((err) => current && setError(err));
    return () => {
      current = false;
    };
  }, [lang, collection, query]);

  function update(next) {
    const merged = { collection, q: query, ...next };
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v)), { replace: true });
  }

  const total = data?.collections.reduce((n, c) => n + c.count, 0) ?? 0;
  return (
    <main>
      <div className="page-header">
        <div>
          <h1>{t("libraryTitle")}</h1>
          <p className="lead">{t("libraryIntro")}</p>
        </div>
      </div>
      <form
        className="card library-search"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          update({ q: text.trim() });
        }}
      >
        <div className="field" style={{ flex: "1 1 16rem", margin: 0 }}>
          <label htmlFor="lib-q">{t("librarySearch")}</label>
          <input
            id="lib-q"
            type="search"
            maxLength={100}
            placeholder={t("librarySearchHint")}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <button type="submit">
          <Search size={18} aria-hidden="true" />
          {t("search")}
        </button>
      </form>
      {data && (
        <div className="segmented library-filter" role="group" aria-label={t("libraryCollections")}>
          <button type="button" aria-pressed={!collection} onClick={() => update({ collection: "" })}>
            {t("allTopics")} ({total})
          </button>
          {data.collections.map((c) => (
            <button
              key={c.collection}
              type="button"
              aria-pressed={collection === c.collection}
              onClick={() => update({ collection: c.collection })}
            >
              {t(`collection_${c.collection}`)} ({c.count})
            </button>
          ))}
        </div>
      )}
      {error !== null && <ErrorMessage error={error} />}
      {data === null && error === null && <Loading />}
      {data && (
        <>
          <p className="muted small" aria-live="polite">
            {query ? t("libraryFound", { count: data.total, query }) : t("libraryCount", { count: data.total })}
          </p>
          {data.documents.length === 0 && (
            <div className="card empty">
              <span className="icon-tile" aria-hidden="true">
                <BookOpen size={22} />
              </span>
              <span>{t("libraryNone")}</span>
            </div>
          )}
          <ul className="library-list">
            {data.documents.map((d) => {
              const Icon = COLLECTION_ICON[d.collection] ?? FileText;
              return (
                <li key={`${d.collection}/${d.slug}`}>
                  <Link className="card library-item" to={`/library/${d.collection}/${d.slug}`}>
                    <span className="icon-tile" aria-hidden="true">
                      <Icon size={20} />
                    </span>
                    <span>
                      <strong>{d.title}</strong>
                      <span className="muted small"> · {t(`collection_${d.collection}`)}</span>
                      <span className="library-summary">{d.summary}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </main>
  );
}
