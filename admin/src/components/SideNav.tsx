import type { Role } from "../api/types";
import { HOME, type Route } from "../routing/routes";

interface NavLink {
  href: string;
  label: string;
}

const LINKS: Record<Role, NavLink[]> = {
  doctor: [{ href: "#/doctor/appointments", label: "Appointments" }],
  admin: [
    { href: "#/admin/overview", label: "Overview" },
    { href: "#/admin/appointments", label: "Appointments" },
    { href: "#/admin/doctors", label: "Doctors" },
    { href: "#/admin/accounts", label: "Accounts" },
    { href: "#/admin/clinic-info", label: "Clinic info" },
    { href: "#/admin/closures", label: "Closures" },
    { href: "#/admin/database", label: "Database" },
  ],
};

function activeHref(route: Route): string | null {
  switch (route.name) {
    case "doctor-appointments":
    case "doctor-appointment":
      return "#/doctor/appointments";
    case "admin-appointments":
    case "admin-appointment":
      return "#/admin/appointments";
    case "admin":
      return `#/admin/${route.section}`;
    default:
      return null;
  }
}

export function SideNav({ role, route }: { role: Role; route: Route }) {
  const active = activeHref(route);
  return (
    <nav className="sidenav" aria-label="Main">
      <a className="sidenav-brand" href={HOME[role]}>
        <span className="brand-mark" aria-hidden="true" />
        <span className="brand-text">
          <strong>City Care Clinic</strong>
          <small>Staff portal</small>
        </span>
      </a>
      <ul className="sidenav-links">
        {LINKS[role].map((link) => (
          <li key={link.href}>
            <a href={link.href} aria-current={link.href === active ? "page" : undefined}>
              {link.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
