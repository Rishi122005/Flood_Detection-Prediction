(() => {
  const base = String(window.FLOOD_API_BASE_URL || "").replace(/\/+$/, "");
  if (!base) return;
  const nativeFetch = window.fetch.bind(window);
  const apiPrefix = /^\/(?:api\/|artifacts\/|before-after-artifacts\/|upload-artifacts\/)/;
  const absolutizeArtifacts = (value) => {
    if (Array.isArray(value)) return value.map(absolutizeArtifacts);
    if (value && typeof value === "object") {
      for (const key of Object.keys(value)) value[key] = absolutizeArtifacts(value[key]);
      return value;
    }
    if (typeof value === "string" && apiPrefix.test(value)) return base + value;
    return value;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll('a[href^="/api/"]').forEach((link) => {
      link.href = base + link.getAttribute("href");
    });
  });

  window.fetch = async (input, init) => {
    const originalUrl = input instanceof Request ? input.url : String(input);
    const parsed = new URL(originalUrl, window.location.href);
    const sameOriginApi = parsed.origin === window.location.origin && apiPrefix.test(parsed.pathname);
    const request = sameOriginApi ? base + parsed.pathname + parsed.search + parsed.hash : input;
    const response = await nativeFetch(request, init);
    if (sameOriginApi && response.headers.get("content-type")?.includes("application/json")) {
      const json = response.json.bind(response);
      Object.defineProperty(response, "json", {
        configurable: true,
        value: async () => absolutizeArtifacts(await json()),
      });
    }
    return response;
  };
})();
