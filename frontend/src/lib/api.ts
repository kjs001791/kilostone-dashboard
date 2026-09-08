const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

let _accessToken: string | null = null;

export const tokenStore = {
  get: () => _accessToken,
  set: (token: string | null) => { _accessToken = token; },
};

async function refreshAccessToken(): Promise<string | null> {
  const res = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.access_token ?? null;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = tokenStore.get();

  const makeRequest = (accessToken: string | null) =>
    fetch(`${BASE_URL}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(options.headers ?? {}),
      },
    });

  let res = await makeRequest(token);

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      tokenStore.set(newToken);
      res = await makeRequest(newToken);
    } else {
      tokenStore.set(null);
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
      throw new Error("인증이 만료되었습니다.");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API 오류");
  }

  if (res.status === 204) return undefined as T;

  return res.json();
}

export const authApi = {
  login: (username: string, password: string) =>
    apiFetch<{ access_token: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    apiFetch<void>("/auth/logout", { method: "POST" }),
};

export interface User {
  id: number;
  username: string;
  role: "admin" | "driver";
  is_active: boolean;
  created_at: string;
}

export const usersApi = {
  list: () => apiFetch<User[]>("/users"),
  create: (payload: { username: string; password: string; role: "admin" | "driver" }) =>
    apiFetch<User>("/users", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: number, payload: { password?: string; role?: "admin" | "driver"; is_active?: boolean }) =>
    apiFetch<User>(`/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  delete: (id: number) =>
    apiFetch<void>(`/users/${id}`, { method: "DELETE" }),
};

export const logsApi = {
  list: (params: {
    page?: number;
    per_page?: number;
    vehicle_id?: string;
    date_from?: string;
    date_to?: string;
  }) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return apiFetch<import("@/types/log").LogsPage>(`/logs${qs ? `?${qs}` : ""}`);
  },
  create: (payload: import("@/types/log").LogCreatePayload) =>
    apiFetch<import("@/types/log").DrivingLog>("/logs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (id: number, payload: import("@/types/log").LogUpdatePayload) =>
    apiFetch<import("@/types/log").DrivingLog>(`/logs/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  delete: (id: number) =>
    apiFetch<void>(`/logs/${id}`, { method: "DELETE" }),
};

export const statsApi = {
  get: (params?: { vehicle_id?: string; year?: number }) => {
    const qs = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : "";
    return apiFetch<import("@/types/stats").StatsResponse>(`/stats${qs ? `?${qs}` : ""}`);
  },
};

export const pipelineApi = {
  latest: () => apiFetch<import("@/types/pipeline_run").PipelineRun>("/pipeline-runs/latest"),
  list: (limit = 20) => apiFetch<import("@/types/pipeline_run").PipelineRun[]>(`/pipeline-runs?limit=${limit}`),
};

