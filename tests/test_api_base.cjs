const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const apiBase = "https://flood-api.example.net";
const calls = [];
const handlers = {};
const links = [
  { href: "/api/availability", getAttribute: () => "/api/availability" },
  { href: "/api/detections", getAttribute: () => "/api/detections" },
];
const response = {
  headers: { get: () => "application/json; charset=utf-8" },
  json: async () => ({
    overlay_url: "/upload-artifacts/run/output.png",
    figure_url: "/artifacts/scene.webp",
    value: 3,
  }),
};
const window = {
  FLOOD_API_BASE_URL: apiBase,
  location: { origin: "https://flood-dashboard.vercel.app", href: "https://flood-dashboard.vercel.app/" },
  fetch: async (url) => {
    calls.push(url);
    return response;
  },
};
const document = {
  addEventListener: (name, callback) => { handlers[name] = callback; },
  querySelectorAll: () => links,
};
const context = { window, document, URL, Request: class Request {}, Object, Array, String };
vm.runInNewContext(fs.readFileSync("frontend/assets/api-base.js", "utf8"), context);

(async () => {
  const apiResponse = await window.fetch("/api/satellite/process?scene=1", { method: "POST" });
  const body = await apiResponse.json();
  assert.equal(calls[0], `${apiBase}/api/satellite/process?scene=1`);
  assert.equal(body.overlay_url, `${apiBase}/upload-artifacts/run/output.png`);
  assert.equal(body.figure_url, `${apiBase}/artifacts/scene.webp`);

  await window.fetch("/assets/earth_texture.png");
  assert.equal(calls[1], "/assets/earth_texture.png");

  handlers.DOMContentLoaded();
  assert.equal(links[0].href, `${apiBase}/api/availability`);
  assert.equal(links[1].href, `${apiBase}/api/detections`);
  console.log("API base URL and artifact rewriting checks passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
