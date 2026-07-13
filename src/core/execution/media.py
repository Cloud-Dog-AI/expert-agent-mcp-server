"""Satellite/topographic location maps and licence-aware Wikimedia Commons imagery.

Two self-contained capabilities used to *embellish* a generated report (no external
service needed beyond public tile/Commons endpoints the expert can already reach):

* ``render_location_map`` — composite real web tiles (ESRI World Imagery satellite,
  ESRI World Topo, or OSM) under markers / areas-of-control / lines, auto-zoomed to a
  bbox, returned as a base64 PNG. Used for per-section detail maps (e.g. a Donbas
  satellite view) while the theatre overview keeps its clean vector style.

* ``fetch_commons_image`` — search Wikimedia Commons for a subject and return a single
  image ONLY when its licence clearly permits reuse, together with the source link,
  author and licence so the report can attribute it. Anything with an unknown or
  non-free licence, or any usage restriction, is skipped.

Everything is best-effort: any failure returns ``None`` so report generation is never
blocked by a missing tile or image.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import ssl
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Natural Earth country polygons (same bundled data the theatre map uses) for the geopolitical
# overlay on satellite detail maps — country borders + names so the imagery has real context.
_NE_DIR = os.path.join(os.path.dirname(__file__), "data")
_NE_PATH = next((p for p in (os.path.join(_NE_DIR, "ne_10m_admin0.json"),
                             os.path.join(_NE_DIR, "ne_50m_admin0.json")) if os.path.exists(p)), None)
_ADMIN1_PATH = os.path.join(_NE_DIR, "ne_admin1_ua.json")  # Ukraine oblasts + Russian border regions (geoBoundaries, ODbL)
_NE_CACHE: Optional[Dict[str, Any]] = None
_ADMIN1_CACHE: Optional[Dict[str, Any]] = None
# Macro-regions / water bodies with no admin1 polygon — point labels only: name -> (lon, lat).
_REGION_LABELS = {
    "Donbas": (38.2, 48.4), "Sea of Azov": (36.7, 46.1), "Black Sea": (32.0, 44.0),
}


def _load_json_cached(path: str, ref: str) -> Optional[Dict[str, Any]]:
    """Load bundled GeoJSON once, returning an empty mapping on read failures."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("media: %s data unavailable (%s)", ref, exc)
        return {}


def _load_ne() -> Optional[Dict[str, Any]]:
    """Return cached Natural Earth admin0 features when the bundled file exists."""
    global _NE_CACHE
    if _NE_CACHE is None and _NE_PATH:
        _NE_CACHE = _load_json_cached(_NE_PATH, "Natural Earth admin0")
    return _NE_CACHE or None


def _load_admin1() -> Optional[Dict[str, Any]]:
    """Return cached admin1 boundary features for regional overlays."""
    global _ADMIN1_CACHE
    if _ADMIN1_CACHE is None:
        _ADMIN1_CACHE = _load_json_cached(_ADMIN1_PATH, "admin1 oblasts") if os.path.exists(_ADMIN1_PATH) else {}
    return _ADMIN1_CACHE or None

_TILE_SIZE = 256
# Outbound tile/image fetch User-Agent. Internal deploys may set
# CLOUD_DOG__EXPERT__MEDIA__USER_AGENT to supply a contact string.
_UA = str(
    get_config(
        "media.user_agent",
        "cloud-dog-demo/1.0 research-report-imagery",
    )
    or "cloud-dog-demo/1.0 research-report-imagery"
)
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Tile backends. {z}/{x}/{y}; attribution shown on the map per provider terms.
_TILES = {
    "satellite": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                  "Imagery © Esri, Maxar, Earthstar Geographics"),
    "topo": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
             "© Esri — World Topographic Map"),
    "osm": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            "© OpenStreetMap contributors"),
}

