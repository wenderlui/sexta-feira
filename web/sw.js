// Service worker: guarda a "casca" do app para abrir rápido; dados da API sempre da rede.
const CACHE = "sexta-v6";
const SHELL = ["/", "/index.html", "/styles.css", "/app.js", "/format.js", "/voice.js", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL.map((u) => new Request(u, { cache: "reload" })))));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/") || event.request.method !== "GET") return;
  // Rede primeiro, cache como reserva (para não ficar preso numa versão antiga).
  event.respondWith(
    // "no-cache": sempre confere com o PC, para o iPad não ficar com um app.js velho.
    fetch(event.request.mode === "navigate" ? event.request.url : event.request, { cache: "no-cache" })
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});
