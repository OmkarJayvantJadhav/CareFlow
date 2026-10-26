// Display helpers shared by the screens.

const LOCALES = { en: "en-IN", hi: "hi-IN", mr: "mr-IN" };

/** A calendar date from the API ("2026-10-24") read as a local date, never shifted by the time zone. */
function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function format(iso, lang, options) {
  return new Intl.DateTimeFormat(LOCALES[lang] ?? "en-IN", options).format(parseDate(iso));
}

/** "Sat, 24 Oct 2026" in the interface language. */
export function longDate(iso, lang) {
  return format(iso, lang, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

/** The parts of a calendar tile: month, day and weekday. */
export function dateTile(iso, lang) {
  return {
    month: format(iso, lang, { month: "short" }),
    day: format(iso, lang, { day: "numeric" }),
    weekday: format(iso, lang, { weekday: "short" }),
  };
}

/** "AP" for "Asha Patil"; titles like "Dr." are skipped. */
export function initials(name) {
  const words = (name || "")
    .replace(/\(.*?\)/g, " ")
    .split(/\s+/)
    .filter((w) => w && !/^(dr|mr|mrs|ms)\.?$/i.test(w));
  return words
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

/** [[department, doctors], ...] in the order the doctors come, for a <select> with <optgroup>s. */
export function byDepartment(doctors) {
  const groups = new Map();
  for (const d of doctors) {
    if (!groups.has(d.department)) groups.set(d.department, []);
    groups.get(d.department).push(d);
  }
  return [...groups.entries()];
}

/** "10:35" from an ISO timestamp, in the hospital's time zone. */
export function clockTime(iso) {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  }).format(new Date(iso));
}
