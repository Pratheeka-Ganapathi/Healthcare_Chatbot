import { useEffect, type FormEvent } from "react";

import { updateClinicDoc } from "../api/client";
import type { ClinicDoc } from "../api/types";
import { formatDateTime } from "../lib/format";
import { useSubmit } from "../lib/useSubmit";
import { FormMessages } from "./FormMessages";

interface Props {
  doc: ClinicDoc;
  draft: string;
  onDraftChange: (content: string) => void;
  onSaved: (doc: ClinicDoc) => void;
}

export function ClinicDocEditor({ doc, draft, onDraftChange, onSaved }: Props) {
  const submit = useSubmit();
  const dirty = draft !== doc.content;

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!draft.trim()) return submit.fail("The document cannot be empty.");
    void submit.run(async () => {
      const saved = await updateClinicDoc(doc.name, draft);
      onSaved(saved);
      return "Saved — the chatbot uses the new text from the next question.";
    });
  };

  return (
    <form className="form editor" onSubmit={onSubmit}>
      <div className="editor-head">
        <h2>{doc.title}</h2>
        <p className="muted small">
          {doc.name} · last saved {formatDateTime(doc.updated_at)}
          {doc.updated_by ? ` by ${doc.updated_by}` : ""}
          {dirty && <strong className="unsaved"> · Unsaved changes</strong>}
        </p>
      </div>
      <div className="field">
        <label htmlFor="clinic-doc-content">Document text (Markdown)</label>
        <textarea
          id="clinic-doc-content"
          className="mono"
          rows={24}
          spellCheck
          value={draft}
          disabled={submit.busy}
          onChange={(e) => {
            onDraftChange(e.target.value);
            submit.clear();
          }}
          aria-describedby="clinic-doc-hint"
        />
        <p className="hint" id="clinic-doc-hint">
          Start each section with a <code># Heading</code> line. The chatbot answers questions from
          one section at a time, so keep each section about one topic.
        </p>
      </div>
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={submit.busy || !dirty}>
          {submit.busy ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          disabled={submit.busy || !dirty}
          onClick={() => onDraftChange(doc.content)}
        >
          Discard changes
        </button>
      </div>
      <FormMessages submit={submit} />
    </form>
  );
}
