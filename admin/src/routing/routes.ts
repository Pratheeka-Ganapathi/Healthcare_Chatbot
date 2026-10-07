// Hash routes. Pure functions so they are easy to test; useHashRoute wires them to the URL.
import type { Role } from "../api/types";

export type AdminSection =
  "overview" | "doctors" | "accounts" | "clinic-info" | "closures" | "database";

export type Route =
  | { name: "login" }
  | { name: "account" }
  | { name: "doctor-appointments"; scope: string | null }
  | { name: "doctor-appointment"; id: number }
  | { name: "admin-appointments"; day: string | null }
  | { name: "admin-appointment"; id: number }
  | { name: "admin"; section: AdminSection }
  | { name: "not-found" };

const ADMIN_SECTIONS: readonly AdminSection[] = [
  "overview",
  "doctors",
  "accounts",
  "clinic-info",
  "closures",
  "database",
];

export const HOME: Record<Role, string> = {
  admin: "#/admin/overview",
  doctor: "#/doctor/appointments",
};

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, "");
  const [pathPart = "", queryPart = ""] = raw.split("?", 2);
  const parts = pathPart.split("/").filter((part) => part !== "");
  const query = new URLSearchParams(queryPart);
  const [area, section, idPart, ...rest] = parts;
  if (rest.length > 0) return { name: "not-found" };
  const id = idPart === undefined ? null : parseId(idPart);

  if (parts.length === 0) return { name: "not-found" };
  if (area === "login" && parts.length === 1) return { name: "login" };
  if (area === "account" && parts.length === 1) return { name: "account" };

  if (area === "doctor" && section === "appointments") {
    if (idPart === undefined) return { name: "doctor-appointments", scope: query.get("scope") };
    return id === null ? { name: "not-found" } : { name: "doctor-appointment", id };
  }
  if (area === "admin" && section === "appointments") {
    if (idPart === undefined) return { name: "admin-appointments", day: query.get("day") };
    return id === null ? { name: "not-found" } : { name: "admin-appointment", id };
  }
  if (area === "admin" && idPart === undefined && isAdminSection(section)) {
    return { name: "admin", section };
  }
  return { name: "not-found" };
}

function parseId(part: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(part)) return null;
  return Number(part);
}

function isAdminSection(value: string | undefined): value is AdminSection {
  return ADMIN_SECTIONS.some((section) => section === value);
}

/** Which role a route belongs to; "any" is open to every signed-in user, "public" to nobody signed in. */
export function routeAccess(route: Route): Role | "any" | "public" {
  switch (route.name) {
    case "login":
      return "public";
    case "account":
    case "not-found":
      return "any";
    case "doctor-appointments":
    case "doctor-appointment":
      return "doctor";
    default:
      return "admin";
  }
}

/** The hash to redirect to, or null when the route may be shown as is. */
export function redirectFor(route: Route, role: Role | null): string | null {
  const access = routeAccess(route);
  if (role === null) return access === "public" ? null : "#/login";
  if (route.name === "not-found" || access === "public") return HOME[role];
  if (access !== "any" && access !== role) return HOME[role];
  return null;
}
