import { describe, expect, it } from "vitest";

import { parseRoute, redirectFor } from "./routes";

describe("parseRoute", () => {
  it("parses every screen", () => {
    expect(parseRoute("#/login")).toEqual({ name: "login" });
    expect(parseRoute("#/account")).toEqual({ name: "account" });
    expect(parseRoute("#/doctor/appointments")).toEqual({
      name: "doctor-appointments",
      scope: null,
    });
    expect(parseRoute("#/doctor/appointments/12")).toEqual({ name: "doctor-appointment", id: 12 });
    expect(parseRoute("#/admin/appointments/7")).toEqual({ name: "admin-appointment", id: 7 });
    expect(parseRoute("#/admin/clinic-info")).toEqual({ name: "admin", section: "clinic-info" });
    expect(parseRoute("#/admin/database")).toEqual({ name: "admin", section: "database" });
  });

  it("reads query parameters", () => {
    expect(parseRoute("#/doctor/appointments?scope=past")).toEqual({
      name: "doctor-appointments",
      scope: "past",
    });
    expect(parseRoute("#/admin/appointments?day=2026-10-07")).toEqual({
      name: "admin-appointments",
      day: "2026-10-07",
    });
  });

  it("rejects bad paths and ids", () => {
    for (const hash of [
      "",
      "#/",
      "#/admin/nope",
      "#/doctor/appointments/abc",
      "#/admin/appointments/0",
      "#/login/x",
      "#/admin/overview/3",
    ]) {
      expect(parseRoute(hash)).toEqual({ name: "not-found" });
    }
  });
});

describe("redirectFor", () => {
  it("sends signed-out users to login", () => {
    expect(redirectFor(parseRoute("#/admin/overview"), null)).toBe("#/login");
    expect(redirectFor(parseRoute("#/login"), null)).toBeNull();
  });

  it("keeps each role on its own screens", () => {
    expect(redirectFor(parseRoute("#/admin/doctors"), "doctor")).toBe("#/doctor/appointments");
    expect(redirectFor(parseRoute("#/doctor/appointments/3"), "admin")).toBe("#/admin/overview");
    expect(redirectFor(parseRoute("#/login"), "admin")).toBe("#/admin/overview");
    expect(redirectFor(parseRoute("#/account"), "doctor")).toBeNull();
    expect(redirectFor(parseRoute("#/admin/closures"), "admin")).toBeNull();
  });
});
