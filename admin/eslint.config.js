import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Only src/api/client.ts may call fetch." },
      ],
    },
  },
  { files: ["src/api/client.ts", "src/api/*.test.ts"], rules: { "no-restricted-globals": "off" } },
);
