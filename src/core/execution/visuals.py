# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Additive figure pipeline for the document strategy (maps + charts as inline CID images).

This module is **pure presentation plumbing** layered on top of the existing document
pipeline (PS-96 §14 integration glue — no agent loop, no memory store). Given a small,
data-driven ``visuals`` spec supplied by the schedule, it renders:

  * **real-backdrop maps** via the geospatial MCP service's ``geo_render_map`` tool —
    Natural Earth country polygons (bundled, loaded from ``data/ne_50m_admin0.json``, NOT
    fetched at runtime) form the bottom backdrop layers, with styled marker/line/control
    overlays drawn on top; and
  * **varied charts** via the chart MCP service's ``render`` tool — which returns an
    ``asset_id``; the PNG bytes are then fetched over the chart service's REST asset
    endpoint (``GET <base>/api/assets/{id}``) using the same credential the composition
    layer resolves for that service.

It returns ``(inline_images, figures)`` where each inline image is a CID attachment
(``{content_id, content_type, data, filename}``) and each figure is a placement record
(``{content_id, caption, after_heading}``) the document strategy uses to inject an
``<img src="cid:ID">`` at the right heading.

Everything degrades gracefully: a map or chart that fails to render is skipped (logged)
and the rest of the report still sends. Map / label / legend / title text is ASCII-folded
because the renderer's bitmap font draws tofu boxes for accented / em-dash glyphs.
"""

from __future__ import annotations

import base64
import json
import math
import os
import unicodedata
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Bundled Natural Earth admin-0 country polygons. Loaded from disk, never the network —
# the runtime container may have no egress (see PS-96 search/crawl DNS notes). We prefer
# the finer 10m dataset (sharper coastlines + island detail) and fall back to 50m if the
# 10m file is not bundled in this build.
_NE_DIR = os.path.join(os.path.dirname(__file__), "data")
_NE_PATH_10M = os.path.join(_NE_DIR, "ne_10m_admin0.json")
_NE_PATH_50M = os.path.join(_NE_DIR, "ne_50m_admin0.json")
_NE_PATH = _NE_PATH_10M if os.path.exists(_NE_PATH_10M) else _NE_PATH_50M

# bbox area cap enforced by the geo renderer (deg^2). We keep maps under this. Raised to match
# the geo service's governed limit (15000) so continental geopolitical "zone" maps render.
_BBOX_AREA_CAP = 15000.0

# shapely is optional: it is only needed to clip a rough control polygon to a country's
# real coastline. If it is absent (e.g. the pure-UT venv) we fall back to the unclipped
# polygon rather than failing the whole figure.
try:  # pragma: no cover - import guard
    from shapely.geometry import Polygon as _ShPolygon, box as _sh_box, mapping as _sh_mapping, shape as _sh_shape

    _HAVE_SHAPELY = True
except Exception:  # pragma: no cover - import guard
    _HAVE_SHAPELY = False

# matplotlib is optional: when present we render rich, varied, well-styled charts locally
# (grouped/stacked/horizontal bars, donut, multi-series line, area) instead of the chart
# MCP service's single-colour bar/line. When absent we fall back to the chart MCP service.
try:  # pragma: no cover - import guard
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as _plt

    _HAVE_MPL = True
except Exception:  # pragma: no cover - import guard
    _HAVE_MPL = False

# A clean, print-friendly categorical palette reused across every local chart type.
_CHART_PALETTE = ["#2f6f8f", "#c1654b", "#5a9367", "#d8a657", "#7d6b9e", "#4a4e69", "#9d8189", "#52796f"]


def _ascii(s: Any) -> str:
    """Fold to ASCII so the renderer's bitmap font never draws tofu boxes."""
    s = str(s).replace("—", "-").replace("–", "-").replace("’", "'")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


# --------------------------------------------------------------------------- #
# Natural Earth backdrop helpers (ported from the proven geokit/geokit2 kit)
# --------------------------------------------------------------------------- #
_NE_CACHE: Dict[str, Any] = {}


def _load_ne() -> Dict[str, Any]:
    """Load (and cache) the bundled Natural Earth admin-0 FeatureCollection."""
    if "fc" not in _NE_CACHE:
        with open(_NE_PATH, "r", encoding="utf-8") as fh:
            _NE_CACHE["fc"] = json.load(fh)
    return _NE_CACHE["fc"]


def _country_geometry(name: str) -> Optional[Dict[str, Any]]:
    """Return the GeoJSON geometry for a country by NAME/ADMIN/NAME_LONG/SOVEREIGNT."""
    try:
        fc = _load_ne()
    except Exception as exc:  # pragma: no cover - only if the data file is missing
        logger.warning("visuals: Natural Earth data unavailable (%s); maps will have no backdrop", exc)
        return None
    for feat in fc.get("features", []):
        p = feat.get("properties", {})
        if name in (p.get("NAME"), p.get("ADMIN"), p.get("NAME_LONG"), p.get("SOVEREIGNT")):
            return feat.get("geometry")
    return None


