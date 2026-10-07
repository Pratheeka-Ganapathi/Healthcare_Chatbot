import { deleteClosure, listClosures } from "../../api/client";
import type { Closure } from "../../api/types";
import { ClosureForm } from "../../components/ClosureForm";
import { Loadable } from "../../components/Loadable";
import { Notice } from "../../components/Notice";
import { PageHeader } from "../../components/PageHeader";
import { useApi } from "../../lib/useApi";
import { useSubmit } from "../../lib/useSubmit";

const byDate = (a: Closure, b: Closure) => a.date.localeCompare(b.date);

export function ClosuresScreen() {
  const state = useApi(listClosures, "closures");
  const removal = useSubmit();

  const added = (closure: Closure) => {
    state.replace([...(state.data ?? []), closure].sort(byDate));
  };

  const remove = (closure: Closure) => {
    if (
      !window.confirm(
        `Remove the closure on ${closure.date_label}? The day opens for booking again.`,
      )
    ) {
      return;
    }
    void removal.run(async () => {
      await deleteClosure(closure.id);
      state.replace((state.data ?? []).filter((c) => c.id !== closure.id));
      return `Closure on ${closure.date_label} removed.`;
    });
  };

  return (
    <>
      <PageHeader title="Closures" />
      <section className="card" aria-labelledby="add-closure-heading">
        <h2 id="add-closure-heading">Add a closure</h2>
        <p className="muted small">
          The chatbot stops offering slots on a closed day. Appointments already booked that day are
          not cancelled.
        </p>
        <ClosureForm onCreated={added} />
      </section>
      <h2 className="section-title">Upcoming closures</h2>
      {removal.error && <Notice tone="error">{removal.error}</Notice>}
      {removal.success && <Notice tone="success">{removal.success}</Notice>}
      <Loadable state={state}>
        {(closures) =>
          closures.length === 0 ? (
            <p className="empty">No closures from today onwards.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Reason</th>
                    <th scope="col">Booked appointments</th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {closures.map((closure) => (
                    <tr key={closure.id}>
                      <td className="nowrap">{closure.date_label}</td>
                      <td>{closure.reason}</td>
                      <td>
                        {closure.booked_appointments > 0 ? (
                          <span className="warning-text">
                            {closure.booked_appointments} booked — contact these patients
                          </span>
                        ) : (
                          <span className="muted">None</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-danger btn-small"
                          disabled={removal.busy}
                          onClick={() => remove(closure)}
                        >
                          Remove<span className="sr-only"> closure on {closure.date_label}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Loadable>
    </>
  );
}
