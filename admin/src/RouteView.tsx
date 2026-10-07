import type { StaffUser } from "./api/types";
import type { Route } from "./routing/routes";
import { AccountScreen } from "./screens/AccountScreen";
import { AccountsScreen } from "./screens/admin/AccountsScreen";
import { AdminAppointmentScreen } from "./screens/admin/AdminAppointmentScreen";
import { AdminAppointmentsScreen } from "./screens/admin/AdminAppointmentsScreen";
import { ClinicInfoScreen } from "./screens/admin/ClinicInfoScreen";
import { ClosuresScreen } from "./screens/admin/ClosuresScreen";
import { DatabaseScreen } from "./screens/admin/DatabaseScreen";
import { DoctorsScreen } from "./screens/admin/DoctorsScreen";
import { OverviewScreen } from "./screens/admin/OverviewScreen";
import { DoctorAppointmentScreen } from "./screens/doctor/DoctorAppointmentScreen";
import { DoctorAppointmentsScreen } from "./screens/doctor/DoctorAppointmentsScreen";

interface Props {
  route: Route;
  user: StaffUser;
}

/** Maps a (role-checked) route to its screen. */
export function RouteView({ route, user }: Props) {
  switch (route.name) {
    case "account":
      return <AccountScreen />;
    case "doctor-appointments":
      return <DoctorAppointmentsScreen scope={route.scope} />;
    case "doctor-appointment":
      return <DoctorAppointmentScreen key={route.id} id={route.id} />;
    case "admin-appointments":
      return <AdminAppointmentsScreen day={route.day} />;
    case "admin-appointment":
      return <AdminAppointmentScreen key={route.id} id={route.id} />;
    case "admin":
      switch (route.section) {
        case "overview":
          return <OverviewScreen />;
        case "doctors":
          return <DoctorsScreen />;
        case "accounts":
          return <AccountsScreen currentUser={user} />;
        case "clinic-info":
          return <ClinicInfoScreen />;
        case "closures":
          return <ClosuresScreen />;
        case "database":
          return <DatabaseScreen />;
      }
      return null;
    default:
      return null;
  }
}