def _backdrop_layers(
    focus: Any,
    neighbours: List[str],
    focus_fill: Tuple[int, int, int] = (238, 233, 214),
    other_fill: Tuple[int, int, int] = (225, 227, 222),
) -> List[Dict[str, Any]]:
    """Bottom backdrop layers: neighbours muted, focus country highlighted, both bordered."""
    layers: List[Dict[str, Any]] = []
    for n in neighbours or []:
        g = _country_geometry(n)
        if g:
            layers.append({"type": "polygon", "geometry": g, "fill": list(other_fill) + [255],
                           "stroke": [175, 177, 172], "stroke_width": 1})
    focus_list = focus if isinstance(focus, (list, tuple)) else [focus]
    for n in focus_list:
        if not n:
            continue
        g = _country_geometry(n)
        if g:
            layers.append({"type": "polygon", "geometry": g, "fill": list(focus_fill) + [255],
                           "stroke": [120, 110, 80], "stroke_width": 2})
    return layers


def _all_country_layers(
    bbox: List[float],
    highlight: Any = None,
    label_countries: bool = True,
    land_fill: Tuple[int, int, int] = (236, 233, 224),
    highlight_fill: Tuple[int, int, int] = (210, 223, 208),
) -> Optional[List[Dict[str, Any]]]:
    """Backdrop layers for **every** Natural Earth country that intersects ``bbox``,
    each clipped to the bbox via shapely (this fixes the antimeridian artefact that
    dropped the USA's contiguous landmass on continental maps) and — when
    ``label_countries`` — labelled at its representative point. Countries named in
    ``highlight`` get a distinct fill + heavier border.

    Returns ``None`` when shapely is unavailable so the caller can fall back to the
    simpler explicit focus/neighbours backdrop.
    """
    if not _HAVE_SHAPELY:
        return None
    try:
        fc = _load_ne()
    except Exception as exc:  # pragma: no cover - only if the data file is missing
        logger.warning("visuals: Natural Earth data unavailable (%s); maps will have no backdrop", exc)
        return None
    hl = {str(h) for h in (highlight or [])}
    clip = _sh_box(bbox[0], bbox[1], bbox[2], bbox[3])
    cb = clip.bounds
    # min country area (deg^2) to bother labelling — scales with the viewport so tiny
    # sliver intersections at the bbox edge don't get a label.
    min_label_area = abs((bbox[2] - bbox[0]) * (bbox[3] - bbox[1])) * 0.0008
    polys: List[Dict[str, Any]] = []
    labels: List[Dict[str, Any]] = []
    for feat in fc.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            g = _sh_shape(geom)
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
        p = feat.get("properties", {})
        name = p.get("NAME") or p.get("ADMIN") or p.get("NAME_LONG") or ""
        is_hl = name in hl
        fill = (list(highlight_fill) if is_hl else list(land_fill)) + [255]
        stroke = [70, 90, 70] if is_hl else [140, 140, 130]
        width = 2 if is_hl else 1
        geoms = [gi] if gi.geom_type == "Polygon" else list(getattr(gi, "geoms", []))
        for gg in geoms:
            if not gg.is_empty:
                polys.append({"type": "polygon", "geometry": _sh_mapping(gg),
                              "fill": fill, "stroke": stroke, "stroke_width": width})
        if label_countries and gi.area > min_label_area:
            try:
                rp = gi.representative_point()
            except Exception:
                continue
            if bbox[0] < rp.x < bbox[2] and bbox[1] < rp.y < bbox[3]:
                labels.append({"type": "label", "at": [rp.x - 1.0, rp.y],
                               "text": _ascii(name), "colour": [60, 60, 55]})
    # labels last so they draw on top of the fills
    return polys + labels


