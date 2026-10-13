import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import tseslint from "typescript-eslint";
import globals from "globals";

export default tseslint.config(
  { ignores: ["dist/", "node_modules/"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...svelte.configs["flat/recommended"],
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, __APP_VERSION__: "readonly" },
    },
  },
  {
    files: ["**/*.svelte"],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    files: ["**/*.ts"],
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
);
