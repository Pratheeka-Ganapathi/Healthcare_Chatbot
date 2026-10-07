import { useState } from "react";

import { getTablePage } from "../api/client";
import { useApi } from "../lib/useApi";
import { DataGrid } from "./DataGrid";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { Pager } from "./Pager";

const PAGE_SIZE = 50;

export function TableBrowser({ name }: { name: string }) {
  const [offset, setOffset] = useState(0);
  const state = useApi(() => getTablePage(name, offset, PAGE_SIZE), `${name}:${offset}`, {
    keepPrevious: true,
  });
  const page = state.data;

  return (
    <section className="card table-browser" aria-labelledby="table-browser-heading">
      <h2 id="table-browser-heading" className="mono">
        {name}
      </h2>
      {state.error && <ErrorState message={state.error} onRetry={state.reload} />}
      {!page && !state.error && <LoadingState />}
      {page && (
        <>
          <Pager
            offset={page.offset}
            limit={PAGE_SIZE}
            shown={page.rows.length}
            total={page.total}
            busy={state.loading}
            onChange={setOffset}
          />
          <DataGrid page={page} />
        </>
      )}
    </section>
  );
}
