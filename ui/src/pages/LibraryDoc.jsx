import { ArrowLeft, CalendarCheck, FileText, MessageCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";
import { longDate } from "../format";
import { LANGS } from "../i18n";
import { useSession } from "../session";
import { COLLECTION_ICON } from "./Library";

/** A section body: paragraphs, and "- " lines as a list. React escapes the text, so no markup gets in. */
function Body({ text }) {
  const blocks = [];
  for (const line of text.split("\n")) {
    if (line.startsWith("- ")) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "list") last.items.push(line.slice(2));
      else blocks.push({ type: "list", items: [line.slice(2)] });
    } else if (line.trim()) {
      blocks.push({ type: "p", text: line });
    }
  }
  return blocks.map((b, i) =>
    b.type === "list" ? (
      <ul key={i}>
        {b.items.map((item, j) => (
          <li key={j}>{item}</li>
        ))}
      </ul>
    ) : (
      <p key={i}>{b.text}</p>
    ),
  );
}

/** One document from the information library, in the interface language. */
export default function LibraryDoc() {
  const { collection, slug } = useParams();
  const { user, lang, setLang, t } = useSession();
  const [doc, setDoc] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let current = true;
    setError(null);
    api(`/library/${encodeURIComponent(collection)}/${encodeURIComponent(slug)}?language=${lang}`)
      .then((result) => current && setDoc(result))
      .catch((err) => current && setError(err));
    return () => {
      current = false;
    };
  }, [collection, slug, lang]);

  const Icon = COLLECTION_ICON[collection] ?? FileText;
  const patient = user?.role === "patient" || user?.role === "caregiver";
  return (
    <main className="narrow">
      <Link to="/library" className="back-link">
        <ArrowLeft size={16} aria-hidden="true" />
        {t("libraryBack")}
      </Link>
      {error !== null && <ErrorMessage error={error} />}
      {doc === null && error === null && <Loading />}
      {doc && (
        <article className="card library-doc" lang={doc.language}>
          <div className="library-doc-head">
            <span className="icon-tile" aria-hidden="true">
              <Icon size={22} />
            </span>
            <div>
              <span className="eyebrow">{t(`collection_${doc.collection}`)}</span>
              <h1>{doc.title}</h1>
              <p className="muted small">{t("verifiedOn", { date: longDate(doc.last_verified, lang) })}</p>
            </div>
          </div>
          {doc.languages.length > 1 && (
            <div className="segmented" role="group" aria-label={t("readIn")}>
              {LANGS.filter((l) => doc.languages.includes(l.code)).map((l) => (
                <button
                  key={l.code}
                  type="button"
                  lang={l.code}
                  aria-pressed={lang === l.code}
                  onClick={() => setLang(l.code)}
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
          {doc.sections.map((s) => (
            <section key={s.heading}>
              <h2>{s.heading}</h2>
              <Body text={s.body} />
            </section>
          ))}
          <div className="library-doc-foot">
            <p className="muted small">{t("libraryDisclaimer")}</p>
            {patient && (
              <div className="row">
                <Link className="button secondary" to="/chat">
                  <MessageCircle size={16} aria-hidden="true" />
                  {t("askAssistant")}
                </Link>
                <Link className="button secondary" to="/book">
                  <CalendarCheck size={16} aria-hidden="true" />
                  {t("navBook")}
                </Link>
              </div>
            )}
          </div>
        </article>
      )}
    </main>
  );
}
