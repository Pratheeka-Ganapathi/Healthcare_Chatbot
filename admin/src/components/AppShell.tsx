import type { ReactNode } from "react";

import type { StaffUser } from "../api/types";
import type { Route } from "../routing/routes";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";

interface Props {
  user: StaffUser;
  route: Route;
  onSignOut: () => void;
  children: ReactNode;
}

export function AppShell({ user, route, onSignOut, children }: Props) {
  return (
    <div className="app">
      <SideNav role={user.role} route={route} />
      <div className="app-main">
        <TopBar user={user} onSignOut={onSignOut} />
        <main className="content">{children}</main>
        <footer className="demo-footer">Demo with synthetic data.</footer>
      </div>
    </div>
  );
}
