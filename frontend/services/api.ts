/**
 * Thin wrapper around the backend API. No secrets belong in this file
 * or anywhere in frontend code — broker/API keys stay server-side only.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function getHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}
