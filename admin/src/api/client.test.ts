import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  deleteClosure,
  getMe,
  login,
  saveConsultation,
  setAuthToken,
  setUnauthorizedHandler,
} from "./client";

function reply(status: number, body?: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as Response;
}

const fetchMock = vi.fn<typeof fetch>();
const onUnauthorized = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  onUnauthorized.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  setAuthToken("tok-123");
  setUnauthorizedHandler(onUnauthorized);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setAuthToken(null);
  setUnauthorizedHandler(null);
});

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("api client", () => {
  it("sends the bearer token and a JSON body", async () => {
    fetchMock.mockResolvedValue(reply(200, { id: 4 }));
    await saveConsultation(4, {
      notes: "n",
      diagnosis: "d",
      medication: "",
      followup_required: false,
      followup_in_days: null,
    });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("http://localhost:8000/staff/doctor/appointments/4/consultation");
    expect(init?.method).toBe("PUT");
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok-123");
    expect(headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toMatchObject({ diagnosis: "d" });
  });

  it("treats 204 as no body", async () => {
    fetchMock.mockResolvedValue(reply(204));
    await expect(deleteClosure(9)).resolves.toBeUndefined();
  });

  it("uses a string detail as the message", async () => {
    fetchMock.mockResolvedValue(reply(409, { detail: "A closure already exists for that day." }));
    const error = await failure(deleteClosure(1));
    expect(error.status).toBe(409);
    expect(error.message).toBe("A closure already exists for that day.");
  });

  it("turns a 422 detail list into a readable message", async () => {
    fetchMock.mockResolvedValue(
      reply(422, {
        detail: [
          { loc: ["body", "new_password"], msg: "String should have at least 8 characters" },
          { loc: ["body"], msg: "Field required" },
        ],
      }),
    );
    const error = await failure(getMe());
    expect(error.status).toBe(422);
    expect(error.message).toBe(
      "New password: String should have at least 8 characters. Field required.",
    );
  });

  it("signs out on a 401 from a signed-in call", async () => {
    fetchMock.mockResolvedValue(reply(401, { detail: "Not signed in." }));
    await failure(getMe());
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it("does not sign out on a failed login", async () => {
    fetchMock.mockResolvedValue(reply(401, { detail: "Invalid email or password." }));
    const error = await failure(login({ email: "a@b.c", password: "wrongpass" }));
    expect(error.message).toBe("Invalid email or password.");
    expect(onUnauthorized).not.toHaveBeenCalled();
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("reports a network failure as status 0", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await failure(getMe());
    expect(error.status).toBe(0);
  });
});
