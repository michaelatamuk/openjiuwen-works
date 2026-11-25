import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["node_modules/**", "dist/**", "test-results/**", "playwright-report/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // The compiler-era rule flags intentional sync state in effects (scroll and tab resets).
      "react-hooks/set-state-in-effect": "warn",
      // Focus is moved on purpose in the sign-in gate and the command palette.
      "jsx-a11y/no-autofocus": "off",
    },
  },
  {
    files: ["src/test/**/*.ts"],
    rules: {
      // Canonicalized API snapshots: the cast happens once, at the test boundary.
      "@typescript-eslint/no-explicit-any": "off",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "e2e/**/*.ts", "vitest.setup.ts"],
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
      "jsx-a11y/no-autofocus": "off",
    },
  },
);
