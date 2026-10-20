import { AlertCircle } from "lucide-react";
import { ApiError } from "../api";
import { useSession } from "../session";

const KNOWN = new Set([
  "RATE_LIMITED",
  "LLM_UNAVAILABLE",
  "FORBIDDEN",
  "UNAUTHORIZED",
  "UNSAFE_QUERY",
  "INVALID_CREDENTIALS",
  "USERNAME_TAKEN",
]);

/** Plain-language error with a next step; never a bare code (docs §8). */
export function useErrorText() {
  const { t, lang } = useSession();
  return (error) => {
    if (error instanceof ApiError) {
      if (error.code === "NETWORK") return t("error_network");
      if (KNOWN.has(error.code)) return t(`error_${error.code}`);
      // Rule messages from the server ("This slot was just taken…") are plain English sentences.
      if (lang === "en" && error.message) return error.message;
      return error.message ? `${t("error_generic")} (${error.message})` : t("error_generic");
    }
    return t("error_generic");
  };
}

export default function ErrorMessage({ error, onRetry }) {
  const { t } = useSession();
  const text = useErrorText()(error);
  return (
    <div className="error" role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <div>
        {text}
        {onRetry && (
          <>
            {" "}
            <button type="button" className="link-button" onClick={onRetry}>
              {t("retry")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
