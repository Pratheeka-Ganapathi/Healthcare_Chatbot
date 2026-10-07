import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/ui/types.ts"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["@pipecat-ai/*"], message: "Only modules in src/transport/ may import the Pipecat SDK." }] },
      ],
    },
  },
  { files: ["src/transport/*.ts"], rules: { "no-restricted-imports": "off" } },
);
