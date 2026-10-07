// The only module that calls fetch. One typed function per endpoint in SPEC §17.5.
import { API_URL } from "../config";
import type {
  AccountCreate,
  AccountUpdate,
  AppointmentDetail,
  AppointmentScope,
  AppointmentSummary,
  AppointmentUpdate,
  ChangePasswordRequest,
  ClinicDoc,
  Closure,
  ClosureCreate,
  ConsultationRequest,
  Doctor,
  DoctorUpdate,
  LoginRequest,
  LoginResponse,
  Overview,
  StaffUser,
  TableInfo,
  TablePage,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let authToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

/** Called when a signed-in request gets a 401: the app clears the session and shows the login. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

const LOGIN_PATH = "/staff/auth/login";

const FALLBACK_MESSAGES: Record<number, string> = {
  0: "Could not reach the server. Check your connection and try again.",
  401: "Your session has ended. Please sign in again.",
  403: "You do not have access to this.",
  404: "Not found.",
  409: "This conflicts with the current data. Reload and try again.",
  429: "Too many attempts. Please wait and try again.",
};

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const sentToken = path === LOGIN_PATH ? null : authToken;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (sentToken) headers.Authorization = `Bearer ${sentToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, messageFor(0));
  }

  const text = response.status === 204 ? "" : await response.text();
  const payload = parseJson(text);

  if (!response.ok) {
    // Only sign out when the token that failed is still the current one; a late reply
    // from an older session must not end a newer one.
    if (response.status === 401 && sentToken !== null && sentToken === authToken) {
      unauthorizedHandler?.();
    }
    throw new ApiError(response.status, errorMessage(payload, response.status));
  }
  return payload as T;
}

function parseJson(text: string): unknown {
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}

function messageFor(status: number): string {
  return FALLBACK_MESSAGES[status] ?? `The server returned an error (${status}). Please try again.`;
}

/** Turns `{detail: string}` or FastAPI's 422 `{detail: [{loc, msg}]}` into one readable message. */
export function errorMessage(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail: unknown = payload.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const parts = detail.map(validationMessage).filter((part) => part !== "");
      if (parts.length > 0) return parts.join(" ");
    }
  }
  return messageFor(status);
}

function validationMessage(item: unknown): string {
  if (typeof item !== "object" || item === null) return "";
  const msg = "msg" in item && typeof item.msg === "string" ? item.msg : "";
  if (!msg) return "";
  const loc = "loc" in item && Array.isArray(item.loc) ? (item.loc as unknown[]) : [];
  const field = loc.filter((part) => typeof part === "string" && !LOC_ROOTS.has(part)).pop();
  const sentence = msg.endsWith(".") ? msg : `${msg}.`;
  if (typeof field !== "string") return sentence;
  const label = field.replace(/_/g, " ");
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}: ${sentence}`;
}

const LOC_ROOTS = new Set(["body", "query", "path", "header"]);

const json = (method: RequestOptions["method"], body?: unknown): RequestOptions => ({
  method,
  body,
});

// Auth and own account

export const login = (body: LoginRequest) => request<LoginResponse>(LOGIN_PATH, json("POST", body));

export const logout = () => request<undefined>("/staff/auth/logout", json("POST"));

export const getMe = () => request<StaffUser>("/staff/me");

export const changePassword = (body: ChangePasswordRequest) =>
  request<undefined>("/staff/me/password", json("POST", body));

// Doctor

export const listDoctorAppointments = (scope: AppointmentScope) =>
  request<AppointmentSummary[]>(`/staff/doctor/appointments?scope=${scope}`);

export const getDoctorAppointment = (id: number) =>
  request<AppointmentDetail>(`/staff/doctor/appointments/${id}`);

export const updateDoctorAppointment = (id: number, body: AppointmentUpdate) =>
  request<AppointmentDetail>(`/staff/doctor/appointments/${id}`, json("PATCH", body));

export const saveConsultation = (id: number, body: ConsultationRequest) =>
  request<AppointmentDetail>(`/staff/doctor/appointments/${id}/consultation`, json("PUT", body));

// Admin

export const getOverview = () => request<Overview>("/staff/admin/overview");

export const listAdminAppointments = (day?: string) =>
  request<AppointmentSummary[]>(
    day ? `/staff/admin/appointments?day=${encodeURIComponent(day)}` : "/staff/admin/appointments",
  );

export const getAdminAppointment = (id: number) =>
  request<AppointmentDetail>(`/staff/admin/appointments/${id}`);

export const listDoctors = () => request<Doctor[]>("/staff/admin/doctors");

export const updateDoctor = (id: number, body: DoctorUpdate) =>
  request<Doctor>(`/staff/admin/doctors/${id}`, json("PUT", body));

export const listAccounts = () => request<StaffUser[]>("/staff/admin/accounts");

export const createAccount = (body: AccountCreate) =>
  request<StaffUser>("/staff/admin/accounts", json("POST", body));

export const updateAccount = (id: number, body: AccountUpdate) =>
  request<StaffUser>(`/staff/admin/accounts/${id}`, json("PATCH", body));

export const listClinicDocs = () => request<ClinicDoc[]>("/staff/admin/clinic-docs");

export const updateClinicDoc = (name: string, content: string) =>
  request<ClinicDoc>(
    `/staff/admin/clinic-docs/${encodeURIComponent(name)}`,
    json("PUT", { content }),
  );

export const listClosures = () => request<Closure[]>("/staff/admin/closures");

export const createClosure = (body: ClosureCreate) =>
  request<Closure>("/staff/admin/closures", json("POST", body));

export const deleteClosure = (id: number) =>
  request<undefined>(`/staff/admin/closures/${id}`, json("DELETE"));

export const listTables = () => request<TableInfo[]>("/staff/admin/tables");

export const getTablePage = (name: string, offset: number, limit: number) =>
  request<TablePage>(
    `/staff/admin/tables/${encodeURIComponent(name)}?offset=${offset}&limit=${limit}`,
  );
