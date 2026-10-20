import { STRINGS, translate } from "./i18n";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("interface text", () => {
  it("has every string in English, Hindi and Marathi with the same placeholders", () => {
    const keys = Object.keys(STRINGS.en) as (keyof typeof STRINGS.en)[];
    for (const lang of ["hi", "mr"] as const) {
      for (const key of keys) {
        expect(STRINGS[lang][key], `${lang}.${key}`).toBeTruthy();
        expect(placeholders(STRINGS[lang][key]), `${lang}.${key}`).toEqual(placeholders(STRINGS.en[key]));
      }
    }
  });

  it("fills placeholders", () => {
    expect(translate("en", "cardExpires", { minutes: 4 })).toBe("This card expires in 4 min.");
    expect(translate("mr", "affected", { count: 2 })).toBe("कळवलेले रुग्ण: 2");
  });
});
