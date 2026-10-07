import { useEffect, useState } from "react";

import { API_URL } from "../config";

interface DemoPatient {
  name: string;
  phone: string;
  dob: string;
  note: string;
}

export function DemoNotice() {
  return (
    <p className="demo-notice" role="note">
      Demo with synthetic data. Do not enter real health information.
    </p>
  );
}

/** Collapsible list of synthetic test patients from GET /config/demo. */
export function TryItPanel({ onUse }: { onUse: (text: string) => void }) {
  const [patients, setPatients] = useState<DemoPatient[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${API_URL}/config/demo`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : { patients: [] }))
      .then((data: { patients: DemoPatient[] }) => setPatients(data.patients))
      .catch(() => setPatients([]));
    return () => controller.abort();
  }, []);

  if (patients.length === 0) return null;
  return (
    <details className="try-it">
      <summary>Try it with a test patient</summary>
      <ul>
        {patients.map((p) => (
          <li key={p.phone}>
            <div>
              <strong>{p.name}</strong>
              <span className="try-note">{p.note}</span>
              <span className="try-creds">
                Phone {p.phone}, date of birth {p.dob}
              </span>
            </div>
            <button type="button" className="chip" onClick={() => onUse(`${p.phone}, ${p.dob}`)}>
              Use details
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
