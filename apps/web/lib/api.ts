/**
 * API client：透传 NextAuth session 的 access_token 到 FastAPI 后端。
 *
 * - Server Components 用 serverApi(session)
 * - Client Components 用 clientApi(token)
 */

// 服务端（Server Components / NextAuth authorize）优先用 docker 内部 URL；
// 客户端走 NEXT_PUBLIC_*（浏览器从宿主可达）。
const API_BASE =
  process.env.INTERNAL_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8001";

export type ApiOptions = RequestInit & { token?: string };

export async function apiFetch<T = unknown>(
  path: string,
  opts: ApiOptions = {},
): Promise<T> {
  const { token, headers, ...rest } = opts;
  const res = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export async function loginForm(
  username: string,
  password: string,
): Promise<{ access_token: string; expires_in_minutes: number }> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`login failed: ${res.status}`);
  return res.json();
}
