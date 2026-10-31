/**
 * Robust shared API fetch helper for KYC Verification Platform.
 * Features:
 * - Content-Type and res.ok verification before parsing JSON
 * - Friendly human-readable messages on non-JSON responses (502, 500, HTML)
 * - Automatic redirect to /login?next=... on 401 Unauthorized
 * - Configurable timeout (default 20s) + 1 retry for container cold starts
 */

async function apiFetch(url, options = {}, retries = 1, timeoutMs = 20000) {
  const currentPath = window.location.pathname + window.location.search;

  // Add CSRF header if available
  const csrfToken = getCsrfToken();
  if (csrfToken && options.method && !['GET', 'HEAD', 'OPTIONS'].includes(options.method.toUpperCase())) {
    options.headers = options.headers || {};
    if (options.headers instanceof Headers) {
      options.headers.set('X-CSRF-Token', csrfToken);
    } else {
      options.headers['X-CSRF-Token'] = csrfToken;
    }
  }

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      clearTimeout(timer);

      // Handle 401: redirect to login
      if (response.status === 401) {
        if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/register')) {
          window.location.href = `/login?next=${encodeURIComponent(currentPath)}`;
        }
        const err = new Error('Session expired or unauthorized. Please log in.');
        err.status = 401;
        throw err;
      }

      const contentType = response.headers.get('content-type') || '';
      let data = null;

      if (contentType.includes('application/json')) {
        try {
          data = await response.json();
        } catch (jsonErr) {
          throw new Error('Malformed JSON received from server.');
        }
      } else {
        // Response is HTML or plain text (e.g. 502 Bad Gateway from reverse proxy)
        const text = await response.text();
        if (!response.ok) {
          if (response.status === 502 || response.status === 504) {
            throw new Error(`Server temporarily unavailable (HTTP ${response.status}). Please retry in a minute.`);
          }
          if (response.status === 413) {
            throw new Error('Uploaded document exceeds maximum allowed size.');
          }
          throw new Error(`Server error (HTTP ${response.status}). Please try again later.`);
        }
        // OK non-JSON
        return text;
      }

      if (!response.ok) {
        const errorMsg = (data && (data.message || data.detail || data.error)) || `Request failed with HTTP ${response.status}`;
        const err = new Error(typeof errorMsg === 'object' ? JSON.stringify(errorMsg) : errorMsg);
        err.status = response.status;
        err.data = data;
        throw err;
      }

      return data;
    } catch (err) {
      clearTimeout(timer);

      const isTimeout = err.name === 'AbortError';
      const isNetworkErr = isTimeout || err instanceof TypeError;

      // Retry once on network timeout/cold start error
      if (attempt < retries && isNetworkErr) {
        console.warn(`[apiFetch] Request to ${url} failed (attempt ${attempt + 1}), retrying in 1.5s...`);
        await new Promise(r => setTimeout(r, 1500));
        continue;
      }

      if (isTimeout) {
        throw new Error('Request timed out. The server may be warming up—please retry.');
      }
      throw err;
    }
  }
}

function getCsrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : (window.CSRF_TOKEN || '');
}

window.apiFetch = apiFetch;
window.getCsrfToken = getCsrfToken;