# Licences we will embed (free / attribution-only / share-alike / public domain).
_OK_LICENCE = re.compile(r"\b(cc[\s-]?0|cc[\s-]?by(?:[\s-]?sa)?(?:[\s-]?\d(?:\.\d)?)?|public[\s-]?domain|pd[\s-]?\w+)\b", re.I)
# Licences / flags that forbid or cast doubt on reuse -> never embed.
_BAD_LICENCE = re.compile(r"\b(non[\s-]?free|fair[\s-]?use|all[\s-]?rights[\s-]?reserved|cc[\s-]?by[\s-]?n[cd]|no[\s-]?deriv|copyright)\b", re.I)
# File titles whose TYPE makes them a poor illustrative match for a news report — heraldry,
# emblems, flags, maps, charts, historical artworks, logos — skip these and try the next hit
# (this is what dropped a unit *coat of arms* in for "tank" and a *painting* in for "United States").
_OFFTOPIC_TYPE = re.compile(
    r"\b(coat[\s-]?of[\s-]?arms|insignia|emblem|ensign|\bbadge\b|sleeve\s*insignia|patch|"
    r"\bflag\b|banner|\bstandard\b|\bseal\b|logo|crest|heraldr|"
    r"map\s*of|locator|diagram|schematic|\bchart\b|infographic|"
    r"painting|portrait|engraving|lithograph|woodcut|drawing|sketch|cartoon|caricature|"
    r"constitutional\s+convention|coin|banknote|medal|postage|\bstamp\b)\b", re.I)


def _http_get(url: str, timeout: int = 8) -> bytes:
    """Fetch bytes from a public imagery endpoint with the configured user agent."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, context=_CTX, timeout=timeout) as r:
        return r.read()


# --------------------------------------------------------------------------- maps
def _lonlat_to_px(lon: float, lat: float, z: int) -> Tuple[float, float]:
    """Web-Mercator global pixel coordinate (tile*256) for a lon/lat at zoom ``z``."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n * _TILE_SIZE
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n * _TILE_SIZE
    return x, y


def _pick_zoom(bbox: List[float], target_px: int = 1100, max_tiles: int = 49) -> int:
    """Largest zoom whose mosaic is <= ~target_px wide and within the tile budget."""
    west, south, east, north = bbox
    for z in range(13, 1, -1):
        x0, y0 = _lonlat_to_px(west, north, z)
        x1, y1 = _lonlat_to_px(east, south, z)
        w, h = abs(x1 - x0), abs(y1 - y0)
        tiles = (math.ceil(max(w, h) / _TILE_SIZE) + 1) ** 2
        if max(w, h) <= target_px and tiles <= max_tiles:
            return z
    return 5


