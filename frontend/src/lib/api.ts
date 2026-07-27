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

/**
 * Redirige vers la page de login en préservant la route courante dans `next`.
 * No-op si l'on est déjà sur la page de login (évite les boucles de redirection).
 * Centralise la gestion « session expirée » utilisée par AuthGuard et par les
 * handlers globaux QueryCache/MutationCache (BUG-017).
 */
export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const { pathname, search } = window.location;
  if (pathname.startsWith("/ui/login")) return;
  let next = pathname + search;
  if (next.startsWith("/ui")) {
    next = next.slice(3) || "/";
  }
  window.location.href = `/ui/login?next=${encodeURIComponent(next)}`;
}

export function isErrorBodyWithDetail(body: unknown, expected: string): boolean {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return false;
  }
  const detail = (body as Record<string, unknown>).detail;
  return typeof detail === "string" && detail === expected;
}

/**
 * Rafraîchissement de session OIDC (single-flight) : plusieurs requêtes 401
 * simultanées ne déclenchent qu'un seul POST /auth/refresh. L'ID token
 * Keycloak expire vite (5 min par défaut) — sans ce refresh, la session
 * « tombait » à chaque expiration (bug 2026-07-27). Une session locale n'a
 * pas de refresh token : l'appel répond 401 et le 401 d'origine remonte.
 */
let refreshInFlight: Promise<boolean> | null = null;

function tryRefreshSession(): Promise<boolean> {
  refreshInFlight ??= fetch("/auth/refresh", { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

async function request<T>(url: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    credentials: "include",
  });

  if (resp.status === 401 && allowRefresh && (await tryRefreshSession())) {
    // Session rafraîchie : rejoue la requête UNE fois (body = string JSON,
    // réutilisable sans clonage).
    return request<T>(url, init, false);
  }

  // 204/205 : pas de body par contrat HTTP, ne pas tenter de parser.
  if (resp.status === 204 || resp.status === 205) {
    if (!resp.ok) {
      throw new ApiError(resp.status, null);
    }
    return undefined as T;
  }

  let body: unknown = null;
  let parseFailed = false;
  try {
    body = await resp.json();
  } catch {
    parseFailed = true;
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, body);
  }

  if (parseFailed) {
    // Réponse 2xx dont le body est absent/non-JSON (proxy mal configuré,
    // fallback statique, body tronqué) : ne pas faire passer `null` pour un
    // `T` non-nullable — le caster masquerait un TypeError en aval.
    throw new ApiError(resp.status, null);
  }

  return body as T;
}

export const api = {
  get: <T>(url: string): Promise<T> => request<T>(url, { method: "GET" }),

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
    const doFetch = () =>
      fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });
    let resp = await doFetch();
    if (resp.status === 401 && (await tryRefreshSession())) {
      resp = await doFetch();
    }
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

  delete: <T>(url: string): Promise<T> => request<T>(url, { method: "DELETE" }),
};
