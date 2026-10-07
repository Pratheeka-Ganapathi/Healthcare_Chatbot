import type { DoctorCards } from "../ui/types";

interface Props {
  payload: DoctorCards;
  active: boolean;
  onSend: (text: string) => void;
}

export function DoctorCardList({ payload, active, onSend }: Props) {
  return (
    <ul className="doctors" aria-label="Doctors">
      {payload.doctors.map((doctor) => (
        <li key={doctor.name} className="doctor">
          <div className="doctor-main">
            <p className="doctor-name">{doctor.name}</p>
            <p className="doctor-meta">{doctor.specialty}</p>
            <p className="doctor-meta">
              {doctor.days}, {doctor.hours}
            </p>
          </div>
          <div className="doctor-side">
            <button
              type="button"
              className="chip chip-solid"
              disabled={!active}
              onClick={() => onSend(doctor.text)}
            >
              Choose
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
