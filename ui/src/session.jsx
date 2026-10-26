import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setToken, setUnauthorizedHandler } from "./api";
import { translate } from "./i18n";

// Browser storage can be unavailable (private windows, blocked site data); the app works without it.
function load(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function save(key, value) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    /* not persisted */
  }
}

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = load("careflow.user");
    const storedToken = load("careflow.token");
    if (stored && storedToken) {
      setToken(storedToken);
      try {
        return JSON.parse(stored);
      } catch {
        return null;
      }
    }
    return null;
  });
  const [lang, setLangState] = useState(() => load("careflow.lang") || "en");
  const [largeText, setLargeTextState] = useState(() => load("careflow.large") === "1");
  // What this deployment offers (demo roles, sign-up); null until known, and then demo features stay hidden.
  const [config, setConfig] = useState(null);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    save("careflow.user", null);
    save("careflow.token", null);
  }, []);

  const accept = useCallback((data) => {
    setToken(data.token);
    setUser(data.user);
    save("careflow.token", data.token);
    save("careflow.user", JSON.stringify(data.user));
    return data.user;
  }, []);

  useEffect(() => setUnauthorizedHandler(signOut), [signOut]);
  useEffect(() => {
    let current = true;
    api("/config")
      .then((c) => current && setConfig(c))
      .catch(() => current && setConfig({ demo_mode: false, allow_registration: true }));
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.classList.toggle("large-text", largeText);
  }, [lang, largeText]);

  /** Re-read the signed-in user (after a profile change, so names update everywhere). */
  const refreshUser = useCallback(async () => {
    const fresh = await api("/me");
    setUser(fresh);
    save("careflow.user", JSON.stringify(fresh));
    return fresh;
  }, []);

  const value = useMemo(
    () => ({
      user,
      config,
      demo: config?.demo_mode === true,
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
      signIn: async (role) => accept(await api("/auth/demo-login", { method: "POST", body: { role } })),
      logIn: async (username, password) =>
        accept(await api("/auth/login", { method: "POST", body: { username, password } })),
      register: async (details) => accept(await api("/auth/register", { method: "POST", body: details })),
      refreshUser,
      /** A new password ends every earlier sign-in, this one included; carry on with the token that comes back. */
      changePassword: async (current, next) => {
        const result = await api("/me/password", {
          method: "POST",
          body: { current_password: current, new_password: next },
        });
        setToken(result.token);
        save("careflow.token", result.token);
        return refreshUser();
      },
      signOut,
      t: (key, vars) => translate(lang, key, vars),
    }),
    [user, config, lang, largeText, signOut, accept, refreshUser],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
