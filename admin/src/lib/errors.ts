import { ApiError } from "../api/client";

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}
