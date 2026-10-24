window.VoxTraceAPI = {
  async request(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {...(options.headers || {})};
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
      if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
    }
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
    }
    const response = await fetch(url, {
      ...options,
      method,
      headers,
      credentials: "same-origin"
    });
    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (![204, 205].includes(response.status) && contentType.includes("application/json")) {
      payload = await response.json();
    }
    if (response.status === 401 && window.location.pathname !== "/login") {
      window.location.assign("/login");
      throw new Error("La sesión ha expirado.");
    }
    if (!response.ok) {
      const error = new Error(payload?.detail || "No fue posible completar la operación.");
      error.status = response.status;
      throw error;
    }
    return payload;
  }
};
