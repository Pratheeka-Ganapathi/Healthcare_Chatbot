import type { Submitter } from "../lib/useSubmit";
import { Notice } from "./Notice";

/** The error or success line under a form. */
export function FormMessages({ submit }: { submit: Pick<Submitter, "error" | "success"> }) {
  if (submit.error) return <Notice tone="error">{submit.error}</Notice>;
  if (submit.success) return <Notice tone="success">{submit.success}</Notice>;
  return null;
}