def _basemap(bbox: List[float], style: str) -> Optional[Tuple[Any, Tuple[float, float, float, float], int]]:
    """Fetch + stitch tiles covering ``bbox``; return (PIL image, px_extent, zoom).

    ``px_extent`` = (px_min, px_max, py_min, py_max) in global-pixel space at ``zoom``.
    """
    from PIL import Image
    url_tpl, _ = _TILES.get(style, _TILES["satellite"])
    z = _pick_zoom(bbox)
    west, south, east, north = bbox
    x0, y0 = _lonlat_to_px(west, north, z)
    x1, y1 = _lonlat_to_px(east, south, z)
    px_min, px_max = min(x0, x1), max(x0, x1)
    py_min, py_max = min(y0, y1), max(y0, y1)
    tx0, tx1 = int(px_min // _TILE_SIZE), int(px_max // _TILE_SIZE)
    ty0, ty1 = int(py_min // _TILE_SIZE), int(py_max // _TILE_SIZE)
    n = 2 ** z
    cols, rows = (tx1 - tx0 + 1), (ty1 - ty0 + 1)
    mosaic = Image.new("RGB", (cols * _TILE_SIZE, rows * _TILE_SIZE), (40, 40, 40))

    def _one(tx: int, ty: int):
        """Fetch one map tile and return it with tile coordinates."""
        if not (0 <= ty < n):
            return None
        url = url_tpl.format(z=z, x=tx % n, y=ty)
        try:
            return (tx, ty, Image.open(io.BytesIO(_http_get(url))).convert("RGB"))
        except Exception:
            return None

    jobs = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    ok = 0
    for tx, ty in jobs:
        res = _one(tx, ty)
        if res:
            tile_x, tile_y, im = res
            mosaic.paste(im, ((tile_x - tx0) * _TILE_SIZE, (tile_y - ty0) * _TILE_SIZE))
            ok += 1
    if ok == 0:
        return None
    # crop the mosaic to the exact pixel bbox
    left = px_min - tx0 * _TILE_SIZE
    top = py_min - ty0 * _TILE_SIZE
    right = left + (px_max - px_min)
    bottom = top + (py_max - py_min)
    crop = mosaic.crop((int(left), int(top), int(right), int(bottom)))
    return crop, (px_min, px_max, py_min, py_max), z


def render_location_map(bbox: List[float], *, markers: Optional[List[Dict[str, Any]]] = None,
                        areas: Optional[List[Dict[str, Any]]] = None,
                        lines: Optional[List[Dict[str, Any]]] = None,
                        title: str = "", style: str = "satellite") -> Optional[str]:
    """Render a detail map: real ``style`` tiles under markers/areas/lines for ``bbox``
    ([west, south, east, north]). Returns a base64 PNG, or None on failure.

    ``markers``: ``[{"lon","lat","label"}]``; ``areas``: ``[{"coords":[[lon,lat],...],
    "fill":[r,g,b,a],"label"}]``; ``lines``: ``[{"coords":[[lon,lat],...],"colour":[r,g,b]}]``.
    """
    try:
        base = _basemap(bbox, style)
        if not base:
            return None
        img, (px_min, px_max, py_min, py_max), z = base
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon

        w_px, h_px = img.size
        dpi = 100.0
        fig, ax = plt.subplots(figsize=(max(4.0, w_px / dpi), max(3.0, h_px / dpi)), dpi=dpi)
        ax.imshow(img, extent=(px_min, px_max, py_max, py_min), zorder=0)  # note inverted y
        ax.set_xlim(px_min, px_max)
        ax.set_ylim(py_max, py_min)

        def P(lon, lat):
            """Project lon/lat pairs into the basemap pixel extent."""
            return _lonlat_to_px(lon, lat, z)

        _draw_geo_overlay(ax, bbox, z, P, style)  # borders + labels (satellite only; OSM/topo self-label)

        for a in (areas or []):
            pts = [P(lo, la) for lo, la in (a.get("coords") or []) if isinstance(lo, (int, float))]
            if len(pts) >= 3:
                f = a.get("fill") or [200, 60, 50, 70]
                ax.add_patch(MplPolygon(pts, closed=True, facecolor=(f[0] / 255, f[1] / 255, f[2] / 255,
                             (f[3] if len(f) > 3 else 80) / 255), edgecolor=(f[0] / 255, f[1] / 255, f[2] / 255, 0.95),
                             linewidth=1.6, zorder=2))
        for ln in (lines or []):
            pts = [P(lo, la) for lo, la in (ln.get("coords") or [])]
            if len(pts) >= 2:
                c = ln.get("colour") or [220, 30, 30]
                ax.plot([p[0] for p in pts], [p[1] for p in pts],
                        color=(c[0] / 255, c[1] / 255, c[2] / 255), linewidth=ln.get("width", 3), zorder=3)
        for m in (markers or []):
            try:
                x, y = P(float(m["lon"]), float(m["lat"]))
            except Exception:
                continue
            ax.plot(x, y, "o", markersize=7, markerfacecolor="#ffd23f",
                    markeredgecolor="#1a1a1a", markeredgewidth=1.2, zorder=4)
            lab = m.get("label")
            if lab:
                ax.annotate(_ascii(str(lab)), (x, y), xytext=(7, 5), textcoords="offset points",
                            fontsize=9, fontweight="bold", color="white", zorder=5,
                            path_effects=_halo())
        ax.set_axis_off()
        if title:
            ax.set_title(_ascii(title), fontsize=12, fontweight="bold", color="#16243a", pad=8)
        attribution = _TILES.get(style, _TILES["satellite"])[1] + " · Boundaries: Natural Earth, geoBoundaries (ODbL)"
        ax.text(0.995, 0.012, attribution, transform=ax.transAxes, ha="right", va="bottom",
                fontsize=6.5, color="white", path_effects=_halo(1.4))
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.06, dpi=dpi)
        plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return b64 if base64.b64decode(b64)[:4] == b"\x89PNG" else None
    except Exception as exc:
        logger.warning("media: render_location_map failed: %s", exc)
        return None


def _halo(lw: float = 2.0):
    """Build a black text halo for readable labels on imagery."""
    import matplotlib.patheffects as pe
    return [pe.withStroke(linewidth=lw, foreground="black")]


def _ascii(s: str) -> str:
    """Return an ASCII-safe label while preserving the original if conversion empties it."""
    import unicodedata
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii") or str(s)


def _draw_geo_overlay(ax, bbox: List[float], z: int, P, style: str = "satellite") -> None:
    """Overlay country borders (cased line, satellite shows through) + country/oblast and key-region
    labels, clipped to ``bbox``, so a *satellite* detail map carries geopolitical context instead
    of bare terrain. Skipped for OSM/topo bases, which already render borders, place names and
    water labels in proper cartographic style. Best-effort: no-ops if shapely / NE data missing."""
    if style != "satellite":
        return
    try:
        from shapely.geometry import shape as _shape, box as _box
    except Exception:
        return
    fc = _load_ne()
    if not fc:
        return
    try:
        clip = _box(bbox[0], bbox[1], bbox[2], bbox[3])
        cb = clip.bounds
        view_area = abs((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
        for feat in fc.get("features", []):
            geom = feat.get("geometry")
            if not geom:
                continue
            try:
                g = _shape(geom)
            except Exception:
                continue
            b = g.bounds  # cheap reject before the expensive intersection
            if b[2] < cb[0] or b[0] > cb[2] or b[3] < cb[1] or b[1] > cb[3]:
                continue
            try:
                gi = g.buffer(0).intersection(clip)
            except Exception:
                continue
            if gi.is_empty:
                continue
            for gg in ([gi] if gi.geom_type == "Polygon" else list(getattr(gi, "geoms", []))):
                if gg.is_empty or gg.geom_type != "Polygon":
                    continue
                xs, ys = zip(*[P(x, y) for x, y in gg.exterior.coords])
                ax.plot(xs, ys, color="black", linewidth=3.0, alpha=0.4, zorder=1)        # casing
                ax.plot(xs, ys, color="#fff3c4", linewidth=1.3, alpha=0.95, zorder=1.1)   # border
            p = feat.get("properties", {})
            name = p.get("NAME") or p.get("ADMIN") or p.get("NAME_LONG") or ""
            if name and gi.area > view_area * 0.04:
                try:
                    rp = gi.representative_point()
                    x, y = P(rp.x, rp.y)
                    ax.annotate(_ascii(name).upper(), (x, y), ha="center", va="center",
                                fontsize=11, fontweight="bold", color="white", alpha=0.92,
                                zorder=1.2, path_effects=_halo(2.4))
                except Exception:
                    pass
        # Sub-national: actual drawn oblast/region boundaries (thin, so distinct from country
        # borders) + an oblast label at each region's point, clipped to the view.
        a1 = _load_admin1()
        for feat in (a1.get("features", []) if a1 else []):
            geom = feat.get("geometry")
            if not geom:
                continue
            try:
                g = _shape(geom)
            except Exception:
                continue
            b = g.bounds
            if b[2] < cb[0] or b[0] > cb[2] or b[3] < cb[1] or b[1] > cb[3]:
                continue
            try:
                gi = g.buffer(0).intersection(clip)
            except Exception:
                continue
            if gi.is_empty:
                continue
            for gg in ([gi] if gi.geom_type == "Polygon" else list(getattr(gi, "geoms", []))):
                if gg.is_empty or gg.geom_type != "Polygon":
                    continue
                xs, ys = zip(*[P(x, y) for x, y in gg.exterior.coords])
                ax.plot(xs, ys, color="black", linewidth=1.6, alpha=0.35, zorder=1.15)
                ax.plot(xs, ys, color="#ffe6a0", linewidth=0.8, alpha=0.85, zorder=1.16,
                        dashes=(5, 3))
            nm = str((feat.get("properties") or {}).get("name") or "")
            if nm and gi.area > view_area * 0.03:
                try:
                    rp = gi.representative_point()
                    x, y = P(rp.x, rp.y)
                    ax.annotate(_ascii(nm), (x, y), ha="center", va="center", fontsize=8.5,
                                fontstyle="italic", color="#ffe9a8", alpha=0.92, zorder=1.2,
                                path_effects=_halo(1.8))
                except Exception:
                    pass
        for rname, (rlon, rlat) in _REGION_LABELS.items():
            if bbox[0] < rlon < bbox[2] and bbox[1] < rlat < bbox[3]:
                x, y = P(rlon, rlat)
                ax.annotate(_ascii(rname), (x, y), ha="center", va="center", fontsize=8.5,
                            fontstyle="italic", color="#ffe9a8", alpha=0.9, zorder=1.2,
                            path_effects=_halo(1.8))
    except Exception as exc:
        logger.warning("media: geo overlay failed: %s", exc)


# ------------------------------------------------------------------- commons images
def _commons_api(params: Dict[str, str]) -> Dict[str, Any]:
    """Call the Wikimedia Commons API and decode the JSON response."""
    params = {**params, "format": "json"}
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    return json.loads(_http_get(url).decode("utf-8", "replace"))


def _strip_html(s: Any) -> str:
    """Remove simple HTML tags from Commons metadata fields."""
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def fetch_commons_image(subject: str, *, max_px: int = 1024) -> Optional[Dict[str, Any]]:
    """Return a single licence-cleared Wikimedia Commons image for ``subject`` or None.

    The image is embedded ONLY when its licence clearly permits reuse (CC0 / CC-BY /
    CC-BY-SA / public domain) and carries no usage restriction. Returns a dict with the
    base64 ``data`` plus everything needed to attribute it: ``source_url``, ``author``,
    ``licence`` and ``licence_url``.
    """
    try:
        sr = _commons_api({"action": "query", "list": "search", "srsearch": subject,
                           "srnamespace": "6", "srlimit": "6"})
        hits = sr.get("query", {}).get("search", [])
        for hit in hits:
            title = hit.get("title")
            if not title:
                continue
            low = title.lower()
            if any(low.endswith(e) for e in (".svg", ".pdf", ".ogg", ".webm", ".ogv", ".tif", ".gif")):
                continue
            # Skip heraldry / flags / maps / artworks unless the subject explicitly wants one.
            if _OFFTOPIC_TYPE.search(title) and not _OFFTOPIC_TYPE.search(subject):
                continue
            info = _commons_api({"action": "query", "titles": title, "prop": "imageinfo",
                                "iiprop": "url|extmetadata|mime", "iiurlwidth": str(max_px)})
            pages = info.get("query", {}).get("pages", {})
            ii = (list(pages.values())[0].get("imageinfo") or [{}])[0] if pages else {}
            if not ii:
                continue
            em = ii.get("extmetadata", {})

            def meta(k: str) -> str:
                """Extract a normalised Commons extmetadata value."""
                v = em.get(k)
                return _strip_html(v.get("value")) if isinstance(v, dict) else _strip_html(v)

            lic_short = meta("LicenseShortName") or meta("License")
            lic_id = (meta("License") or lic_short)
            restrictions = meta("Restrictions")
            usage = meta("UsageTerms")
            blob = " ".join([lic_short, lic_id, usage])
            if restrictions or _BAD_LICENCE.search(blob) or not _OK_LICENCE.search(blob):
                continue  # unknown / non-free / restricted -> never embed
            mime = str(ii.get("mime") or "")
            thumb = ii.get("thumburl") or ii.get("url")
            if not thumb or "image/" not in (mime or "image/"):
                continue
            try:
                raw = _http_get(thumb, timeout=8)
            except Exception:
                continue
            if raw[:4] != b"\x89PNG" and raw[:3] != b"\xff\xd8\xff":  # PNG or JPEG only
                continue
            author = meta("Artist") or meta("Credit") or "Wikimedia Commons"
            return {
                "subject": subject,
                "data": base64.b64encode(raw).decode("ascii"),
                "content_type": "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg",
                "source_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                "image_url": ii.get("url") or thumb,
                "author": author[:120] or "Wikimedia Commons",
                "licence": lic_short or lic_id or "see source",
                "licence_url": meta("LicenseUrl"),
                "title": title,
            }
        return None
    except Exception as exc:
        logger.warning("media: fetch_commons_image(%r) failed: %s", subject, exc)
        return None
