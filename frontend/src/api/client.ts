/** Fetch wrapper for the Django API: session cookie + CSRF header, one error shape. */

export class ApiError extends Error {
  status: number
  errors: Record<string, string[]>

  constructor(status: number, detail: string, errors: Record<string, string[]> = {}) {
    super(detail)
    this.status = status
    this.errors = errors
  }
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

let csrfReady: Promise<unknown> | null = null

/** Django sets the csrftoken cookie from this call; every write needs it. */
function ensureCsrf(): Promise<unknown> {
  if (csrfToken()) return Promise.resolve()
  csrfReady ??= fetch('/api/auth/csrf', { credentials: 'same-origin' })
  return csrfReady
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (method !== 'GET') {
    await ensureCsrf()
    headers['X-CSRFToken'] = csrfToken()
  }
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(path, { method, headers, body, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, "We couldn't reach the server. Check your connection and try again.")
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(response.status, data.detail ?? 'Something went wrong. Try again.', data.errors ?? {})
  }
  return data as T
}

/** The first message for a field, for showing under that input. */
export function fieldError(error: unknown, field: string): string | undefined {
  return error instanceof ApiError ? error.errors[field]?.[0] : undefined
}
