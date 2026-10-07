// Mirrors SPEC §17.5. Times are ISO 8601 with the IST offset; money is whole rupees.

export type Role = "admin" | "doctor";

export interface StaffUser {
  id: number;
  email: string;
  name: string;
  role: Role;
  doctor_id: number | null;
  doctor_name: string | null;
  active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export type Sex = "female" | "male" | "other";

export interface PatientRef {
  id: number;
  name: string;
  age: number;
  sex: Sex;
}

export interface PatientDetail extends PatientRef {
  phone: string;
  dob: string;
}

export type VisitType = "new" | "followup";

export type AppointmentStatus = "booked" | "cancelled" | "completed" | "no_show";

/** The statuses a doctor may set. `cancelled` is only ever set by the patient through the bot. */
export type EditableStatus = Exclude<AppointmentStatus, "cancelled">;

export interface AppointmentSummary {
  id: number;
  start: string;
  end: string;
  date_label: string;
  time_label: string;
  doctor_id: number;
  doctor_name: string;
  patient: PatientRef;
  visit_type: VisitType;
  status: AppointmentStatus;
  chief_complaint: string | null;
  has_consultation: boolean;
}

export interface IntakeAnswer {
  q: string;
  a: string;
}

export interface Intake {
  chief_complaint: string;
  duration: string | null;
  severity: number | null;
  answers: IntakeAnswer[];
  red_flags_checked: string[];
}

export interface Consultation {
  notes: string;
  diagnosis: string;
  medication: string;
  followup_required: boolean;
  followup_in_days: number | null;
  /** A date, YYYY-MM-DD. */
  followup_valid_until: string | null;
  submitted_by: string;
  created_at: string;
  updated_at: string;
}

export interface HistoryItem {
  appointment_id: number;
  date_label: string;
  doctor_name: string;
  diagnosis: string;
  notes: string;
  medication: string;
  followup_required: boolean;
}

export interface ChatSummary {
  id: number;
  summary: string;
  created_at: string;
}

export interface AppointmentDetail extends Omit<AppointmentSummary, "patient"> {
  fee_rupees: number;
  patient: PatientDetail;
  intake: Intake | null;
  consultation: Consultation | null;
  chat_summaries: ChatSummary[];
  history: HistoryItem[];
  /** False when cancelled or on a later day. */
  can_record: boolean;
}

export interface DoctorAccountRef {
  id: number;
  email: string;
  active: boolean;
}

export interface Doctor {
  id: number;
  name: string;
  specialty: string;
  specialty_label: string;
  bio: string;
  /** 0 = Monday. */
  consulting_days: number[];
  days_label: string;
  hours: string;
  fee_rupees: number;
  followup_fee_rupees: number;
  account: DoctorAccountRef | null;
}

export interface ClinicDoc {
  name: string;
  title: string;
  content: string;
  updated_at: string | null;
  updated_by: string | null;
}

export interface Closure {
  id: number;
  date: string;
  date_label: string;
  reason: string;
  booked_appointments: number;
}

export interface TableInfo {
  name: string;
  row_count: number;
}

export type Cell = string | number | boolean | null;

export interface TablePage {
  name: string;
  columns: string[];
  rows: Cell[][];
  total: number;
  offset: number;
  limit: number;
}

export interface Overview {
  patients: number;
  doctors: number;
  appointments_today: number;
  upcoming_appointments: number;
  consultations: number;
  chat_summaries: number;
  callbacks: number;
}

// Request and response bodies.

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: StaffUser;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export type AppointmentScope = "today" | "upcoming" | "past";

export interface IntakeUpdate {
  chief_complaint: string;
  duration: string | null;
  severity: number | null;
}

export interface AppointmentUpdate {
  status?: EditableStatus;
  intake?: IntakeUpdate;
}

export interface ConsultationRequest {
  notes: string;
  diagnosis: string;
  medication: string;
  followup_required: boolean;
  followup_in_days: number | null;
}

export interface DoctorUpdate {
  name: string;
  bio: string;
  fee_rupees: number;
  followup_fee_rupees: number;
}

export interface AccountCreate {
  email: string;
  name: string;
  password: string;
  doctor_id: number;
}

export interface AccountUpdate {
  name?: string;
  active?: boolean;
  password?: string;
}

export interface ClosureCreate {
  date: string;
  reason: string;
}
