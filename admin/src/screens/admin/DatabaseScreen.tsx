import { useState } from "react";

import { listTables } from "../../api/client";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { TableBrowser } from "../../components/TableBrowser";
import { useApi } from "../../lib/useApi";

export function DatabaseScreen() {
  const state = useApi(listTables, "tables");
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <>
      <PageHeader title="Database" />
      <p className="muted">
        Read-only view of every table. Password hashes and sessions are never shown.
      </p>
      <Loadable state={state}>
        {(tables) => (
          <div className="split">
            <ul className="doc-list" aria-label="Tables">
              {tables.map((table) => (
                <li key={table.name}>
                  <button
                    type="button"
                    aria-current={table.name === selected ? "true" : undefined}
                    onClick={() => setSelected(table.name)}
                  >
                    <strong className="mono">{table.name}</strong>
                    <span className="muted small">
                      {table.row_count.toLocaleString("en-IN")} rows
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {selected ? (
              <TableBrowser key={selected} name={selected} />
            ) : (
              <p className="empty">Choose a table to see its rows.</p>
            )}
          </div>
        )}
      </Loadable>
    </>
  );
}
