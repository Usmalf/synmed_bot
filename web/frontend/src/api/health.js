import { apiGet } from "./client";

export function fetchHealth() {
  return apiGet("/health");
}
