import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, setToken, setUnauthorizedHandler, type User } from "./api";
import { translate, type Key, type Lang } from "./i18n";

// Browser storage can be unavailable (private windows, blocked site data); the app works without it.
function load(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function save(key: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    /* not persisted */
  }
}

interface SessionState {
  user: User | null;
  lang: Lang;
  largeText: boolean;
  setLang: (lang: Lang) => void;
  setLargeText: (on: boolean) => void;
  signIn: (role: string) => Promise<User>;
  signOut: () => void;
  t: (key: Key, vars?: Record<string, string | number>) => string;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const stored = load("careflow.user");
    const storedToken = load("careflow.token");
    if (stored && storedToken) {
      setToken(storedToken);
      try {
        return JSON.parse(stored) as User;
      } catch {
        return null;
      }
    }
    return null;
  });
  const [lang, setLangState] = useState<Lang>(() => (load("careflow.lang") as Lang) || "en");
  const [largeText, setLargeTextState] = useState(() => load("careflow.large") === "1");

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    save("careflow.user", null);
    save("careflow.token", null);
  }, []);

  useEffect(() => setUnauthorizedHandler(signOut), [signOut]);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.classList.toggle("large-text", largeText);
  }, [lang, largeText]);

  const value = useMemo<SessionState>(
    () => ({
      user,
      lang,
      largeText,
      setLang: (next) => {
        setLangState(next);
        save("careflow.lang", next);
      },
      setLargeText: (on) => {
        setLargeTextState(on);
        save("careflow.large", on ? "1" : "0");
      },
      signIn: async (role) => {
        const data = await api<{ token: string; user: User }>("/auth/demo-login", { method: "POST", body: { role } });
        setToken(data.token);
        setUser(data.user);
        save("careflow.token", data.token);
        save("careflow.user", JSON.stringify(data.user));
        return data.user;
      },
      signOut,
      t: (key, vars) => translate(lang, key, vars),
    }),
    [user, lang, largeText, signOut],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
