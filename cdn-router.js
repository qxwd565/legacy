// URL aliases for HSdeck API and artwork. Original static paths remain available.
const API_ROOT_FILES = new Set([
  'cards.json', 'cards-date.json', 'render.json', 'render-date.json',
  'history.json', 'history-date.json', 'release-policy.json',
  'beta-patch-dates.json', 'taxonomy-history.json',
]);
const API_DIRECTORIES = new Set(['data', 'metadata']);
const ART_DIRECTORIES = new Set(['art', 'golden']);
const IMAGE_FILE = /^[A-Za-z0-9_.-]+\.(?:png|jpe?g|webp)$/i;

function targetAssetPath(pathname, hostname) {
  if (!pathname.startsWith('/legacy/')) return null;
  const relative = pathname.slice('/legacy/'.length);
  if (!relative || relative.includes('\\') || relative.split('/').some(segment => !segment || segment === '.' || segment === '..' || segment.startsWith('.'))) return null;

  const directory = relative.split('/', 1)[0];
  const api = API_ROOT_FILES.has(relative) || API_DIRECTORIES.has(directory);
  const art = ART_DIRECTORIES.has(directory) || IMAGE_FILE.test(relative);

  if (hostname === 'api.hsdeck.com' && !api) return null;
  if (hostname === 'art.hsdeck.com' && !art) return null;
  if (!api && !art) return null;

  return IMAGE_FILE.test(relative) ? '/art/' + relative : '/' + relative;
}

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Range, If-None-Match',
    'Cross-Origin-Resource-Policy': 'cross-origin',
  };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const assetPath = targetAssetPath(url.pathname, url.hostname);
    if (!assetPath) return new Response('Not found', { status: 404 });
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders() });
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('Method not allowed', { status: 405 });

    url.pathname = assetPath;
    const assetResponse = await env.ASSETS.fetch(new Request(url, request));
    const headers = new Headers(assetResponse.headers);
    for (const [name, value] of Object.entries(corsHeaders())) headers.set(name, value);
    return new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers,
    });
  },
};
