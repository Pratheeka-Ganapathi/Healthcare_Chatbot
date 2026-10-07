import { useState } from "react";

import { listClinicDocs } from "../../api/client";
import type { ClinicDoc } from "../../api/types";
import { ClinicDocEditor } from "../../components/ClinicDocEditor";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { useApi } from "../../lib/useApi";

export function ClinicInfoScreen() {
  const state = useApi(listClinicDocs, "clinic-docs");
  const [selected, setSelected] = useState<string | null>(null);
  // null means "no edits": the editor shows the saved content.
  const [draft, setDraft] = useState<string | null>(null);

  const saved = (doc: ClinicDoc) => {
    state.replace((state.data ?? []).map((d) => (d.name === doc.name ? doc : d)));
    setDraft(null);
  };

  return (
    <>
      <PageHeader title="Clinic information" />
      <p className="muted">
        These documents are what the chatbot uses to answer questions about the clinic: timings,
        services, insurance and test preparation.
      </p>
      <Loadable state={state}>
        {(docs) => {
          const current = docs.find((d) => d.name === selected) ?? docs[0];
          if (!current) return <p className="empty">No documents found.</p>;
          const dirty = draft !== null && draft !== current.content;
          const choose = (name: string) => {
            if (name === current.name) return;
            if (dirty && !window.confirm("Discard your unsaved changes to this document?")) return;
            setSelected(name);
            setDraft(null);
          };
          return (
            <div className="split">
              <ul className="doc-list" aria-label="Documents">
                {docs.map((doc) => (
                  <li key={doc.name}>
                    <button
                      type="button"
                      aria-current={doc.name === current.name ? "true" : undefined}
                      onClick={() => choose(doc.name)}
                    >
                      <strong>{doc.title}</strong>
                      <span className="muted small">{doc.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <ClinicDocEditor
                key={current.name}
                doc={current}
                draft={draft ?? current.content}
                onDraftChange={setDraft}
                onSaved={saved}
              />
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
