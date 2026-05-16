export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

async function request<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    credentials: "include",
  });

  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    // 204 No Content ou réponse non-JSON
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, body);
  }

  return body as T;
}

export const api = {
  get: <T>(url: string): Promise<T> =>
    request<T>(url, { method: "GET" }),

  post: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  patch: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: <T>(url: string): Promise<T> =>
    request<T>(url, { method: "DELETE" }),
};
