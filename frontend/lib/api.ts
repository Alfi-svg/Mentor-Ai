/**
 * Safe client-side API fetch wrapper for Mentor AI backend.
 */

export interface HealthStatus {
  status: string;
  version: string;
  environment: string;
  ai_provider: string;
  timestamp: string;
}

export interface ReadinessStatus {
  status: string;
  database: string;
  ai_service: string;
  details: Record<string, unknown>;
  timestamp: string;
}

import { getApiBaseUrl } from "./api-client";

const API_BASE_URL = getApiBaseUrl();

export async function fetchHealth(): Promise<HealthStatus | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      headers: {
        "Accept": "application/json",
      },
      // short timeout for liveness check
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });

    if (!res.ok) {
      return null;
    }

    return (await res.json()) as HealthStatus;
  } catch (err) {
    console.warn("Unable to reach Mentor AI backend health probe:", err);
    return null;
  }
}

export async function fetchReadiness(): Promise<ReadinessStatus | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/health/ready`, {
      method: "GET",
      headers: {
        "Accept": "application/json",
      },
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });

    if (!res.ok) {
      return null;
    }

    return (await res.json()) as ReadinessStatus;
  } catch (err) {
    console.warn("Unable to reach Mentor AI backend readiness probe:", err);
    return null;
  }
}