def _marker_layers(lon: float, lat: float, label: Optional[str] = None,
                   colour: Tuple[int, int, int] = (30, 30, 30), radius: int = 4,
                   dx: float = 0.18, dy: float = 0.10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = [{
        "type": "marker", "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "fill": list(colour), "stroke": [0, 0, 0], "radius": radius}]
    if label:
        out.append({"type": "label", "at": [lon + dx, lat + dy], "text": _ascii(label), "colour": [15, 15, 15]})
    return out


def _line_layer(coords: List[List[float]], colour: Tuple[int, int, int] = (200, 40, 40),
                width: int = 4) -> Dict[str, Any]:
    return {"type": "line", "geometry": {"type": "LineString", "coordinates": coords},
            "stroke": list(colour), "stroke_width": width}


def _control_layers(control: List[Dict[str, Any]], clip_country: Optional[str]) -> List[Dict[str, Any]]:
    """Translucent 'area of control' polygons, optionally clipped to a country's real
    coastline via shapely (falls back to the raw polygon if shapely is unavailable)."""
    out: List[Dict[str, Any]] = []
    clip_geom = None
    if clip_country and _HAVE_SHAPELY:
        cg = _country_geometry(clip_country)
        if cg:
            try:
                clip_geom = _sh_shape(cg).buffer(0)
            except Exception:
                clip_geom = None
    for c in control or []:
        coords = c.get("coords") or c.get("coordinates")
        if not coords:
            continue
        fill = list(c.get("fill") or [200, 55, 45, 85])
        stroke = list(c.get("stroke") or [180, 40, 30])
        width = int(c.get("stroke_width") or 1)
        geoms: List[Dict[str, Any]] = []
        if clip_geom is not None:
            try:
                clipped = _ShPolygon(coords).buffer(0).intersection(clip_geom)
                if clipped.is_empty:
                    geoms = [{"type": "Polygon", "coordinates": [coords]}]
                elif clipped.geom_type == "Polygon":
                    geoms = [_sh_mapping(clipped)]
                else:
                    geoms = [_sh_mapping(g) for g in getattr(clipped, "geoms", [])]
            except Exception:
                geoms = [{"type": "Polygon", "coordinates": [coords]}]
        else:
            geoms = [{"type": "Polygon", "coordinates": [coords]}]
        for gm in geoms:
            out.append({"type": "polygon", "geometry": gm, "fill": fill, "stroke": stroke, "stroke_width": width})
    return out


def _title_layer(text: str, bbox: List[float]) -> Dict[str, Any]:
    return {"type": "label", "at": [bbox[0] + 0.35, bbox[3] - 0.5], "text": _ascii(text), "colour": [20, 20, 40]}


def _legend_layer(items: List[Dict[str, Any]], height: int, x: int = 12) -> Dict[str, Any]:
    items = [{**it, "label": _ascii(it.get("label", ""))} for it in (items or [])]
    return {"type": "legend", "x": x, "y": int(height - 22 - 16 * len(items)), "items": items}


def _aspect_height(bbox: List[float], width: int) -> int:
    """Pixel height that preserves geographic aspect (lon range scaled by cos(midlat))."""
    midlat = (bbox[1] + bbox[3]) / 2.0
    lat_range = (bbox[3] - bbox[1]) or 1e-6
    asp = (bbox[2] - bbox[0]) * math.cos(math.radians(midlat)) / lat_range
    asp = asp or 1.0
    return max(1, int(width / asp))


# --------------------------------------------------------------------------- #
# Service-response envelope parsing (geo + chart)
# --------------------------------------------------------------------------- #
def _geo_image_b64(raw: Any) -> Optional[str]:
    """Pull ``data.image_base64`` from a geo_render_map result, tolerating the MCP
    content envelope (``result.content[0].text`` is a JSON string ``{ok,data:{...}}``),
    a ``structuredContent`` dict, or an already-parsed dict."""
    val: Any = raw
    for _ in range(4):
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return None
            continue
        if not isinstance(val, dict):
            return None
        data = val.get("data")
        if isinstance(data, dict) and data.get("image_base64"):
            return str(data["image_base64"])
        if val.get("image_base64"):
            return str(val["image_base64"])
        nxt = None
        if isinstance(val.get("structuredContent"), dict):
            nxt = val["structuredContent"]
        elif isinstance(val.get("result"), dict):
            nxt = val["result"]
        elif isinstance(val.get("content"), list):
            for blk in val["content"]:
                if isinstance(blk, dict) and "text" in blk:
                    try:
                        nxt = json.loads(blk["text"])
                        break
                    except Exception:
                        continue
        if nxt is None:
            return None
        val = nxt
    return None


def _chart_asset_id(raw: Any) -> Optional[str]:
    """Pull the first ``assets[0].asset_id`` from a chart ``render`` result, tolerating
    structuredContent-or-content envelopes and an ``assets`` list nested under ``data``."""
    val: Any = raw
    for _ in range(4):
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return None
            continue
        if not isinstance(val, dict):
            return None
        assets = val.get("assets")
        if not assets and isinstance(val.get("data"), dict):
            assets = val["data"].get("assets")
        if isinstance(assets, list) and assets and isinstance(assets[0], dict) and assets[0].get("asset_id"):
            return str(assets[0]["asset_id"])
        nxt = None
        if isinstance(val.get("structuredContent"), dict):
            nxt = val["structuredContent"]
        elif isinstance(val.get("result"), dict):
            nxt = val["result"]
        elif isinstance(val.get("content"), list):
            for blk in val["content"]:
                if isinstance(blk, dict) and "text" in blk:
                    try:
                        nxt = json.loads(blk["text"])
                        break
                    except Exception:
                        continue
        if nxt is None:
            return None
        val = nxt
    return None


def _chart_png_b64(asset_response: Any) -> Optional[str]:
    """Pull ``asset.base64_data`` (or ``base64_data``) from a REST asset GET response."""
    if isinstance(asset_response, str):
        try:
            asset_response = json.loads(asset_response)
        except Exception:
            return None
    if not isinstance(asset_response, dict):
        return None
    asset = asset_response.get("asset")
    if isinstance(asset, dict) and asset.get("base64_data"):
        return str(asset["base64_data"])
    if asset_response.get("base64_data"):
        return str(asset_response["base64_data"])
    return None


def _is_png_b64(b64: str) -> bool:
    """Cheap validation that a base64 string decodes to a PNG (magic bytes)."""
    try:
        return base64.b64decode(b64)[:4] == b"\x89PNG"
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Single-figure renderers
# --------------------------------------------------------------------------- #
async def _render_one_map(
    spec: Dict[str, Any],
    dispatch_service: Callable[..., Awaitable[Any]],
    geo_service: str,
    width: int = 1200,
    background: Tuple[int, int, int] = (208, 226, 240),
) -> Optional[str]:
    """Render one map from a spec entry; return its base64 PNG or None on any failure."""
    bbox = spec.get("bbox")
    if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
        logger.warning("visuals: map %r has no valid bbox; skipping", spec.get("id"))
        return None
    bbox = [float(x) for x in bbox]
    area = abs(bbox[2] - bbox[0]) * abs(bbox[3] - bbox[1])
    if area > _BBOX_AREA_CAP:
        # Pre-format the numbers to strings: the project logger redacts (stringifies) %-args,
        # which would break a %f/%d format specifier. Use %s with ready-made strings.
        logger.warning("visuals: map %r bbox area %s deg^2 exceeds cap %s; skipping",
                       spec.get("id"), "%.0f" % area, "%.0f" % _BBOX_AREA_CAP)
        return None

    layers: List[Dict[str, Any]] = []
    # Highlight set = the focus country/countries plus any explicit ``highlight`` names.
    focus = spec.get("focus_country")
    focus_list = list(focus) if isinstance(focus, (list, tuple)) else ([focus] if focus else [])
    highlight = [f for f in focus_list if f] + list(spec.get("highlight") or [])
    label_countries = spec.get("label_countries", True)
    # Preferred path: clip every country in the bbox (fixes the antimeridian USA drop) and
    # label them. Falls back to the explicit focus/neighbours backdrop without shapely.
    backdrop = _all_country_layers(bbox, highlight=highlight, label_countries=bool(label_countries))
    if backdrop is None:
        backdrop = _backdrop_layers(spec.get("focus_country"), spec.get("neighbours") or [])
    layers.extend(backdrop)
    layers.extend(_control_layers(spec.get("control") or [], spec.get("focus_country")))
    for ln in spec.get("lines") or []:
        coords = ln.get("coords") or ln.get("coordinates") or ln
        if isinstance(coords, list) and coords:
            layers.append(_line_layer(coords, tuple(ln.get("colour", (200, 40, 40))) if isinstance(ln, dict) else (200, 40, 40),
                                      int(ln.get("width", 4)) if isinstance(ln, dict) else 4))
    for mk in spec.get("markers") or []:
        try:
            layers.extend(_marker_layers(float(mk["lon"]), float(mk["lat"]), mk.get("label"),
                                         tuple(mk.get("colour", (30, 30, 30))), int(mk.get("radius", 4))))
        except (KeyError, TypeError, ValueError):
            continue
    if spec.get("title"):
        layers.append(_title_layer(str(spec["title"]), bbox))

    height = _aspect_height(bbox, width)
    legend_items = spec.get("legend") or []
    if legend_items:
        layers.append(_legend_layer(legend_items, height))

    args = {"width": width, "height": height, "bbox": bbox, "crs": "EPSG:4326",
            "background": list(background), "transfer_mode": "base64", "layers": layers}
    try:
        raw = await dispatch_service(geo_service, "geo_render_map", args)
    except Exception as exc:
        logger.warning("visuals: geo_render_map failed for %r: %s", spec.get("id"), exc)
        return None
    b64 = _geo_image_b64(raw)
    if not b64 or not _is_png_b64(b64):
        logger.warning("visuals: map %r returned no usable PNG", spec.get("id"))
        return None
    return b64


def _series_from_spec(spec: Dict[str, Any]) -> Tuple[List[str], "Dict[str, List[float]]"]:
    """Extract (categories, {series_name: values}) from a chart spec.

    Two shapes are accepted:
      * explicit multi-series — ``categories: [...]`` + ``series: {name: [v,...], ...}``;
      * tidy rows — ``rows: [{x: cat, <series-col>: name, y: val}]`` collapsed by series,
        or plain ``rows`` + ``x`` + ``y`` (single series keyed by the y column name).
    """
    cats = spec.get("categories")
    series = spec.get("series")
    if isinstance(cats, list) and isinstance(series, dict):
        return [str(c) for c in cats], {str(k): [float(v) for v in vals] for k, vals in series.items()}
    rows = spec.get("rows") or spec.get("data") or []
    x = spec.get("x")
    y = spec.get("y")
    scol = spec.get("series_col") or spec.get("group")
    if scol:  # tidy long form -> wide
        cats_ord: List[str] = []
        out: Dict[str, List[float]] = {}
        for r in rows:
            c = str(r.get(x))
            if c not in cats_ord:
                cats_ord.append(c)
        for r in rows:
            name = str(r.get(scol))
            out.setdefault(name, [0.0] * len(cats_ord))
            out[name][cats_ord.index(str(r.get(x)))] = float(r.get(y) or 0)
        return cats_ord, out
    cats_ord = [str(r.get(x)) for r in rows]
    vals = [float(r.get(y) or 0) for r in rows]
    return cats_ord, {str(y or "value"): vals}


def _render_chart_local(spec: Dict[str, Any]) -> Optional[str]:
    """Render a rich chart locally with matplotlib; return base64 PNG or None.

    Supported ``chart_type``: bar, grouped_bar, stacked_bar, hbar/horizontal_bar,
    donut/pie, line, multiline, area. Anything else (or matplotlib absent) returns
    None so the caller falls back to the chart MCP service.
    """
    if not _HAVE_MPL:
        return None
    ct = str(spec.get("chart_type") or "bar").lower()
    title = _ascii(spec.get("title") or "")
    ylabel = _ascii(spec.get("y_label") or spec.get("y") or "")
    xlabel = _ascii(spec.get("x_label") or "")
    try:
        rows = spec.get("rows") or spec.get("data") or []
        _plt.rcParams.update({
            "font.size": 11, "axes.edgecolor": "#888", "axes.linewidth": 0.8,
            "axes.titlesize": 14, "axes.titleweight": "bold", "axes.labelcolor": "#333",
            "text.color": "#222", "xtick.color": "#555", "ytick.color": "#555",
            "figure.facecolor": "white", "axes.facecolor": "#fbfbfb"})
        pal = _CHART_PALETTE

        if ct in ("donut", "pie"):
            labels = [_ascii(r.get(spec.get("x") or "label")) for r in rows]
            vals = [float(r.get(spec.get("y") or "value") or 0) for r in rows]
            if not vals:
                return None
            fig, ax = _plt.subplots(figsize=(6.2, 4.6))
            cols = [pal[i % len(pal)] for i in range(len(labels))]
            width = 0.42 if ct == "donut" else 1.0
            wedges, _t, _a = ax.pie(
                vals, labels=None, colors=cols, autopct=lambda p: ("%.0f%%" % p),
                pctdistance=0.78 if ct == "donut" else 0.6,
                wedgeprops=dict(width=width, edgecolor="white"),
                textprops=dict(color="white", fontsize=9, weight="bold"))
            ax.legend(wedges, labels, frameon=False, fontsize=9, loc="center left", bbox_to_anchor=(1.0, 0.5))
            ax.set_title(title)
            ax.axis("equal")

        elif ct in ("hbar", "horizontal_bar", "barh"):
            cats, series = _series_from_spec(spec)
            name, vals = next(iter(series.items()))
            order = sorted(range(len(vals)), key=lambda i: vals[i])
            cats = [_ascii(cats[i]) for i in order]
            vals = [vals[i] for i in order]
            fig, ax = _plt.subplots(figsize=(7.2, max(3.2, 0.5 * len(cats) + 1)))
            bars = ax.barh(cats, vals, color=pal[0], edgecolor="white", linewidth=0.6)
            for r in bars:
                ax.annotate("%g" % r.get_width(), (r.get_width(), r.get_y() + r.get_height() / 2),
                            ha="left", va="center", fontsize=9, color="#444",
                            xytext=(3, 0), textcoords="offset points")
            ax.set_xlabel(xlabel or ylabel)
            ax.set_title(title)
            ax.grid(axis="x", alpha=0.3)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)

        elif ct in ("grouped_bar", "grouped", "group_bar"):
            cats, series = _series_from_spec(spec)
            fig, ax = _plt.subplots(figsize=(7.2, 4.2))
            n = max(len(series), 1)
            w = 0.8 / n
            xs = range(len(cats))
            for i, (nm, vals) in enumerate(series.items()):
                off = [x + i * w - 0.4 + w / 2 for x in xs]
                bb = ax.bar(off, vals, w, label=_ascii(nm), color=pal[i % len(pal)], edgecolor="white", linewidth=0.6)
                for r in bb:
                    ax.annotate("%g" % r.get_height(), (r.get_x() + r.get_width() / 2, r.get_height()),
                                ha="center", va="bottom", fontsize=8, color="#444")
            ax.set_xticks(list(xs))
            ax.set_xticklabels([_ascii(c) for c in cats])
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.legend(frameon=False, fontsize=9, ncol=min(n, 4))
            ax.grid(axis="y", alpha=0.3)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)

        elif ct in ("stacked_bar", "stacked", "stack_bar"):
            cats, series = _series_from_spec(spec)
            fig, ax = _plt.subplots(figsize=(7.2, 4.2))
            bottom = [0.0] * len(cats)
            for i, (nm, vals) in enumerate(series.items()):
                ax.bar([_ascii(c) for c in cats], vals, bottom=bottom, label=_ascii(nm),
                       color=pal[i % len(pal)], edgecolor="white", linewidth=0.6)
                bottom = [b + v for b, v in zip(bottom, vals)]
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.legend(frameon=False, fontsize=9, ncol=2)
            ax.grid(axis="y", alpha=0.3)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)

        elif ct in ("multiline", "multi_line", "lines"):
            cats, series = _series_from_spec(spec)
            fig, ax = _plt.subplots(figsize=(7.2, 4.2))
            for i, (nm, vals) in enumerate(series.items()):
                ax.plot([_ascii(c) for c in cats], vals, marker="o", ms=5, lw=2,
                        color=pal[i % len(pal)], label=_ascii(nm))
            ax.set_ylabel(ylabel)
            ax.set_xlabel(xlabel)
            ax.set_title(title)
            ax.legend(frameon=False, fontsize=9, ncol=min(len(series), 4))
            ax.grid(alpha=0.3)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)

        elif ct in ("bar", "line", "area"):
            cats, series = _series_from_spec(spec)
            name, vals = next(iter(series.items()))
            cats = [_ascii(c) for c in cats]
            fig, ax = _plt.subplots(figsize=(7.2, 4.2))
            if ct == "bar":
                bars = ax.bar(cats, vals, color=pal[0], edgecolor="white", linewidth=0.6)
                for r in bars:
                    ax.annotate("%g" % r.get_height(), (r.get_x() + r.get_width() / 2, r.get_height()),
                                ha="center", va="bottom", fontsize=8, color="#444")
            elif ct == "area":
                ax.fill_between(range(len(cats)), vals, color=pal[0], alpha=0.25)
                ax.plot(range(len(cats)), vals, marker="o", ms=4, lw=2, color=pal[0])
                ax.set_xticks(range(len(cats)))
                ax.set_xticklabels(cats)
            else:  # line
                ax.plot(cats, vals, marker="o", ms=5, lw=2, color=pal[0])
            ax.set_ylabel(ylabel or _ascii(name))
            ax.set_xlabel(xlabel)
            ax.set_title(title)
            ax.tick_params(axis="x", rotation=20)
            ax.grid(axis="y", alpha=0.3)
            ax.set_axisbelow(True)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)
        else:
            return None

        import io as _io

        buf = _io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="white")
        _plt.close(fig)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return b64 if _is_png_b64(b64) else None
    except Exception as exc:
        logger.warning("visuals: local chart render failed for %r: %s", spec.get("id"), exc)
        try:
            _plt.close("all")
        except Exception:
            pass
        return None


