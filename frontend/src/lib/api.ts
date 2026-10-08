export const getApiBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    const envUrl = (import.meta as any).env?.VITE_API_URL;
    if (envUrl) return envUrl;
    // In local dev on Vite port 3000/5173, point to FastAPI on port 8000
    if (
      window.location.hostname === "localhost" &&
      (window.location.port === "3000" || window.location.port === "5173")
    ) {
      return "http://localhost:8000";
    }
    // In Dockerized Render deployment, use origin relative path
    return "";
  }
  return "http://localhost:8000";
};
