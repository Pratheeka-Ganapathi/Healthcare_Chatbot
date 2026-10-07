import { useState } from "react";

import { listDoctors } from "../../api/client";
import type { Doctor } from "../../api/types";
import { DoctorEditForm } from "../../components/DoctorEditForm";
import { Loadable } from "../../components/Loadable";
import { PageHeader } from "../../components/PageHeader";
import { formatRupees } from "../../lib/format";
import { useApi } from "../../lib/useApi";

function AccountCell({ doctor }: { doctor: Doctor }) {
  if (!doctor.account) return <span className="muted">No login</span>;
  return (
    <>
      {doctor.account.email}{" "}
      {!doctor.account.active && <span className="badge badge-cancelled">Inactive</span>}
    </>
  );
}

export function DoctorsScreen() {
  const state = useApi(listDoctors, "doctors");
  const [editingId, setEditingId] = useState<number | null>(null);

  const saved = (doctor: Doctor) => {
    state.replace((state.data ?? []).map((d) => (d.id === doctor.id ? doctor : d)));
  };

  return (
    <>
      <PageHeader title="Doctors" />
      <Loadable state={state}>
        {(doctors) => {
          const editing = doctors.find((d) => d.id === editingId);
          return (
            <>
              {editing && (
                <DoctorEditForm
                  key={editing.id}
                  doctor={editing}
                  onSaved={saved}
                  onClose={() => setEditingId(null)}
                />
              )}
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th scope="col">Name</th>
                      <th scope="col">Specialty</th>
                      <th scope="col">Days and hours</th>
                      <th scope="col" className="num">
                        Fee
                      </th>
                      <th scope="col" className="num">
                        Follow-up fee
                      </th>
                      <th scope="col">Login account</th>
                      <th scope="col">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {doctors.map((doctor) => (
                      <tr
                        key={doctor.id}
                        className={doctor.id === editingId ? "row-selected" : undefined}
                      >
                        <td>{doctor.name}</td>
                        <td>{doctor.specialty_label}</td>
                        <td>
                          {doctor.days_label}
                          <br />
                          <span className="muted small">{doctor.hours}</span>
                        </td>
                        <td className="num">{formatRupees(doctor.fee_rupees)}</td>
                        <td className="num">{formatRupees(doctor.followup_fee_rupees)}</td>
                        <td>
                          <AccountCell doctor={doctor} />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-secondary btn-small"
                            onClick={() => setEditingId(doctor.id)}
                          >
                            Edit<span className="sr-only"> {doctor.name}</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          );
        }}
      </Loadable>
    </>
  );
}