# --------------------------------------------------------------------------- #
# Data-driven charts: real numbers pulled from the SQL agent (NL -> SQL)
# --------------------------------------------------------------------------- #
def _rows_from_list(items: List[Any]) -> List[List[Any]]:
    """Normalise a result list into list-of-lists. The SQL agent returns either a list of
    row dicts (``[{"col": v, ...}, ...]`` — column order = SELECT order, preserved by dict
    insertion order) or a list of positional rows; both collapse to ``[[v, ...], ...]``."""
    out: List[List[Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(list(it.values()))
        elif isinstance(it, (list, tuple)):
            out.append(list(it))
        else:
            out.append([it])
    return out


def _sql_rows(raw: Any) -> List[List[Any]]:
    """Extract result rows (list-of-lists) from a SQL-agent ``query_database*`` response.
    The agent returns either a top-level JSON array of row dicts/lists, or a body
    ``{"rows": [[...], ...]}`` — possibly with a trailing ``\\n---\\n_profile_audit: {...}``
    annotation — wrapped in the MCP content envelope. Returns ``[]`` for no-result /
    unparseable responses (the caller then skips that chart)."""
    val: Any = raw
    for _ in range(6):
        if isinstance(val, str):
            s = val.strip()
            for sep in ("\n---", "\n\n---"):
                if sep in s:
                    s = s.split(sep, 1)[0].strip()
            try:
                val = json.loads(s)
            except Exception:
                return []
            continue
        if isinstance(val, list):
            return _rows_from_list(val)
        if isinstance(val, dict):
            rows = val.get("rows")
            if isinstance(rows, list):
                return _rows_from_list(rows)
            if isinstance(val.get("data"), list):
                return _rows_from_list(val["data"])
            nxt: Any = None
            if isinstance(val.get("structuredContent"), (dict, list)):
                nxt = val["structuredContent"]
            elif isinstance(val.get("result"), (dict, list)):
                nxt = val["result"]
            elif isinstance(val.get("content"), list):
                for blk in val["content"]:
                    if isinstance(blk, dict) and "text" in blk:
                        nxt = blk["text"]
                        break
            if nxt is None:
                return []
            val = nxt
            continue
        return []
    return []


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _chart_spec_from_sql_rows(spec: Dict[str, Any], rows: List[List[Any]]) -> Optional[Dict[str, Any]]:
    """Map positional SQL rows into a local-chart spec (categories/series or rows+x/y).

    Column order is fixed by the question, so the spec describes how to read it:
      * multi-series (multiline/grouped_bar/stacked_bar): col 0 = category axis, cols 1..n
        = series named by ``series_names``;
      * ``row_dims``: a single result row rendered as a bar over named columns (``dims``);
      * otherwise (bar/hbar/line/area/donut/pie): col 0 = label, col 1 = value.
    """
    if not rows:
        return None
    ct = str(spec.get("chart_type") or "bar").lower()
    base = {k: spec.get(k) for k in ("id", "title", "after", "caption", "x_label", "y_label")
            if spec.get(k) is not None}
    base["chart_type"] = ct
    if ct in ("multiline", "multi_line", "grouped_bar", "grouped", "stacked_bar", "stacked", "lines"):
        names = spec.get("series_names") or []
        ncols = max((len(r) for r in rows), default=0)
        series: Dict[str, List[float]] = {}
        for i in range(1, ncols):
            nm = str(names[i - 1]) if (i - 1) < len(names) else ("series%d" % i)
            series[nm] = [_num(r[i]) if i < len(r) else 0.0 for r in rows]
        base["categories"] = [str(r[0]) for r in rows]
        base["series"] = series
        return base
    if ct == "row_dims":
        dims = spec.get("dims") or []
        r0 = rows[0]
        base["chart_type"] = "bar"
        base["rows"] = [{"dim": str(dims[i]) if i < len(dims) else ("col%d" % i), "val": _num(r0[i])}
                        for i in range(len(r0))]
        base["x"], base["y"] = "dim", "val"
        return base
    # default x/y mapping (label = col 0, value = col 1)
    base["rows"] = [{"label": str(r[0]), "value": _num(r[1]) if len(r) > 1 else 0.0} for r in rows]
    base["x"], base["y"] = "label", "value"
    return base


async def _render_chart_from_sql(
    spec: Dict[str, Any],
    dispatch_service: Callable[..., Awaitable[Any]],
    sql_service: str,
) -> Optional[str]:
    """Query the SQL agent for a chart's real data, then render it locally. Returns the
    base64 PNG or None (no rows / render failure) so the report still sends."""
    question = spec.get("sql")
    if not question:
        return None
    args: Dict[str, Any] = {"question": str(question),
                            "agent_strategy": str(spec.get("sql_strategy") or "simple")}
    if spec.get("sql_profile"):
        args["profile"] = str(spec["sql_profile"])
    try:
        raw = await dispatch_service(sql_service, "query_database_async_blocking", args)
    except Exception as exc:
        logger.warning("visuals: sql chart %r query failed: %s", spec.get("id"), exc)
        return None
    rows = _sql_rows(raw)
    if not rows:
        logger.warning("visuals: sql chart %r returned no rows; skipping", spec.get("id"))
        return None
    cspec = _chart_spec_from_sql_rows(spec, rows)
    if not cspec:
        return None
    return _render_chart_local(cspec)


async def _render_one_chart(
    spec: Dict[str, Any],
    dispatch_service: Callable[..., Awaitable[Any]],
    http_get: Optional[Callable[[str], Awaitable[Any]]],
    chart_service: str,
) -> Optional[str]:
    """Render one chart from a spec entry; return its base64 PNG or None on any failure."""
    rows = spec.get("rows") or spec.get("data") or []
    if not rows:
        logger.warning("visuals: chart %r has no rows; skipping", spec.get("id"))
        return None
    chart_spec = {
        "chart_type": str(spec.get("chart_type") or "bar"),
        "x": spec.get("x"),
        "y": spec.get("y"),
        "title": _ascii(spec.get("title") or ""),
        "renderer": str(spec.get("renderer") or "matplotlib"),
        "output_formats": ["png"],
        "width": int(spec.get("width") or 820),
        "height": int(spec.get("height") or 470),
    }
    try:
        raw = await dispatch_service(chart_service, "render", {"data": {"rows": rows}, "spec": chart_spec})
    except Exception as exc:
        logger.warning("visuals: chart render failed for %r: %s", spec.get("id"), exc)
        return None
    asset_id = _chart_asset_id(raw)
    if not asset_id:
        logger.warning("visuals: chart %r returned no asset_id", spec.get("id"))
        return None
    if http_get is None:
        logger.warning("visuals: no http_get helper available to fetch chart asset %s", asset_id)
        return None
    try:
        asset_resp = await http_get(f"/api/assets/{asset_id}")
    except Exception as exc:
        logger.warning("visuals: chart asset GET failed for %s: %s", asset_id, exc)
        return None
    b64 = _chart_png_b64(asset_resp)
    if not b64 or not _is_png_b64(b64):
        logger.warning("visuals: chart %r asset %s had no usable PNG", spec.get("id"), asset_id)
        return None
    return b64


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
async def render_visuals(
    visuals_spec: Dict[str, Any],
    dispatch_service: Callable[..., Awaitable[Any]],
    http_get: Optional[Callable[[str], Awaitable[Any]]] = None,
    geo_service: str = "geospatialmcpserver0",
    chart_service: str = "chartmcpserver0",
    sql_service: str = "sqlagent0",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Render the maps and charts in ``visuals_spec`` into inline CID images.

    ``visuals_spec`` shape (all data-driven by the schedule)::

        {
          "maps": [{
            "id": "theatre", "title": "...", "after": "<heading substring>",
            "focus_country": "Ukraine",            # str OR list; highlighted on the map
            "highlight": ["Russia", ...],           # extra countries to highlight (optional)
            "label_countries": true,                # draw country-name labels (default true)
            "bbox": [minx, miny, maxx, maxy],
            "markers": [{"lon":..,"lat":..,"label":"Kyiv","colour":[r,g,b],"radius":4}],
            "lines": [{"coords": [[lon,lat],...], "colour":[r,g,b], "width":4}],
            "control": [{"coords": [[lon,lat],...], "fill":[r,g,b,a], "stroke":[r,g,b]}],
            "legend": [{"colour":[r,g,b], "label":"..."}],
            "caption": "Figure 1 - ..."
          }],
          "charts": [{
            "id": "aid", "title": "...", "after": "<heading substring>",
            # rich local types: bar|line|area|hbar|donut|pie|grouped_bar|stacked_bar|multiline
            # (rendered with matplotlib when present); else falls back to the chart MCP
            # service for bar|line|area|scatter|table via renderer matplotlib|vega_lite|great_tables.
            "chart_type": "grouped_bar",
            "x": "month", "y": "value", "rows": [{"month":"Jan","value":12}, ...],
            # multi-series (grouped/stacked/multiline) — either explicit:
            "categories": ["Q1","Q2"], "series": {"OFAC":[42,55], "EU":[28,31]},
            # ...or tidy rows + a "series_col" naming the grouping column.
            "caption": "Chart - ..."
          }]
        }

    Returns ``(inline_images, figures)``:
      * ``inline_images = [{content_id, content_type:"image/png", data:<base64>, filename}]``
      * ``figures = [{content_id, caption, after_heading}]`` (placement records).

    Each map/chart that fails to render is skipped (logged) so the report still sends.
    """
    inline_images: List[Dict[str, Any]] = []
    figures: List[Dict[str, Any]] = []
    if not isinstance(visuals_spec, dict):
        return inline_images, figures

    seq = 0

    def _cid(spec: Dict[str, Any], prefix: str) -> str:
        nonlocal seq
        seq += 1
        cid = str(spec.get("id") or f"{prefix}{seq}").strip()
        # CID must be a simple token usable in src="cid:..."; fold to a safe slug.
        return "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in _ascii(cid)) or f"{prefix}{seq}"

    def _emit(spec: Dict[str, Any], prefix: str, b64: str) -> None:
        cid = _cid(spec, prefix)
        inline_images.append({"content_id": cid, "content_type": "image/png",
                              "data": b64, "filename": cid + ".png"})
        figures.append({"content_id": cid,
                        "caption": _ascii(spec.get("caption") or spec.get("title") or ""),
                        "after_heading": spec.get("after")})

    for m in visuals_spec.get("maps") or []:
        if not isinstance(m, dict):
            continue
        b64 = await _render_one_map(m, dispatch_service, geo_service)
        if b64:
            _emit(m, "map", b64)

    charts = [c for c in (visuals_spec.get("charts") or []) if isinstance(c, dict)]
    # Data-driven charts (spec has ``sql``) pull real numbers from the SQL agent — each
    # query is a slow NL->SQL job, so fire them concurrently rather than serially.
    sql_idx = [i for i, c in enumerate(charts) if c.get("sql")]
    sql_b64: Dict[int, Optional[str]] = {}
    if sql_idx:
        import asyncio as _asyncio

        results = await _asyncio.gather(
            *[_render_chart_from_sql(charts[i], dispatch_service, sql_service) for i in sql_idx],
            return_exceptions=True)
        for i, res in zip(sql_idx, results):
            sql_b64[i] = res if isinstance(res, str) else None
    for i, c in enumerate(charts):
        if i in sql_b64:
            b64 = sql_b64[i]
        else:
            # Prefer the rich local matplotlib renderer (grouped/stacked/horizontal/donut/
            # multi-series). Fall back to the chart MCP service when matplotlib is absent or
            # the chart type is not one the local renderer handles.
            b64 = _render_chart_local(c)
            if not b64:
                b64 = await _render_one_chart(c, dispatch_service, http_get, chart_service)
        if b64:
            _emit(c, "chart", b64)

    return inline_images, figures


# --------------------------------------------------------------------------- #
# HTML injection helpers (used by the document strategy)
# --------------------------------------------------------------------------- #
def figure_html(content_id: str, caption: str) -> str:
    """A self-contained, inline-styled <figure> referencing the CID image (Gmail-safe)."""
    import html as _html

    cap = _html.escape(caption or "")
    return ('<figure style="margin:18px 0;text-align:center">'
            '<img src="cid:%s" alt="%s" style="max-width:100%%;border:1px solid #ccd;border-radius:4px">'
            '<figcaption style="font:13px Arial,Helvetica,sans-serif;color:#556;margin-top:5px">%s</figcaption>'
            '</figure>') % (content_id, cap, cap)


def inject_figures(html: str, figures: List[Dict[str, Any]]) -> str:
    """Insert each figure's <img> block after its ``after_heading`` <h2>/<h3> in ``html``.

    Figures without a matching heading (or no ``after_heading``) are prepended to the body
    so they are never silently dropped. ``html`` is the already-rendered email HTML.
    """
    import re as _re

    for fig in figures or []:
        cid = fig.get("content_id")
        if not cid:
            continue
        block = figure_html(cid, str(fig.get("caption") or ""))
        after = fig.get("after_heading")
        placed = False
        if after:
            pat = r"(<h[1-4][^>]*>[^<]*" + _re.escape(str(after)) + r"[^<]*</h[1-4]>)"
            m = _re.search(pat, html, _re.IGNORECASE)
            if m:
                html = html[:m.end()] + block + html[m.end():]
                placed = True
        if not placed:
            # prepend just inside <body> if present, else at the very start.
            bm = _re.search(r"<body[^>]*>", html, _re.IGNORECASE)
            if bm:
                html = html[:bm.end()] + block + html[bm.end():]
            else:
                html = block + html
    return html


def inject_before_sources(html: str, block: str) -> str:
    """Insert ``block`` immediately before the rendered '## Sources' heading, or append it
    to the document body (just before </body>) when there is no Sources section."""
    import re as _re

    m = _re.search(r"<h[1-4][^>]*>\s*Sources\s*</h[1-4]>", html, _re.IGNORECASE)
    if m:
        return html[:m.start()] + block + html[m.start():]
    bm = _re.search(r"</body>", html, _re.IGNORECASE)
    if bm:
        return html[:bm.start()] + block + html[bm.start():]
    return html + block


def previous_reports_html(previous_reports: List[Dict[str, Any]], heading: str = "Further Detail & Previous Reports") -> str:
    """Render a 'Further Detail & Previous Reports' section (a list of links).

    ``previous_reports`` items are ``{"title": ..., "url": ..., "note": ...(optional)}``.
    Returns "" when there is nothing to render.
    """
    import html as _html

    items = [r for r in (previous_reports or []) if isinstance(r, dict) and r.get("url")]
    if not items:
        return ""
    lis = []
    for r in items:
        title = _html.escape(str(r.get("title") or r.get("url")))
        url = _html.escape(str(r.get("url")), quote=True)
        note = r.get("note")
        suffix = (" — " + _html.escape(str(note))) if note else ""
        lis.append('<li><a href="%s" style="color:#15569c">%s</a>%s</li>' % (url, title, suffix))
    return ('<h2 style="font-family:Arial,Helvetica,sans-serif;color:#1a2330;'
            'border-bottom:1px solid #e3e7ee;padding-bottom:3px;margin:1.6em 0 .5em">%s</h2>'
            '<ul style="font:14px/1.5 Arial,Helvetica,sans-serif">%s</ul>') % (_html.escape(heading), "".join(lis))
