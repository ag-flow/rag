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

export function isErrorBodyWithDetail(body: unknown, expected: string): boolean {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return false;
  }
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === "string" && detail === expected;
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

  put: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  /**
   * PUT bas-niveau retournant la `Response` brute pour permettre la lecture
   * du status code (200/202/204). Les codes 4xx/5xx remontent comme `ApiError`.
   */
  putRaw: async (url: string, body: unknown): Promise<Response> => {
    const resp = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    if (!resp.ok) {
      let parsed: unknown = null;
      try {
        parsed = await resp.json();
      } catch {
        // pas de body JSON
      }
      throw new ApiError(resp.status, parsed);
    }
    return resp;
  },

  patch: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: <T>(url: string): Promise<T> =>
    request<T>(url, { method: "DELETE" }),
};
