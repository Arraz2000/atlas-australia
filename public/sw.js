// Service Worker: intercepts ESRI World_Hillshade tile requests and applies
// pixel inversion + gamma correction (gamma 2.5) to produce jet-black flat land
// with bright mountain ridges.

const ESRI_HILLSHADE = 'World_Hillshade/MapServer/tile/';

// Activate immediately — don't wait for old SW to vacate
self.addEventListener('install', e => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', event => {
  if (!event.request.url.includes(ESRI_HILLSHADE)) return;

  event.respondWith((async () => {
    const resp = await fetch(event.request);
    const blob = await resp.blob();
    const bitmap = await createImageBitmap(blob);

    const oc = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = oc.getContext('2d');
    ctx.drawImage(bitmap, 0, 0);

    const d = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
    for (let i = 0; i < d.data.length; i += 4) {
      d.data[i]   = Math.pow((255 - d.data[i])   / 255, 2.5) * 255;
      d.data[i+1] = Math.pow((255 - d.data[i+1]) / 255, 2.5) * 255;
      d.data[i+2] = Math.pow((255 - d.data[i+2]) / 255, 2.5) * 255;
    }
    ctx.putImageData(d, 0, 0);

    const out = await oc.convertToBlob({ type: 'image/jpeg', quality: 0.9 });
    return new Response(out, { headers: { 'Content-Type': 'image/jpeg' } });
  })());
});
