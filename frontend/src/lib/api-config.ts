/**
 * Centralized API configuration for CHAI frontend.
 * Reads VITE_API_BASE_URL if configured, otherwise defaults to local FastAPI server on port 8000.
 */
export const API_BASE: string =
  ((import.meta as any).env?.VITE_API_BASE_URL as string) || "http://localhost:8000";
