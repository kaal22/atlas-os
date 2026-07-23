/**
 * Atlas Maps — MapLibre + PMTiles boot (standalone /maps/ and Command Centre).
 *
 * Paint-first strategy (never fail silently):
 * 1. Default style: solid sky background + GeoJSON bbox fill/outline (MapLibre-only)
 *    + one bright fill on the first archive vector_layer (usually earth) + remaining layers.
 * 2. Bright-red archive bbox outline always until vector tiles paint (or forever with ?debug=1).
 *    Red box ⇒ MapLibre works, PMTiles path broken. Nothing ⇒ container/WebGL broken.
 * 3. Optional ?pretty=1 uses @protomaps/basemaps layers when the archive looks like v4.
 * 4. After idle, if tile features empty → auto-switch to paint-first once + dump diagnostics.
 * 5. ?debug=1 always shows the diagnostics panel.
 *
 * Protomaps basemap v4 source-layers: earth, landcover, landuse, water, roads,
 * buildings, boundaries, places, pois (+ transit reserved).
 * ~1180-byte PMTiles metadata typically holds vector_layers[] for those ids (+ light tilestats).
 */
(function (global) {
  "use strict";

  var PROTOMAPS_V4 = [
    "earth",
    "water",
    "landcover",
    "landuse",
    "roads",
    "buildings",
    "boundaries",
    "places",
    "pois",
  ];

  /** Matches Protomaps UK extract header when registry/header missing. */
  var UK_DEFAULT_BBOX = [-8.2, 49.8, 1.8, 60.9];

  var DIAG_SOURCE = "atlas-diag-bbox";
  var DIAG_FILL = "atlas-diag-bbox-fill";
  var DIAG_LINE = "atlas-diag-bbox-line";

  var PAINT_FILLS = [
    "#f4e04d",
    "#7cfc00",
    "#ff7f50",
    "#da70d6",
    "#00fa9a",
    "#ffd700",
    "#ff69b4",
    "#adff2f",
  ];
  var PAINT_LINES = ["#ff1493", "#1e90ff", "#ff4500", "#8a2be2", "#00ced1"];

  var state = {
    map: null,
    protocol: null,
    protocolAdded: false,
    countries: [],
    resizeObserver: null,
    resizeTimer: null,
    host: null,
    ui: null,
    opts: null,
    libsReady: false,
    mountGen: 0,
    tileErrors: [],
    dataEvents: [],
    lastStyleMode: "",
    lastArchiveLayers: [],
    lastHeader: null,
    lastBounds: null,
    paintFallbackTried: false,
    tilesPainted: false,
    debug: false,
  };

  function mapsRoot() {
    return global.location.origin + "/maps";
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[<>&]/g, function (c) {
      return { "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c];
    });
  }

  function wantDebug() {
    if (state.debug) return true;
    try {
      return new URLSearchParams(global.location.search).get("debug") === "1";
    } catch (_) {
      return false;
    }
  }

  function wantPretty() {
    try {
      var q = new URLSearchParams(global.location.search);
      if (q.get("paint") === "1") return false;
      if (q.get("pretty") === "0") return false;
      if (q.get("pretty") === "1") return true;
    } catch (_) {}
    // Default: pretty Protomaps when archive is v4; paint-first is fallback / ?paint=1.
    return true;
  }

  /** Stable vector source id — never use country code (collides with lang "uk" = Ukrainian). */
  var TILE_SOURCE = "protomaps";

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-atlas-maps-src="' + src + '"]');
      if (existing) {
        if (existing.dataset.loaded === "1") return resolve();
        existing.addEventListener("load", function () {
          resolve();
        });
        existing.addEventListener("error", function () {
          reject(new Error("Failed to load " + src));
        });
        return;
      }
      var s = document.createElement("script");
      s.src = src;
      s.async = false;
      s.dataset.atlasMapsSrc = src;
      s.onload = function () {
        s.dataset.loaded = "1";
        resolve();
      };
      s.onerror = function () {
        reject(new Error("Failed to load " + src));
      };
      document.head.appendChild(s);
    });
  }

  function loadCss(href) {
    if (document.querySelector('link[data-atlas-maps-href="' + href + '"]')) return;
    var l = document.createElement("link");
    l.rel = "stylesheet";
    l.href = href;
    l.dataset.atlasMapsHref = href;
    document.head.appendChild(l);
  }

  function ensureLibs() {
    if (global.maplibregl && global.pmtiles && global.basemaps) {
      state.libsReady = true;
      return Promise.resolve();
    }
    if (state.libsReady && global.maplibregl && global.pmtiles && global.basemaps) {
      return Promise.resolve();
    }
    var root = mapsRoot();
    loadCss(root + "/lib/maplibre-gl.css");
    return loadScript(root + "/lib/maplibre-gl.js")
      .then(function () {
        return loadScript(root + "/lib/pmtiles.js");
      })
      .then(function () {
        return loadScript(root + "/lib/basemaps.js");
      })
      .then(function () {
        if (!global.maplibregl) throw new Error("maplibre-gl.js did not define maplibregl");
        if (!global.pmtiles) throw new Error("pmtiles.js did not define pmtiles");
        if (!global.basemaps) throw new Error("basemaps.js did not define basemaps");
        state.libsReady = true;
      });
  }

  function ensureProtocol() {
    if (!state.protocol) {
      state.protocol = new global.pmtiles.Protocol({ metadata: true });
    }
    if (!state.protocolAdded) {
      global.maplibregl.addProtocol("pmtiles", function (req, abort) {
        return state.protocol.tile(req, abort);
      });
      state.protocolAdded = true;
    }
  }

  /** Explicit px box before MapLibre — flex % hosts often yield a 0×0 WebGL canvas. */
  function forceContainerSize(el, fallbackH) {
    if (!el) return { width: 960, height: 560 };
    var parent = el.parentElement;
    var rect = el.getBoundingClientRect();
    var vw = global.innerWidth || 1200;
    var vh = global.innerHeight || 800;
    var w = Math.max(
      rect.width || 0,
      el.clientWidth || 0,
      parent ? parent.clientWidth || 0 : 0,
      Math.floor(vw * 0.9),
      320
    );
    var h = Math.max(
      rect.height || 0,
      el.clientHeight || 0,
      parent ? parent.clientHeight || 0 : 0,
      fallbackH || 480,
      Math.floor(vh * 0.85)
    );
    if (h < 120) h = Math.max(fallbackH || 560, Math.floor(vh * 0.85));
    if (w < 120) w = Math.max(640, Math.floor(vw * 0.9));
    w = Math.round(w);
    h = Math.round(h);
    el.style.boxSizing = "border-box";
    el.style.width = w + "px";
    el.style.height = h + "px";
    el.style.minWidth = "320px";
    el.style.minHeight = Math.max(480, fallbackH || 480) + "px";
    return { width: w, height: h };
  }

  /**
   * Toggle panels without relying on [hidden] alone.
   * Inline display:grid/flex overrides UA [hidden]{display:none} on some engines,
   * which left the empty-state CTA covering a successfully painted MapLibre canvas.
   */
  function setPanelVisible(el, visible, shownDisplay) {
    if (!el) return;
    el.hidden = !visible;
    el.style.setProperty("display", visible ? shownDisplay || "block" : "none", "important");
    el.style.visibility = visible ? "visible" : "hidden";
    el.style.pointerEvents = visible ? "auto" : "none";
    if (!visible) el.setAttribute("aria-hidden", "true");
    else el.removeAttribute("aria-hidden");
  }

  function hideEmptyOverlay() {
    if (!state.ui || !state.ui.empty) return;
    setPanelVisible(state.ui.empty, false);
  }

  function showEmptyOverlay(htmlMsg) {
    if (!state.ui || !state.ui.empty) return;
    if (state.ui.emptyMsg && htmlMsg != null) state.ui.emptyMsg.innerHTML = htmlMsg;
    setPanelVisible(state.ui.empty, true, "grid");
  }

  /** One-release unmistakable confirmation that tiles painted under the chrome. */
  function showMapOkBanner(tileFeats) {
    if (!state.host) return;
    var prev = state.host.querySelector(".atlas-maps-ok");
    if (prev) {
      try {
        prev.remove();
      } catch (_) {}
    }
    var el = document.createElement("div");
    el.className = "atlas-maps-ok";
    el.setAttribute("role", "status");
    el.textContent =
      "MAP OK — " +
      (tileFeats || 0) +
      " features painted (empty CTA hidden)";
    el.style.cssText =
      "position:absolute;z-index:20;top:72px;left:50%;transform:translateX(-50%);" +
      "max-width:min(36rem,92vw);padding:12px 18px;border-radius:10px;text-align:center;" +
      "background:#16a34a;color:#fff;font:700 1rem/1.3 system-ui,sans-serif;" +
      "box-shadow:0 8px 28px rgba(0,0,0,.45);pointer-events:none;";
    state.host.appendChild(el);
    setTimeout(function () {
      try {
        el.remove();
      } catch (_) {}
    }, 10000);
  }

  function buildHostChrome(host, opts) {
    host.innerHTML = "";
    host.classList.add("atlas-maps-host");
    var hostH = Math.max(560, Math.floor((global.innerHeight || 800) * 0.92));
    host.style.cssText =
      "position:relative;display:block;width:100%;height:" +
      hostH +
      "px;min-height:100%;background:#0b6e99;color:#e8eef4;" +
      'font-family:"Segoe UI","IBM Plex Sans",system-ui,sans-serif;overflow:hidden;';

    // Map first in paint order / z-index so it is never under a sticky empty CTA.
    var mapEl = document.createElement("div");
    mapEl.id = "map";
    mapEl.style.cssText =
      "position:absolute;z-index:1;inset:0;width:100%;height:100%;min-height:560px;" +
      "background:#0b6e99;";

    var empty = document.createElement("div");
    empty.className = "atlas-maps-empty";
    empty.innerHTML =
      "<div><h1 style=\"margin:0 0 .5rem;font-weight:600\">Atlas Maps</h1>" +
      '<p class="atlas-maps-empty-msg" style="color:#9aa8b5;max-width:28rem;line-height:1.45"></p>' +
      '<p><a class="atlas-maps-cc" href="/#/content" style="color:#3d8bfd">Open Content</a></p></div>';
    // No inline display:grid here — that previously defeated [hidden] and covered #map forever.
    empty.style.cssText =
      "position:absolute;z-index:3;inset:0;place-items:center;text-align:center;padding:2rem;" +
      "background:#0f1419;";
    setPanelVisible(empty, false);

    var bar = document.createElement("div");
    bar.className = "atlas-maps-bar";
    bar.style.cssText =
      "position:absolute;z-index:4;top:12px;left:12px;right:12px;flex-wrap:wrap;gap:10px;" +
      "align-items:center;padding:10px 12px;border-radius:10px;background:rgba(18,24,32,.92);" +
      "border:1px solid rgba(255,255,255,.12);backdrop-filter:blur(8px);";
    bar.innerHTML =
      '<label for="atlasMapsCountry" style="font-size:.85rem;color:#9aa8b5">Country</label>' +
      '<select id="atlasMapsCountry" style="background:#1b2430;color:#e8eef4;border:1px solid rgba(255,255,255,.12);' +
      'border-radius:8px;padding:8px 12px;font-size:.95rem"></select>' +
      '<button type="button" id="atlasMapsFit" style="cursor:pointer;background:#1b2430;color:#e8eef4;' +
      "border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:8px 12px\">Fit</button>" +
      '<span id="atlasMapsStatus" style="font-size:.8rem;color:#9aa8b5;margin-left:auto"></span>';
    setPanelVisible(bar, false);

    var banner = document.createElement("div");
    banner.id = "atlasMapsBanner";
    banner.style.cssText =
      "position:absolute;z-index:5;left:12px;right:12px;bottom:12px;pointer-events:none;" +
      "padding:8px 12px;border-radius:8px;background:rgba(15,20,25,.82);color:#c5d0da;" +
      "font-size:.8rem;line-height:1.35;display:none;";

    var err = document.createElement("div");
    err.className = "atlas-maps-error";
    err.setAttribute("role", "alert");
    err.style.cssText =
      "position:absolute;z-index:6;left:12px;right:12px;bottom:12px;max-width:48rem;margin:0 auto;" +
      "padding:14px 16px;border-radius:10px;background:rgba(248,113,113,.12);" +
      "border:1px solid rgba(248,113,113,.45);color:#e8eef4;box-shadow:0 8px 24px rgba(0,0,0,.35);" +
      "max-height:45vh;overflow:auto;";
    err.innerHTML =
      '<strong style="color:#f87171;display:block;margin-bottom:.35rem">Map failed to render</strong>' +
      '<p class="atlas-maps-error-msg" style="margin:0;color:#9aa8b5;font-size:.9rem;line-height:1.45"></p>';
    setPanelVisible(err, false);

    var diag = document.createElement("pre");
    diag.id = "atlasMapsDiag";
    diag.style.cssText =
      "position:absolute;z-index:7;top:64px;right:12px;left:auto;width:min(28rem,92vw);" +
      "max-height:55vh;overflow:auto;margin:0;padding:10px 12px;border-radius:8px;" +
      "background:rgba(8,12,18,.92);color:#b8f5c5;font:11px/1.35 ui-monospace,Menlo,monospace;" +
      "border:1px solid rgba(184,245,197,.25);white-space:pre-wrap;word-break:break-word;";
    setPanelVisible(diag, false);

    host.appendChild(mapEl);
    host.appendChild(empty);
    host.appendChild(bar);
    host.appendChild(banner);
    host.appendChild(err);
    host.appendChild(diag);

    var contentUrl = (opts && opts.contentUrl) || global.location.origin + "/#/content";
    var cc = empty.querySelector(".atlas-maps-cc");
    if (cc) cc.href = contentUrl;

    forceContainerSize(host, hostH);
    forceContainerSize(mapEl, hostH);

    return {
      empty: empty,
      emptyMsg: empty.querySelector(".atlas-maps-empty-msg"),
      bar: bar,
      select: bar.querySelector("#atlasMapsCountry"),
      fitBtn: bar.querySelector("#atlasMapsFit"),
      statusEl: bar.querySelector("#atlasMapsStatus"),
      banner: banner,
      mapEl: mapEl,
      error: err,
      errorMsg: err.querySelector(".atlas-maps-error-msg"),
      diag: diag,
      contentUrl: contentUrl,
    };
  }

  function setStatus(msg, isErr) {
    if (!state.ui) return;
    state.ui.statusEl.textContent = msg || "";
    state.ui.statusEl.style.color = isErr ? "#f87171" : "#9aa8b5";
    if (state.ui.banner) {
      if (state.ui.error && !state.ui.error.hidden && isErr) {
        state.ui.banner.style.display = "none";
        return;
      }
      state.ui.banner.style.display = msg ? "block" : "none";
      state.ui.banner.textContent = msg || "";
      state.ui.banner.style.color = isErr ? "#fecaca" : "#c5d0da";
      state.ui.banner.style.border = isErr
        ? "1px solid rgba(248,113,113,.45)"
        : "1px solid transparent";
    }
  }

  function showError(msg, detail) {
    if (!state.ui) return;
    // Never resurrect the empty CTA over a live painted map.
    if (state.tilesPainted) hideEmptyOverlay();
    var text = String(msg || "Unknown map error");
    state.ui.errorMsg.innerHTML =
      escapeHtml(text) +
      (detail
        ? "<br><code style=\"font-size:.8rem;color:#fecaca;word-break:break-all\">" +
          escapeHtml(detail) +
          "</code>"
        : "");
    setPanelVisible(state.ui.error, true, "block");
    if (state.ui.banner) state.ui.banner.style.display = "none";
    setStatus(text, true);
  }

  function clearError() {
    if (!state.ui) return;
    setPanelVisible(state.ui.error, false);
    state.ui.errorMsg.textContent = "";
  }

  function showDiag(obj) {
    if (!state.ui || !state.ui.diag) return;
    setPanelVisible(state.ui.diag, true, "block");
    try {
      state.ui.diag.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
    } catch (_) {
      state.ui.diag.textContent = String(obj);
    }
  }

  /**
   * Safe isSourceLoaded — MapLibre fires "There is no source with ID '…'" on the map
   * error channel when the id is missing from sourceCaches (does not throw).
   * Never call map.isSourceLoaded until getSource confirms the source exists.
   */
  function safeSourceLoaded(map, sourceId) {
    if (!map || !sourceId) return null;
    try {
      if (!map.getSource || !map.getSource(sourceId)) return false;
      if (!map.isSourceLoaded) return null;
      return !!map.isSourceLoaded(sourceId);
    } catch (_) {
      return null;
    }
  }

  function styleHasSource(styleObj, sourceId) {
    return !!(styleObj && styleObj.sources && styleObj.sources[sourceId]);
  }

  /** Every layer.source must exist in style.sources — reject incomplete styles early. */
  function assertStyleSources(styleObj) {
    if (!styleObj || !styleObj.sources) {
      throw new Error("Style missing sources object");
    }
    var layers = styleObj.layers || [];
    var missing = [];
    for (var i = 0; i < layers.length; i++) {
      var lid = layers[i];
      if (!lid || !lid.source) continue;
      if (!styleObj.sources[lid.source]) {
        missing.push(lid.id + "→" + lid.source);
      }
    }
    if (missing.length) {
      throw new Error(
        "Layers reference missing sources: " + missing.slice(0, 8).join(", ")
      );
    }
    if (!styleObj.sources[TILE_SOURCE]) {
      throw new Error("Style missing vector source '" + TILE_SOURCE + "'");
    }
    return styleObj;
  }

  function collectDiagnostics(extra) {
    var map = state.map;
    var canvas = map && map.getCanvas && map.getCanvas();
    var style = null;
    var layerIds = [];
    var sourceIds = [];
    var sourceOk = null;
    var tilesLoaded = null;
    var center = null;
    var zoom = null;
    var bearing = null;
    var pitch = null;
    var feats = null;
    var styleSourcesOk = null;
    try {
      if (map) {
        style = map.isStyleLoaded && map.isStyleLoaded();
        center = map.getCenter && map.getCenter();
        zoom = map.getZoom && map.getZoom();
        bearing = map.getBearing && map.getBearing();
        pitch = map.getPitch && map.getPitch();
        if (map.getStyle) {
          var st = map.getStyle();
          layerIds = ((st && st.layers) || []).map(function (l) {
            return l.id + ":" + (l["source-layer"] || l.type);
          });
          sourceIds = st && st.sources ? Object.keys(st.sources) : [];
          styleSourcesOk = styleHasSource(st, TILE_SOURCE);
        }
        // CRITICAL: do not call isSourceLoaded unless getSource exists —
        // MapLibre otherwise fires "There is no source with ID …" into tileErrors.
        sourceOk = safeSourceLoaded(map, TILE_SOURCE);
        if (map.areTilesLoaded) tilesLoaded = map.areTilesLoaded();
        feats = map.queryRenderedFeatures ? map.queryRenderedFeatures().length : null;
      }
    } catch (e) {
      extra = Object.assign({}, extra || {}, { diagError: String(e && e.message ? e.message : e) });
    }
    var hostRect =
      state.host && state.host.getBoundingClientRect
        ? state.host.getBoundingClientRect()
        : null;
    return Object.assign(
      {
        ok: feats > 0,
        paintedFeatures: feats,
        styleLoaded: style,
        sourceId: TILE_SOURCE,
        sourceInStyle: styleSourcesOk,
        sourceIds: sourceIds,
        sourceLoaded: sourceOk,
        tilesLoaded: tilesLoaded,
        tilesPainted: state.tilesPainted,
        canvas: canvas ? { width: canvas.width, height: canvas.height } : null,
        host: hostRect
          ? { width: Math.round(hostRect.width), height: Math.round(hostRect.height) }
          : null,
        camera: {
          center: center ? [center.lng, center.lat] : null,
          zoom: zoom,
          bearing: bearing,
          pitch: pitch,
        },
        styleMode: state.lastStyleMode,
        archiveLayers: state.lastArchiveLayers,
        expectedProtomapsV4: PROTOMAPS_V4,
        layerIds: layerIds.slice(0, 40),
        tileErrors: state.tileErrors.slice(-12),
        recentData: state.dataEvents.slice(-8),
        header: state.lastHeader,
        bounds: state.lastBounds,
        hint:
          "Red bbox outline = MapLibre OK. ?paint=1 = bright diagnostic. ?pretty=0 forces paint-first. /maps/diag for server.",
      },
      extra || {}
    );
  }

  function forceResizeLoop() {
    if (!state.map) return;
    var n = 0;
    function tick() {
      if (!state.map || n > 16) return;
      try {
        if (state.host) forceContainerSize(state.host, 560);
        if (state.ui && state.ui.mapEl) forceContainerSize(state.ui.mapEl, 560);
        state.map.resize();
      } catch (_) {}
      n += 1;
      var canvas = state.map.getCanvas && state.map.getCanvas();
      if (canvas && canvas.width >= 2 && canvas.height >= 2 && n > 2) return;
      state.resizeTimer = setTimeout(tick, 80 + n * 40);
    }
    tick();
  }

  function ensureMapSize() {
    if (!state.map) return;
    try {
      if (state.host) forceContainerSize(state.host, 560);
      if (state.ui && state.ui.mapEl) forceContainerSize(state.ui.mapEl, 560);
      state.map.resize();
    } catch (_) {}
    var canvas = state.map.getCanvas && state.map.getCanvas();
    var host = state.host;
    var rect = host && host.getBoundingClientRect ? host.getBoundingClientRect() : null;
    if (canvas && (canvas.width < 2 || canvas.height < 2)) {
      showError(
        "Map canvas has zero size — layout collapsed. Open /maps/?country=uk full page.",
        "canvas " +
          (canvas && canvas.width) +
          "×" +
          (canvas && canvas.height) +
          (rect ? " host " + Math.round(rect.width) + "×" + Math.round(rect.height) : "")
      );
    }
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store", credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(url + " → " + r.status);
      return r.json();
    });
  }

  function headOk(url) {
    return fetch(url, { method: "HEAD", cache: "no-store" })
      .then(function (r) {
        if (r.ok) return true;
        return fetch(url, {
          method: "GET",
          headers: { Range: "bytes=0-0" },
          cache: "no-store",
        }).then(function (r2) {
          return r2.ok || r2.status === 206;
        });
      })
      .catch(function () {
        return fetch(url, {
          method: "GET",
          headers: { Range: "bytes=0-0" },
          cache: "no-store",
        })
          .then(function (r2) {
            return r2.ok || r2.status === 206;
          })
          .catch(function () {
            return false;
          });
      });
  }

  function assertRangeSupport(url) {
    return fetch(url, {
      method: "GET",
      headers: { Range: "bytes=0-126" },
      cache: "no-store",
    }).then(function (r) {
      if (!(r.status === 206 || r.status === 200)) {
        throw new Error("PMTiles HTTP " + r.status + " (need 206 Range or 200)");
      }
      if (r.status === 200) {
        var cl = Number(r.headers.get("Content-Length") || 0);
        if (cl > 512) {
          try {
            if (r.body && typeof r.body.cancel === "function") r.body.cancel();
          } catch (_) {}
          throw new Error(
            "Server ignored HTTP Range (200 + Content-Length " +
              cl +
              "). PMTiles needs Accept-Ranges / 206."
          );
        }
      }
      if (r.status === 206) {
        var cr = r.headers.get("Content-Range") || "";
        if (!/bytes\s+\d+-\d+\/\d+/i.test(cr)) {
          throw new Error("Range response missing Content-Range header");
        }
      }
      return r.arrayBuffer().then(function (ab) {
        var buf = new Uint8Array(ab);
        var magic = String.fromCharCode.apply(null, Array.prototype.slice.call(buf, 0, 7));
        if (magic !== "PMTiles") {
          throw new Error("Not a PMTiles archive (magic=" + JSON.stringify(magic) + ")");
        }
        if (buf.length >= 8 && buf[7] !== 3) {
          throw new Error("Unsupported PMTiles version " + buf[7] + " (need v3)");
        }
        return buf;
      });
    });
  }

  function assertBasemapAssets(assetsBase) {
    var glyph = assetsBase + "fonts/Noto Sans Regular/0-255.pbf";
    var spriteV4 = assetsBase + "sprites/v4/light.json";
    var spriteV3 = assetsBase + "sprites/v3/light.json";
    return Promise.all([headOk(glyph), headOk(spriteV4), headOk(spriteV3)]).then(function (oks) {
      var gOk = oks[0];
      var s4 = oks[1];
      var s3 = oks[2];
      if (!gOk || (!s4 && !s3)) {
        throw new Error(
          "Basemap fonts/sprites missing (glyphs " +
            (gOk ? "ok" : "404") +
            ", sprites " +
            (s4 ? "v4" : s3 ? "v3" : "404") +
            "). Re-open Maps to extract assets."
        );
      }
      return s4 ? "v4" : "v3";
    });
  }

  function normalizeRegistry(doc) {
    var out = [];
    if (!doc || typeof doc !== "object") return out;
    var raw = doc.countries;
    if (Array.isArray(raw)) {
      for (var i = 0; i < raw.length; i++) {
        var row = raw[i];
        if (!row || !row.code) continue;
        out.push({
          code: String(row.code).toLowerCase(),
          name: row.name || String(row.code).toUpperCase(),
          center: row.center || null,
          bbox: row.bbox || null,
          status: row.status || "listed",
        });
      }
      return out;
    }
    if (raw && typeof raw === "object") {
      Object.keys(raw).forEach(function (code) {
        var row = raw[code];
        var cc = String(code).toLowerCase();
        out.push({
          code: cc,
          name: (row && row.name) || cc.toUpperCase(),
          center: (row && row.center) || null,
          bbox: (row && row.bbox) || null,
          status: (row && row.status) || "stub",
          tiles: (row && row.tiles) || [],
        });
      });
    }
    return out;
  }

  function layerNamesFromMeta(meta) {
    var names = [];
    if (!meta) return names;
    var vl = meta.vector_layers || (meta.tilestats && meta.tilestats.layers) || null;
    if (Array.isArray(vl)) {
      for (var i = 0; i < vl.length; i++) {
        var id = vl[i] && (vl[i].id || vl[i].layer || vl[i].name);
        if (id) names.push(String(id));
      }
    }
    return names;
  }

  function readArchiveInfo(tileUrl) {
    var p = new global.pmtiles.PMTiles(tileUrl);
    return Promise.all([
      p.getHeader().catch(function () {
        return null;
      }),
      p.getMetadata().catch(function () {
        return null;
      }),
    ]).then(function (pair) {
      var header = pair[0];
      var meta = pair[1];
      var layers = layerNamesFromMeta(meta);
      var hdr = null;
      if (header) {
        hdr = {
          minZoom: header.minZoom,
          maxZoom: header.maxZoom,
          minLon: header.minLon,
          minLat: header.minLat,
          maxLon: header.maxLon,
          maxLat: header.maxLat,
          centerLon: header.centerLon,
          centerLat: header.centerLat,
          centerZoom: header.centerZoom,
          tileType: header.tileType,
        };
      }
      return { meta: meta, layers: layers, header: hdr };
    });
  }

  function isProtomapsV4(layers) {
    var set = {};
    layers.forEach(function (n) {
      set[n] = true;
    });
    return !!(set.earth && set.water);
  }

  function boundsForCountry(header, country) {
    if (
      header &&
      typeof header.minLon === "number" &&
      typeof header.minLat === "number" &&
      typeof header.maxLon === "number" &&
      typeof header.maxLat === "number" &&
      header.minLon < header.maxLon &&
      header.minLat < header.maxLat
    ) {
      return [header.minLon, header.minLat, header.maxLon, header.maxLat];
    }
    if (country && Array.isArray(country.bbox) && country.bbox.length === 4) {
      return [
        Number(country.bbox[0]),
        Number(country.bbox[1]),
        Number(country.bbox[2]),
        Number(country.bbox[3]),
      ];
    }
    if (country && country.code === "uk") return UK_DEFAULT_BBOX.slice();
    return UK_DEFAULT_BBOX.slice();
  }

  function bboxFeatureCollection(bounds) {
    var w = bounds[0];
    var s = bounds[1];
    var e = bounds[2];
    var n = bounds[3];
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { atlas_diag: "bbox" },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [w, s],
                [e, s],
                [e, n],
                [w, n],
                [w, s],
              ],
            ],
          },
        },
      ],
    };
  }

  function diagSources(bounds) {
    var out = {};
    out[DIAG_SOURCE] = {
      type: "geojson",
      data: bboxFeatureCollection(bounds),
    };
    return out;
  }

  /** GeoJSON fill + bright red outline — paints without PMTiles. */
  function diagLayers() {
    return [
      {
        id: DIAG_FILL,
        type: "fill",
        source: DIAG_SOURCE,
        paint: {
          "fill-color": "#fbbf24",
          "fill-opacity": 0.12,
        },
      },
      {
        id: DIAG_LINE,
        type: "line",
        source: DIAG_SOURCE,
        paint: {
          "line-color": "#ff0000",
          "line-width": 3.5,
          "line-opacity": 1,
        },
      },
    ];
  }

  function pmtilesSource(tileHttpUrl, header) {
    var src = {
      type: "vector",
      // Explicit tile template under stable id TILE_SOURCE ("protomaps").
      // Do not use country code as source id ("uk" collides with basemaps lang).
      tiles: ["pmtiles://" + tileHttpUrl + "/{z}/{x}/{y}"],
      attribution:
        '© <a href="https://openstreetmap.org">OpenStreetMap</a> · <a href="https://protomaps.com">Protomaps</a>',
    };
    if (header) {
      if (typeof header.minZoom === "number") src.minzoom = header.minZoom;
      if (typeof header.maxZoom === "number") src.maxzoom = header.maxZoom;
      if (
        typeof header.minLon === "number" &&
        typeof header.minLat === "number" &&
        typeof header.maxLon === "number" &&
        typeof header.maxLat === "number" &&
        header.minLon < header.maxLon
      ) {
        src.bounds = [header.minLon, header.minLat, header.maxLon, header.maxLat];
      }
    } else {
      src.minzoom = 0;
      src.maxzoom = 14;
    }
    var out = {};
    out[TILE_SOURCE] = src;
    return out;
  }

  /**
   * Bright diagnostic / reliable paint style — no geometry filters, no labels.
   * Complete style JSON: sources[TILE_SOURCE] + layers in one object (never addLayer first).
   */
  function buildPaintFirstStyle(code, layerNames, tileHttpUrl, header, assetsBase, spriteVer, bounds) {
    var names = layerNames.length ? layerNames.slice() : PROTOMAPS_V4.slice();
    // Prefer earth first so land fills immediately.
    names.sort(function (a, b) {
      if (a === "earth") return -1;
      if (b === "earth") return 1;
      if (a === "water") return -1;
      if (b === "water") return 1;
      return a < b ? -1 : a > b ? 1 : 0;
    });
    var b = bounds || boundsForCountry(header, { code: code });
    var layers = [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#0b6e99" },
      },
    ];
    // Diag geojson first so something always paints even if vector tiles fail.
    layers = layers.concat(diagLayers().slice(0, 1)); // fill under tiles
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      layers.push({
        id: "atlas-fill-" + name,
        type: "fill",
        source: TILE_SOURCE,
        "source-layer": name,
        paint: {
          "fill-color": PAINT_FILLS[i % PAINT_FILLS.length],
          "fill-opacity": name === "earth" ? 0.95 : 0.85,
          "fill-outline-color": "#1a1a1a",
        },
      });
      layers.push({
        id: "atlas-line-" + name,
        type: "line",
        source: TILE_SOURCE,
        "source-layer": name,
        paint: {
          "line-color": PAINT_LINES[i % PAINT_LINES.length],
          "line-width": 1.4,
          "line-opacity": 0.95,
        },
      });
      layers.push({
        id: "atlas-circle-" + name,
        type: "circle",
        source: TILE_SOURCE,
        "source-layer": name,
        paint: {
          "circle-radius": 3,
          "circle-color": PAINT_FILLS[(i + 3) % PAINT_FILLS.length],
          "circle-stroke-width": 1,
          "circle-stroke-color": "#111",
        },
      });
    }
    // Red outline on top — diagnostic independent of PMTiles.
    layers.push(diagLayers()[1]);
    var styleObj = {
      version: 8,
      name: "atlas-paint-first-" + code,
      // No glyphs/sprite — paint-first has no symbol layers (avoids asset stalls).
      sources: Object.assign({}, pmtilesSource(tileHttpUrl, header), diagSources(b)),
      layers: layers,
    };
    return assertStyleSources(styleObj);
  }

  function buildProtomapsStyle(code, tileHttpUrl, header, assetsBase, spriteVer, bounds) {
    var flavor;
    var layers;
    try {
      if (!global.basemaps || typeof global.basemaps.namedFlavor !== "function") {
        throw new Error("basemaps.namedFlavor missing");
      }
      flavor = global.basemaps.namedFlavor("light");
      // Third arg is options {lang, labelsOnly} — null/undefined = no labels.
      // Never pass country code as lang ("uk" = Ukrainian).
      layers = global.basemaps.layers(TILE_SOURCE, flavor, null);
    } catch (e) {
      throw new Error(
        "basemaps.layers failed: " + (e && e.message ? e.message : e)
      );
    }
    if (!layers || !layers.length) {
      throw new Error("basemaps.layers returned empty");
    }
    for (var i = 0; i < layers.length; i++) {
      if (layers[i].source && layers[i].source !== TILE_SOURCE) {
        layers[i].source = TILE_SOURCE;
      }
      if (layers[i].id === "background") {
        layers[i].paint = layers[i].paint || {};
        layers[i].paint["background-color"] = "#8eb4d4";
      }
    }
    var b = bounds || boundsForCountry(header, { code: code });
    var withDiag = [layers[0]]
      .concat(diagLayers().slice(0, 1))
      .concat(layers.slice(1))
      .concat([diagLayers()[1]]);
    var styleObj = {
      version: 8,
      name: "atlas-protomaps-" + code,
      glyphs: assetsBase + "fonts/{fontstack}/{range}.pbf",
      sprite: assetsBase + "sprites/" + spriteVer + "/light",
      sources: Object.assign({}, pmtilesSource(tileHttpUrl, header), diagSources(b)),
      layers: withDiag,
    };
    return assertStyleSources(styleObj);
  }

  function buildStyle(code, archiveLayers, tileHttpUrl, header, assetsBase, spriteVer, forcePaint, bounds) {
    var b = bounds || boundsForCountry(header, { code: code });
    var paint = forcePaint || !wantPretty() || !isProtomapsV4(archiveLayers);
    if (!paint) {
      try {
        return {
          style: buildProtomapsStyle(code, tileHttpUrl, header, assetsBase, spriteVer, b),
          mode: "protomaps-v4",
          layers: archiveLayers,
        };
      } catch (e) {
        return {
          style: buildPaintFirstStyle(
            code,
            archiveLayers,
            tileHttpUrl,
            header,
            assetsBase,
            spriteVer,
            b
          ),
          mode: "paint-first-after-basemaps-error",
          layers: archiveLayers,
          basemapsError: e && e.message ? e.message : String(e),
        };
      }
    }
    return {
      style: buildPaintFirstStyle(
        code,
        archiveLayers,
        tileHttpUrl,
        header,
        assetsBase,
        spriteVer,
        b
      ),
      mode: archiveLayers.length ? "paint-first" : "paint-first-assumed-v4",
      layers: archiveLayers,
    };
  }

  function flyToCountry(c) {
    if (!state.map || !c) return;
    var hdr = state.lastHeader;
    if (hdr && hdr.minLon < hdr.maxLon && hdr.minLat < hdr.maxLat) {
      try {
        state.map.fitBounds(
          [
            [hdr.minLon, hdr.minLat],
            [hdr.maxLon, hdr.maxLat],
          ],
          { padding: 40, duration: 600, maxZoom: 8, bearing: 0, pitch: 0 }
        );
        return;
      } catch (_) {}
    }
    if (Array.isArray(c.bbox) && c.bbox.length === 4) {
      state.map.fitBounds(
        [
          [c.bbox[0], c.bbox[1]],
          [c.bbox[2], c.bbox[3]],
        ],
        { padding: 48, duration: 800, maxZoom: 8, bearing: 0, pitch: 0 }
      );
      return;
    }
    if (Array.isArray(c.center) && c.center.length >= 2) {
      state.map.flyTo({
        center: [c.center[0], c.center[1]],
        zoom: 5.5,
        bearing: 0,
        pitch: 0,
        duration: 800,
      });
      return;
    }
    if (c.code === "uk") {
      state.map.flyTo({
        center: [-2.5, 54.5],
        zoom: 5.5,
        bearing: 0,
        pitch: 0,
        duration: 800,
      });
    }
  }

  function applyStyle(built, c, gen) {
    state.lastStyleMode = built.mode;
    state.lastArchiveLayers = built.layers || [];
    state.tilesPainted = false;
    state.lastBounds = boundsForCountry(state.lastHeader, c);
    if (built.basemapsError) {
      setStatus("basemaps failed — using paint-first: " + built.basemapsError, true);
    }
    var styleObj = assertStyleSources(built.style);
    var size = forceContainerSize(state.ui.mapEl, 560);
    if (state.host) forceContainerSize(state.host, 560);
    setStatus("Creating map " + size.width + "×" + size.height + " (" + built.mode + ")…");

    if (!state.map) {
      state.map = new global.maplibregl.Map({
        container: state.ui.mapEl,
        style: styleObj,
        center:
          (c.center && [c.center[0], c.center[1]]) ||
          (state.lastHeader
            ? [state.lastHeader.centerLon, state.lastHeader.centerLat]
            : [-2.5, 54.5]),
        zoom:
          (state.lastHeader && state.lastHeader.centerZoom) ||
          5.2,
        bearing: 0,
        pitch: 0,
        attributionControl: true,
        failIfMajorPerformanceCaveat: false,
      });
      state.map.addControl(
        new global.maplibregl.NavigationControl({ visualizePitch: false }),
        "bottom-right"
      );
      state.map.addControl(new global.maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      wireMapEvents(c, built.mode, built.layers);
      if (typeof ResizeObserver !== "undefined") {
        state.resizeObserver = new ResizeObserver(function () {
          ensureMapSize();
        });
        state.resizeObserver.observe(state.ui.mapEl);
        if (state.host) state.resizeObserver.observe(state.host);
      }
      global.addEventListener("resize", ensureMapSize);
      global.addEventListener("message", function (ev) {
        if (ev && ev.data && ev.data.type === "atlas-maps-resize") ensureMapSize();
      });
      forceResizeLoop();
    } else {
      state.map.once("idle", function () {
        if (gen !== state.mountGen) return;
        setStatus(c.name || c.code);
        ensureMapSize();
        flyToCountry(c);
        verifyPaint(c, built.mode, built.layers);
      });
      // Full replace — style diff can briefly drop sources while layers still reference them.
      state.map.setStyle(styleObj, { diff: false });
    }
  }

  function switchToPaintFirst(c, gen) {
    if (state.paintFallbackTried || gen !== state.mountGen) return;
    state.paintFallbackTried = true;
    setStatus("Empty paint — switching to paint-first style…", true);
    var root = mapsRoot();
    var assetsBase = root + "/basemaps-assets/";
    var tileUrl = root + "/pmtiles/" + c.code + ".pmtiles";
    assertBasemapAssets(assetsBase)
      .then(function (spriteVer) {
        if (gen !== state.mountGen) return;
        var built = buildStyle(
          c.code,
          state.lastArchiveLayers,
          tileUrl,
          state.lastHeader,
          assetsBase,
          spriteVer,
          true
        );
        applyStyle(built, c, gen);
      })
      .catch(function (e) {
        showError("Paint-first fallback failed", e && e.message ? e.message : e);
        showDiag(collectDiagnostics({ fallbackError: String(e && e.message ? e.message : e) }));
      });
  }

  function countPainted(map) {
    var tileFeats = 0;
    var diagFeats = 0;
    try {
      var all = map.queryRenderedFeatures() || [];
      for (var i = 0; i < all.length; i++) {
        var f = all[i];
        var lid = f && f.layer && f.layer.id;
        if (lid === DIAG_FILL || lid === DIAG_LINE) diagFeats += 1;
        else tileFeats += 1;
      }
    } catch (_) {}
    return { tileFeats: tileFeats, diagFeats: diagFeats, total: tileFeats + diagFeats };
  }

  function maybeHideDiagOverlay() {
    if (!state.map || wantDebug() || !state.tilesPainted) return;
    try {
      if (state.map.getLayer(DIAG_LINE)) state.map.setLayoutProperty(DIAG_LINE, "visibility", "none");
      if (state.map.getLayer(DIAG_FILL)) state.map.setLayoutProperty(DIAG_FILL, "visibility", "none");
    } catch (_) {}
  }

  function verifyPaint(c, mode, layerNames) {
    if (!state.map) return;
    try {
      var canvas = state.map.getCanvas && state.map.getCanvas();
      if (canvas && (canvas.width < 2 || canvas.height < 2)) {
        ensureMapSize();
        canvas = state.map.getCanvas && state.map.getCanvas();
      }
      var counts = countPainted(state.map);
      if (counts.tileFeats > 0) {
        state.tilesPainted = true;
        hideEmptyOverlay();
        clearError();
        showMapOkBanner(counts.tileFeats);
        setStatus(
          (c.name || c.code) +
            " · " +
            mode +
            " · tiles " +
            counts.tileFeats +
            (counts.diagFeats ? " · diag " + counts.diagFeats : "") +
            (canvas ? " · canvas " + canvas.width + "×" + canvas.height : "")
        );
        maybeHideDiagOverlay();
        if (wantDebug()) showDiag(collectDiagnostics({ painted: true, tiles: counts.tileFeats }));
        return;
      }
      if (counts.diagFeats > 0) {
        setStatus(
          (c.name || c.code) +
            " · " +
            mode +
            " · MapLibre OK (red bbox) — waiting for vector tiles…",
          true
        );
        if (wantDebug()) {
          showDiag(
            collectDiagnostics({
              painted: false,
              maplibreOk: true,
              diagOnly: counts.diagFeats,
            })
          );
        }
      }
    } catch (_) {}

    try {
      flyToCountry(c);
    } catch (_) {}
    setTimeout(function () {
      if (!state.map) return;
      try {
        var counts2 = countPainted(state.map);
        if (counts2.tileFeats > 0) {
          state.tilesPainted = true;
          hideEmptyOverlay();
          clearError();
          showMapOkBanner(counts2.tileFeats);
          setStatus(
            (c.name || c.code) + " · " + mode + " · tiles " + counts2.tileFeats + " features"
          );
          maybeHideDiagOverlay();
          if (wantDebug()) showDiag(collectDiagnostics({ painted: true, afterFit: true }));
          return;
        }
        if (counts2.diagFeats > 0 && counts2.tileFeats === 0) {
          if (!state.paintFallbackTried && mode && mode.indexOf("paint-first") !== 0) {
            switchToPaintFirst(c, state.mountGen);
            return;
          }
          showError(
            "MapLibre paints (red bbox) but vector tiles did not. PMTiles/protocol path broken.",
            "mode=" + mode + " diag=" + counts2.diagFeats
          );
          showDiag(
            collectDiagnostics({
              blankTiles: true,
              maplibreOk: true,
              diagOnly: counts2.diagFeats,
            })
          );
          return;
        }
      } catch (_) {}

      if (!state.paintFallbackTried && mode && mode.indexOf("paint-first") !== 0) {
        switchToPaintFirst(c, state.mountGen);
        return;
      }

      var diag = collectDiagnostics({
        blank: true,
        mode: mode,
        archive_layers: layerNames || [],
      });
      showError(
        "Map loaded but nothing painted (no red bbox either — container/WebGL). Try /maps/?country=" +
          (c.code || "uk") +
          "&debug=1 or /maps/diag",
        "mode=" +
          mode +
          " layers=[" +
          (layerNames || []).join(",") +
          "] tileErrors=" +
          state.tileErrors.length
      );
      showDiag(diag);
    }, 1000);
  }

  function wireMapEvents(c, mode, layerNames) {
    state.map.on("load", function () {
      setStatus("Map loaded — fetching tiles for " + (c.name || c.code) + "…");
      ensureMapSize();
      forceResizeLoop();
      // Reset camera attitude — pitched/bearing maps can look "empty".
      try {
        state.map.setBearing(0);
        state.map.setPitch(0);
      } catch (_) {}
      flyToCountry(c);
    });
    state.map.on("idle", function onIdle() {
      state.map.off("idle", onIdle);
      ensureMapSize();
      setTimeout(function () {
        verifyPaint(c, mode, layerNames);
      }, 800);
    });
    state.map.on("error", function (e) {
      var msg = (e && e.error && e.error.message) || (e && e.message) || "Map error";
      if (/AbortError/i.test(msg)) return;
      if (/Alpha-premult|y-flip|texImage/i.test(msg)) return;
      // Spurious: MapLibre isSourceLoaded(id) fires this when sourceCaches lacks id.
      // Our diagnostics used to call that during style load → error spam loop.
      if (/There is no source with ID/i.test(msg)) return;
      state.tileErrors.push({
        t: Date.now(),
        message: msg,
        sourceId: e && e.sourceId,
        tile: e && e.tile ? { z: e.tile.tileID && e.tile.tileID.canonical && e.tile.tileID.canonical.z } : null,
      });
      if (state.tileErrors.length > 40) state.tileErrors.shift();
      showError(msg, e && e.sourceId ? "source=" + e.sourceId : "");
      // Do not call collectDiagnostics here — it can re-enter via isSourceLoaded errors.
      if (wantDebug() && state.map && state.map.isStyleLoaded && state.map.isStyleLoaded()) {
        showDiag(collectDiagnostics({ fromError: msg }));
      }
    });
    state.map.on("data", function (e) {
      if (!e) return;
      if (e.dataType === "source" && e.isSourceLoaded === false && e.tile) {
        // Track tile activity lightly.
      }
      if (e.sourceDataType === "metadata" || e.sourceDataType === "content") {
        state.dataEvents.push({
          t: Date.now(),
          dataType: e.dataType,
          sourceDataType: e.sourceDataType,
          sourceId: e.sourceId,
          isSourceLoaded: e.isSourceLoaded,
        });
        if (state.dataEvents.length > 30) state.dataEvents.shift();
      }
      if (e.error || (e.tile && e.tile.aborted === false && e.tile.state && String(e.tile.state).indexOf("errored") >= 0)) {
        state.tileErrors.push({
          t: Date.now(),
          message: "data event tile issue",
          sourceId: e.sourceId,
        });
      }
    });
  }

  function loadReadyCountries(opts) {
    var root = mapsRoot();
    var pmtilesBase = root + "/pmtiles/";
    var countriesUrl = root + "/countries.json";
    var catalogueUrl =
      (opts && opts.catalogueUrl) || global.location.origin + "/api/content/catalogue";
    var repairUrl = catalogueUrl.replace(/\/api\/content\/catalogue$/, "/api/content/maps-repair");

    return fetch(repairUrl, { cache: "no-store", credentials: "same-origin" })
      .catch(function () {})
      .then(function () {
        return fetchJson(countriesUrl).catch(function () {
          return { countries: {} };
        });
      })
      .then(function (doc) {
        var registry = normalizeRegistry(doc);
        return fetchJson(catalogueUrl)
          .catch(function () {
            return { packs: [] };
          })
          .then(function (cat) {
            var hints = {};
            (cat.packs || []).forEach(function (p) {
              if ((p.category || "").includes("map") || (p.type || "").includes("map")) {
                var cc = String(p.country || "").toLowerCase();
                if (cc) hints[cc] = p;
              }
            });
            var ready = [];
            var pending = [];
            var seen = {};

            function consider(cc, row) {
              if (!cc || seen[cc]) return Promise.resolve();
              seen[cc] = true;
              return headOk(pmtilesBase + cc + ".pmtiles").then(function (tilesOk) {
                if (tilesOk) {
                  var hint = hints[cc] || {};
                  ready.push({
                    code: cc,
                    name: (row && row.name) || hint.name || cc.toUpperCase(),
                    center: (row && row.center) || hint.center || null,
                    bbox: (row && row.bbox) || hint.bbox || null,
                  });
                } else if (
                  (row && (row.status === "stub" || row.status === "ready" || row.status === "listed")) ||
                  (hints[cc] &&
                    (hints[cc].installed ||
                      hints[cc].tiles_status === "ready" ||
                      hints[cc].tiles_status === "fetching"))
                ) {
                  pending.push((row && row.name) || (hints[cc] && hints[cc].name) || cc.toUpperCase());
                }
              });
            }

            var chain = Promise.resolve();
            registry.forEach(function (row) {
              chain = chain.then(function () {
                return consider(row.code, row);
              });
            });
            Object.keys(hints).forEach(function (cc) {
              var hint = hints[cc];
              if (hint.installed || hint.tiles_status === "ready") {
                chain = chain.then(function () {
                  return consider(cc, {
                    name: hint.name,
                    center: hint.center,
                    bbox: hint.bbox,
                    status: hint.tiles_status || "listed",
                  });
                });
              }
            });
            return chain.then(function () {
              if (!ready.length) {
                var probes = ["uk", "ie", "de", "fr", "us"];
                var pchain = Promise.resolve();
                probes.forEach(function (cc) {
                  pchain = pchain.then(function () {
                    if (
                      ready.some(function (r) {
                        return r.code === cc;
                      })
                    )
                      return;
                    return headOk(pmtilesBase + cc + ".pmtiles").then(function (ok) {
                      if (ok)
                        ready.push({
                          code: cc,
                          name: cc.toUpperCase(),
                          center: null,
                          bbox: null,
                        });
                    });
                  });
                });
                return pchain.then(function () {
                  return { ready: ready, pending: pending };
                });
              }
              return { ready: ready, pending: pending };
            });
          });
      });
  }

  function showCountry(code, mountGen) {
    var gen = mountGen || state.mountGen;
    var c =
      state.countries.find(function (x) {
        return x.code === code;
      }) || { code: code };
    var root = mapsRoot();
    var assetsBase = root + "/basemaps-assets/";
    var tileUrl = root + "/pmtiles/" + code + ".pmtiles";
    clearError();
    state.tileErrors = [];
    state.dataEvents = [];
    state.paintFallbackTried = false;
    setStatus("Loading " + (c.name || code) + "…");

    return assertRangeSupport(tileUrl)
      .then(function () {
        if (gen !== state.mountGen) return null;
        setStatus("Fetching basemap assets…");
        return assertBasemapAssets(assetsBase);
      })
      .then(function (spriteVer) {
        if (gen !== state.mountGen || spriteVer == null) return;
        setStatus("Reading tile archive layers…");
        return readArchiveInfo(tileUrl).then(function (info) {
          if (gen !== state.mountGen) return;
          state.lastHeader = info.header;
          state.lastArchiveLayers = info.layers || [];
          var built = buildStyle(
            code,
            info.layers,
            tileUrl,
            info.header,
            assetsBase,
            spriteVer,
            false
          );
          setStatus(
            "Style " +
              built.mode +
              (info.layers.length ? " · layers " + info.layers.join(",") : " · layers unknown")
          );
          try {
            applyStyle(built, c, gen);
          } catch (err) {
            showError(
              "MapLibre constructor failed",
              err && err.message ? err.message : String(err)
            );
            showDiag(
              collectDiagnostics({
                constructorError: err && err.message ? err.message : String(err),
              })
            );
            throw err;
          }
          // Defer diagnostics until style is in sourceCaches — early isSourceLoaded('…')
          // used to spam "There is no source with ID 'uk'".
          if (wantDebug()) {
            showDiag({
              phase: "style-queued",
              styleMode: built.mode,
              archiveLayers: info.layers,
              header: info.header,
              sourceId: TILE_SOURCE,
              sourcesInStyle: built.style && built.style.sources
                ? Object.keys(built.style.sources)
                : [],
              layerCount: built.style && built.style.layers ? built.style.layers.length : 0,
              hint: "Full runtime diag appears after idle / paint verify.",
            });
          }
        });
      })
      .catch(function (e) {
        if (gen !== state.mountGen) return;
        showError("Cannot load map tiles", e && e.message ? e.message : e);
        showDiag(
          collectDiagnostics({ loadError: e && e.message ? e.message : String(e) })
        );
      });
  }

  function unmount() {
    if (state.resizeTimer) {
      clearTimeout(state.resizeTimer);
      state.resizeTimer = null;
    }
    if (state.resizeObserver) {
      try {
        state.resizeObserver.disconnect();
      } catch (_) {}
      state.resizeObserver = null;
    }
    if (state.map) {
      try {
        state.map.remove();
      } catch (_) {}
      state.map = null;
    }
    if (state.host) {
      try {
        state.host.innerHTML = "";
      } catch (_) {}
      state.host = null;
    }
    state.ui = null;
    state.countries = [];
    state.opts = null;
  }

  function mount(host, opts) {
    opts = opts || {};
    if (!host) return Promise.reject(new Error("AtlasMaps.mount: missing host element"));
    if (!host.isConnected) {
      return Promise.reject(
        new Error("AtlasMaps.mount: host is not in the document (stale page() race)")
      );
    }
    unmount();
    var gen = ++state.mountGen;
    state.host = host;
    state.opts = opts;
    state.debug = !!(opts && opts.debug) || wantDebug();
    state.ui = buildHostChrome(host, opts);
    setStatus("Loading map libraries…");

    return ensureLibs()
      .then(function () {
        if (gen !== state.mountGen || state.host !== host) return null;
        ensureProtocol();
        setStatus("Discovering ready countries…");
        return loadReadyCountries(opts);
      })
      .then(function (info) {
        if (gen !== state.mountGen || state.host !== host || !info) return;
        state.countries = info.ready || [];
        if (!state.countries.length) {
          if (info.pending && info.pending.length) {
            showEmptyOverlay(
              "Map packs are installed but tiles are not ready yet (" +
                info.pending
                  .slice(0, 6)
                  .map(function (n) {
                    return "<strong>" + escapeHtml(n) + "</strong>";
                  })
                  .join(", ") +
                "). Install / retry from <a href=\"" +
                escapeHtml(state.ui.contentUrl) +
                '">Content</a> and wait for the tile download to finish, then refresh.'
            );
          } else {
            showEmptyOverlay(
              "No ready country maps yet. Install a country pack in Command Centre → <a href=\"" +
                escapeHtml(state.ui.contentUrl) +
                '">Content</a>, wait until tiles are <strong>ready</strong>, then open Maps again.'
            );
          }
          return;
        }
        // Tiles ready (or URL names a country): never leave the Open Content CTA on screen.
        hideEmptyOverlay();
        setPanelVisible(state.ui.bar, true, "flex");
        state.ui.select.innerHTML = state.countries
          .map(function (c) {
            return (
              '<option value="' +
              escapeHtml(c.code) +
              '">' +
              escapeHtml(c.name) +
              " (" +
              escapeHtml(c.code.toUpperCase()) +
              ")</option>"
            );
          })
          .join("");

        var initial =
          state.countries.find(function (c) {
            return c.code === "uk";
          }) || state.countries[0];
        var q = (opts && opts.country) || null;
        if (!q && typeof URLSearchParams !== "undefined") {
          q = new URLSearchParams(global.location.search).get("country");
        }
        if (q) {
          var hit = state.countries.find(function (c) {
            return c.code === String(q).toLowerCase();
          });
          if (hit) initial = hit;
        }
        state.ui.select.value = initial.code;
        state.ui.select.addEventListener("change", function () {
          hideEmptyOverlay();
          showCountry(state.ui.select.value, gen);
        });
        state.ui.fitBtn.addEventListener("click", function () {
          var c = state.countries.find(function (x) {
            return x.code === state.ui.select.value;
          });
          flyToCountry(c);
        });
        setStatus("Starting map for " + (initial.name || initial.code) + "…");
        return showCountry(initial.code, gen);
      })
      .catch(function (e) {
        if (gen !== state.mountGen) return;
        // If MapLibre already painted, keep the map visible — show error chrome only.
        if (state.tilesPainted) {
          hideEmptyOverlay();
          showError(String(e && e.message ? e.message : e));
          showDiag({ mountError: String(e && e.message ? e.message : e), painted: true });
          return;
        }
        showEmptyOverlay(escapeHtml(String(e && e.message ? e.message : e)));
        showError(String(e && e.message ? e.message : e));
        showDiag({ mountError: String(e && e.message ? e.message : e) });
      });
  }

  global.AtlasMaps = {
    mount: mount,
    unmount: unmount,
    resize: ensureMapSize,
    ensureLibs: ensureLibs,
    /** Exposed for unit tests / console debugging. */
    _test: {
      PROTOMAPS_V4: PROTOMAPS_V4,
      TILE_SOURCE: TILE_SOURCE,
      DIAG_SOURCE: DIAG_SOURCE,
      layerNamesFromMeta: layerNamesFromMeta,
      isProtomapsV4: isProtomapsV4,
      buildPaintFirstStyle: buildPaintFirstStyle,
      buildStyle: buildStyle,
      pmtilesSource: pmtilesSource,
      assertStyleSources: assertStyleSources,
      safeSourceLoaded: safeSourceLoaded,
      wantPretty: wantPretty,
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
