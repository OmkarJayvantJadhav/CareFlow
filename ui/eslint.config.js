// Lint rules for the UI: JavaScript recommended rules, React (JSX) and the rules of hooks.
import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/"] },
  js.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: { globals: { ...globals.browser, ...globals.node, ...globals.vitest } },
    plugins: { "react-hooks": reactHooks },
    settings: { react: { version: "18.3" } },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react/prop-types": "off",
    },
  },
];
