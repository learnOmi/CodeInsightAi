const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

/** 统一 API 请求函数 */
export async function apiFetch<T>(
  path: string,
  options: globalThis.RequestInit = {}
): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(API_KEY && { "X-API-Key": API_KEY }),
    ...options.headers,
  };

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new APIError(response.status, errorBody.detail || errorBody.message || "API request failed");
  }

  return response.json();
}

/** API 错误类 */
export class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "APIError";
  }
}
