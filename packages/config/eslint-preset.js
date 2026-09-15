/**
 * Shared ESLint flat-config base for Infinity Radius JS/TS packages.
 * App-level configs (e.g. apps/web/eslint.config.mjs) spread this in and
 * layer framework-specific rules (Next.js, React) on top.
 */
const baseConfig = [
  {
    ignores: [
      "**/node_modules/**",
      "**/.next/**",
      "**/.turbo/**",
      "**/dist/**",
      "**/build/**",
      "**/coverage/**",
    ],
  },
  {
    rules: {
      "no-unused-vars": "off",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["error", "always"],
      "prefer-const": "error",
    },
  },
];

module.exports = baseConfig;
