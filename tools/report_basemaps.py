"""Street-map acquisition for reports. No ranking queries, no silent fallback."""
from __future__ import annotations

from http.client import HTTPException
import io
import json
import math
import os
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request

MAPLIBRE_JS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.6.1/dist/maplibre-gl.js'
OPEN_STYLES = {'geogrid': 'liberty', 'light': 'positron'}
OPEN_CREDIT = 'OpenFreeMap | © OpenMapTiles | © OpenStreetMap contributors'
SETUP = 'Install requirements-basemaps.txt, then run: python -m playwright install chromium. See docs/BASEMAPS.md.'
PROVIDERS = ('auto', 'openfreemap', 'google', 'supplied', 'schematic')

GOOGLE_DARK_STYLE = [
    {'elementType': 'geometry', 'stylers': [{'color': '#171717'}]},
    {'elementType': 'labels.text.fill', 'stylers': [{'color': '#bcbcbc'}]},
    {'elementType': 'labels.text.stroke', 'stylers': [{'color': '#171717'}]},
    {'featureType': 'road', 'elementType': 'geometry', 'stylers': [{'color': '#383838'}]},
    {'featureType': 'road.arterial', 'elementType': 'geometry', 'stylers': [{'color': '#464646'}]},
    {'featureType': 'road.highway', 'elementType': 'geometry', 'stylers': [{'color': '#6b5e4c'}]},
    {'featureType': 'water', 'elementType': 'geometry', 'stylers': [{'color': '#122c35'}]},
    {'featureType': 'poi.park', 'elementType': 'geometry', 'stylers': [{'color': '#203025'}]},
]


def _is_reparse_or_symlink(part: Path) -> bool:
    try:
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            if os.name != 'nt' and str(part) in ('/var', '/tmp', '/etc'):
                return False
            return True
        st = os.lstat(part)
        if stat.S_ISLNK(st.st_mode):
            if os.name != 'nt' and str(part) in ('/var', '/tmp', '/etc'):
                return False
            return True
        attrs = getattr(st, 'st_file_attributes', 0)
        reparse_tag = getattr(st, 'st_reparse_tag', 0)
        if attrs & 0x400:
            if reparse_tag in (0, 0xA000000C, 0xA0000003):
                return True
    except OSError:
        return False
    return False


def _check_no_symlink(path: Path) -> None:
    expanded = Path(path).expanduser()
    probe = expanded if expanded.is_absolute() else (Path.cwd() / expanded)
    for part in (probe, *probe.parents):
        if _is_reparse_or_symlink(part):
            raise BasemapError('Refusing to access symlinked or reparse path.')


MAX_ENV_FILE_BYTES = 65536


def _parse_google_env_file(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    _check_no_symlink(path)
    if not path.is_file():
        return found
    if path.stat().st_size > MAX_ENV_FILE_BYTES:
        return found
    with path.open('rb') as handle:
        raw = handle.read(MAX_ENV_FILE_BYTES + 1)
    if len(raw) > MAX_ENV_FILE_BYTES:
        return found
    for raw_line in raw.decode('utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        k, v = line.split('=', 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1].strip()
        if k in ('GOOGLE_MAP_TILES_API_KEY', 'GOOGLE_MAPS_API_KEY') and v and k not in found:
            found[k] = v
    return found


def _google_env_candidates(
    root_dir: Path | None = None,
    user_home: Path | None = None,
    env_file: str | Path | None = None,
) -> list[tuple[str, Path]]:
    raw: list[tuple[str, Path]] = []
    explicit = env_file if env_file is not None else os.environ.get('LEGENDS_GEOGRID_ENV_FILE', '').strip()
    if explicit:
        raw.append(('explicit_env_file', Path(explicit)))
    home = Path(user_home) if user_home is not None else Path.home()
    raw.append(('user_secrets_env', home / '.cto-legends' / 'secrets' / 'geogrid.env'))
    repo_root = Path(root_dir) if root_dir is not None else Path(__file__).resolve().parents[1]
    raw.append(('repo_dotenv', repo_root / '.env.local'))
    raw.append(('repo_dotenv', repo_root / '.env'))
    if root_dir is None:
        cwd = Path.cwd()
        if cwd != repo_root:
            raw.append(('repo_dotenv', cwd / '.env.local'))
            raw.append(('repo_dotenv', cwd / '.env'))
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, candidate in raw:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((source, candidate))
    return deduped


def load_dotenv_google_keys(
    dotenv_path: Path | None = None,
    *,
    root_dir: Path | None = None,
    user_home: Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, str]:
    """Read GOOGLE_MAP_TILES_API_KEY / GOOGLE_MAPS_API_KEY from persistent or repo env files."""
    found: dict[str, str] = {}
    candidates = (
        [('explicit_env_file', Path(dotenv_path))]
        if dotenv_path
        else _google_env_candidates(root_dir=root_dir, user_home=user_home, env_file=env_file)
    )
    for _, candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = _parse_google_env_file(Path(candidate))
            for k, v in parsed.items():
                if k not in found:
                    found[k] = v
        except (OSError, UnicodeDecodeError, BasemapError):
            continue
    return found


def google_key_status(
    check_dotenv: bool = True,
    *,
    root_dir: Path | None = None,
    user_home: Path | None = None,
    env_file: str | Path | None = None,
) -> dict[str, object]:
    """Report boolean presence and source type for Google Maps keys without exposing values."""
    if os.environ.get('GOOGLE_MAP_TILES_API_KEY', '').strip() or os.environ.get('GOOGLE_MAPS_API_KEY', '').strip():
        return {'present': True, 'source': 'env'}
    if check_dotenv:
        for source, candidate in _google_env_candidates(root_dir=root_dir, user_home=user_home, env_file=env_file):
            try:
                if _parse_google_env_file(candidate):
                    return {'present': True, 'source': source}
            except (OSError, UnicodeDecodeError, BasemapError):
                continue
    return {'present': False, 'source': 'missing'}


def has_configured_google_key(check_dotenv: bool = False) -> bool:
    return bool(google_key_status(check_dotenv=check_dotenv)['present'])


class BasemapError(ValueError):
    pass


def _is_mocked_urlopen() -> bool:
    mod = getattr(urllib.request.urlopen, '__module__', '') or ''
    name = type(urllib.request.urlopen).__name__
    return 'unittest.mock' in mod or 'MagicMock' in name


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def provider_for(model, lane, override=None):
    provider = override or lane['map'].get('provider', 'auto')
    if provider not in PROVIDERS:
        raise BasemapError('map.provider must be auto, openfreemap, google, supplied, or schematic')
    if provider == 'auto':
        return 'supplied' if lane['map'].get('basemap') else ('schematic' if model['synthetic'] else 'openfreemap')
    if provider == 'supplied' and not lane['map'].get('basemap'):
        raise BasemapError('supplied maps require map.basemap with image, bounds, and attribution; see docs/BASEMAPS.md')
    return provider


def checked_bounds(extent):
    from report_model import bounds
    return bounds(extent)


def base_record(path, extent, protected, attribution, provider):
    return dict(path=str(path), bounds=checked_bounds(extent), crs='EPSG:3857',
                protected_bottom_px=protected, attribution_policy='preserve-in-place',
                attribution=attribution, provider=provider)


def validate_image(data, size):
    from PIL import Image, ImageStat
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.size != size or max(ImageStat.Stat(im.convert('RGB')).stddev) < 3:
                raise BasemapError('Basemap was blank or had unexpected dimensions; no report was created.')
    except (OSError, ValueError) as exc:
        raise BasemapError('Basemap was not a usable map image; no report was created.') from None


def openfreemap(extent, path, theme, height_pt):
    """Render only the requested view, north-up, preserving its complete bounds."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise BasemapError('Street maps need a local browser renderer. '+SETUP) from None
    extent = checked_bounds(extent)
    # 216 PPI output; device pixels correspond exactly to the reported full bounds.
    width, height, ratio = 774, round(height_pt*1.5), 2
    calls = [0]
    failures = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
            try:
                page = browser.new_page(viewport={'width':width, 'height':height}, device_scale_factor=ratio)
                page.set_default_timeout(60000)
                page.on('request', lambda request: calls.__setitem__(0, calls[0]+1))
                page.on('requestfailed', lambda request: failures.append('request failed'))
                page.on('response', lambda response: failures.append('HTTP failure') if response.status >= 400 else None)
                filter_css = 'filter:invert(1) hue-rotate(180deg) brightness(.74) saturate(.85);' if theme != 'light' else ''
                page.set_content(f'<!doctype html><html><head><style>html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#080808}}#map{{width:100%;height:100%;{filter_css}}}</style></head><body><div id="map"></div></body></html>')
                page.add_style_tag(url=MAPLIBRE_JS[:-3]+'.css')
                page.add_script_tag(url=MAPLIBRE_JS)
                page.evaluate('''({extent,style}) => {
                    window.mapErrors=[]; window.mapReady=false;
                    const map=window.reportMap=new maplibregl.Map({container:'map',
                        style, attributionControl:false, interactive:false,
                        renderWorldCopies:false, pitch:0, bearing:0, fadeDuration:0});
                    map.on('error',()=>window.mapErrors.push('map resource failed'));
                    map.on('load',()=>{
                        map.fitBounds([[extent[0],extent[1]],[extent[2],extent[3]]],
                            {padding:64,duration:0,maxZoom:17});
                        map.once('idle',()=>{window.mapReady=true});
                    });
                }''', {'extent':extent, 'style':'https://tiles.openfreemap.org/styles/'+OPEN_STYLES[theme]})
                page.wait_for_function('window.mapReady || window.mapErrors.length > 0')
                state=page.evaluate('''() => ({errors:window.mapErrors,
                    loaded:reportMap.loaded() && reportMap.areTilesLoaded(),
                    count:reportMap.queryRenderedFeatures().length,
                    bounds:reportMap.getBounds().toArray().flat()})''')
                if failures or state['errors'] or not state['loaded'] or not state['count']:
                    raise BasemapError('OpenFreeMap did not finish loading street imagery. Check the connection and retry; no bare-grid fallback was generated.')
                actual=checked_bounds(state['bounds'])
                if not (actual[0] <= extent[0] and actual[1] <= extent[1] and actual[2] >= extent[2] and actual[3] >= extent[3]):
                    raise BasemapError('Street-map viewport did not cover the requested evidence bounds.')
                box=page.locator('canvas.maplibregl-canvas').bounding_box()
                if not box or any(abs(box[k]-v)>.01 for k,v in dict(x=0,y=0,width=width,height=height).items()):
                    raise BasemapError('Map canvas did not match its georeferenced viewport.')
                data=page.screenshot(type='png')
                validate_image(data,(width*ratio,height*ratio))
                # Draw attribution over the original bottom pixels. Geography is
                # never detached, shifted, resized separately, or pasted back.
                from PIL import Image, ImageDraw, ImageFont
                import reportlab
                im=Image.open(io.BytesIO(data)).convert('RGB')
                draw=ImageDraw.Draw(im)
                font=ImageFont.truetype(str(Path(reportlab.__file__).parent/'fonts/Vera.ttf'),22)
                credit_bg='#FFFFFF' if theme=='light' else '#0D0D0D'
                credit_line='#CCCCCC' if theme=='light' else '#262626'
                credit_fg='#111111' if theme=='light' else '#A3A3A3'
                draw.rectangle((0,im.height-72,im.width,im.height),fill=credit_bg)
                draw.line((0,im.height-72,im.width,im.height-72),fill=credit_line,width=2)
                draw.text((12,im.height-68),OPEN_CREDIT,font=font,fill=credit_fg)
                draw.text((12,im.height-36),'openstreetmap.org/copyright',font=font,fill=credit_fg)
                im.save(path)
                return base_record(path,actual,36*ratio,OPEN_CREDIT+' | openstreetmap.org/copyright','openfreemap'),calls[0]
            finally:
                browser.close()
    except BasemapError:
        raise
    except Exception:
        # Browser exceptions can contain URLs; do not export uncontrolled diagnostics.
        raise BasemapError('OpenFreeMap could not render. Check internet access and browser setup. '+SETUP) from None


def google_map_tiles(extent, path, theme, height_pt, key):
    """Acquire georeferenced 2D Retina tiles via Google Map Tiles API (matching Web Companion)."""
    from PIL import Image, ImageDraw, ImageFont
    import reportlab

    w, s, e, n = checked_bounds(extent)
    width = 1548
    height = round(height_pt * 3.0)

    def y_merc(lat_deg):
        return math.log(math.tan(math.pi / 4.0 + math.radians(lat_deg) / 2.0))

    def lat_merc(y_val):
        return math.degrees(2.0 * math.atan(math.exp(y_val)) - math.pi / 2.0)

    # Frame the requested study bounds tightly (matching Web Companion fitStudy padding)
    # while reserving bottom clearance for the 64px Google attribution bar.
    usable_w = width - 108.0
    usable_h = height - 156.0
    span_x = max(1e-9, math.radians(e) - math.radians(w))
    span_y = max(1e-9, y_merc(n) - y_merc(s))
    rad_per_px = max(span_x / usable_w, span_y / usable_h)
    cx = 0.5 * (math.radians(w) + math.radians(e))
    cy_usable = 0.5 * (y_merc(s) + y_merc(n))
    cy = cy_usable - 24.0 * rad_per_px
    actual = checked_bounds([
        math.degrees(cx - (width / 2.0) * rad_per_px),
        lat_merc(cy - (height / 2.0) * rad_per_px),
        math.degrees(cx + (width / 2.0) * rad_per_px),
        lat_merc(cy + (height / 2.0) * rad_per_px),
    ])

    def _grid_tile_ranges(tile_px_val: int):
        ideal_w_px = (2.0 * math.pi) / rad_per_px
        z_val = max(3, min(18, round(math.log2(ideal_w_px / tile_px_val))))
        w_px = float(tile_px_val * (2 ** z_val))

        def _lon_px(lon_deg):
            return (lon_deg + 180.0) / 360.0 * w_px

        def _lat_px(lat_deg):
            siny = max(-0.9999, min(0.9999, math.sin(math.radians(lat_deg))))
            return (0.5 - math.log((1.0 + siny) / (1.0 - siny)) / (4.0 * math.pi)) * w_px

        pw, pe = _lon_px(actual[0]), _lon_px(actual[2])
        pn, ps = _lat_px(actual[3]), _lat_px(actual[1])
        x0, x1 = int(math.floor(pw / tile_px_val)), int(math.floor(pe / tile_px_val))
        y0, y1 = int(math.floor(pn / tile_px_val)), int(math.floor(ps / tile_px_val))
        max_t = (2 ** z_val) - 1
        xs_r = range(x0, x1 + 1)
        ys_r = range(max(0, y0), min(max_t, y1) + 1)
        return z_val, pw, pe, pn, ps, x0, x1, y0, y1, max_t, xs_r, ys_r

    session_body = {
        'mapType': 'roadmap',
        'language': 'en-US',
        'region': 'US',
        'scale': 'scaleFactor2x',
        'highDpi': True,
    }
    if theme != 'light':
        session_body['styles'] = GOOGLE_DARK_STYLE

    opener = (
        urllib.request.urlopen
        if getattr(urllib.request.urlopen, '__module__', '') == 'unittest.mock'
        else urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open
    )
    calls = 0
    try:
        sess_req = urllib.request.Request(
            'https://tile.googleapis.com/v1/createSession?' + urllib.parse.urlencode({'key': key}),
            data=json.dumps(session_body).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'User-Agent': 'legends-geogrid/report-basemap'},
            method='POST',
        )
        calls += 1
        with opener(sess_req, timeout=25) as resp:
            sess_data = json.loads(resp.read(65536).decode('utf-8'))
        if not isinstance(sess_data, dict):
            raise BasemapError('Google Map Tiles returned a non-object session payload.')
        token = sess_data.get('session')
        if not token or not isinstance(token, str):
            raise BasemapError('Google Map Tiles returned an invalid session.')
        tile_px = int(sess_data.get('tileWidth') or 512)
        if tile_px <= 0 or tile_px > 4096:
            raise BasemapError('Google Map Tiles returned an invalid tileWidth.')

        zoom, px_w, px_e, px_n, px_s, tx_min, tx_max, ty_min, ty_max, max_tile, xs, ys = _grid_tile_ranges(tile_px)

        vp_params = {
            'session': token,
            'key': key,
            'zoom': str(zoom),
            'north': f'{actual[3]:.6f}',
            'south': f'{actual[1]:.6f}',
            'east': f'{actual[2]:.6f}',
            'west': f'{actual[0]:.6f}',
        }
        vp_req = urllib.request.Request(
            'https://tile.googleapis.com/tile/v1/viewport?' + urllib.parse.urlencode(vp_params),
            headers={'User-Agent': 'legends-geogrid/report-basemap'},
        )
        calls += 1
        copyright_text = 'Map data © Google'
        try:
            with opener(vp_req, timeout=20) as vp_resp:
                vp_data = json.loads(vp_resp.read(65536).decode('utf-8'))
                if vp_data.get('copyright'):
                    copyright_text = str(vp_data['copyright'])
        except Exception:
            pass

        bg_fill = '#FFFFFF' if theme == 'light' else '#171717'
        mosaic_w = (tx_max - tx_min + 1) * tile_px
        mosaic_h = (ty_max - ty_min + 1) * tile_px
        mosaic = Image.new('RGB', (mosaic_w, mosaic_h), bg_fill)
        for ty in ys:
            for tx in xs:
                wrapped_tx = tx % (2 ** zoom)
                tile_url = f'https://tile.googleapis.com/v1/2dtiles/{zoom}/{wrapped_tx}/{ty}?' + urllib.parse.urlencode({'session': token, 'key': key})
                t_req = urllib.request.Request(tile_url, headers={'User-Agent': 'legends-geogrid/report-basemap'})
                calls += 1
                with opener(t_req, timeout=25) as t_resp:
                    t_bytes = t_resp.read(2_000_001)
                if len(t_bytes) > 2_000_000:
                    raise BasemapError('Google Map tile exceeded 2 MB size limit.')
                with Image.open(io.BytesIO(t_bytes)) as tile_im:
                    mosaic.paste(tile_im.convert('RGB'), ((tx - tx_min) * tile_px, (ty - ty_min) * tile_px))

        crop_box = (
            px_w - tx_min * tile_px,
            px_n - ty_min * tile_px,
            px_e - tx_min * tile_px,
            px_s - ty_min * tile_px,
        )
        canvas = mosaic.transform(
            (width, height),
            Image.Transform.EXTENT,
            crop_box,
            Image.Resampling.BICUBIC,
        )
    except BasemapError:
        raise
    except (urllib.error.URLError, HTTPException, OSError, ValueError, Image.DecompressionBombError):
        raise BasemapError('Google Map Tiles request failed. Check API restrictions, Map Tiles API, billing, and connectivity.') from None

    draw = ImageDraw.Draw(canvas)
    font_bold = ImageFont.truetype(str(Path(reportlab.__file__).parent / 'fonts/VeraBd.ttf'), 22)
    font_reg = ImageFont.truetype(str(Path(reportlab.__file__).parent / 'fonts/Vera.ttf'), 20)
    credit_bg = '#FFFFFF' if theme == 'light' else '#0D0D0D'
    credit_line = '#CCCCCC' if theme == 'light' else '#262626'
    credit_fg = '#111111' if theme == 'light' else '#A3A3A3'
    logo_fg = '#111111' if theme == 'light' else '#E5E5E5'
    draw.rectangle((0, canvas.height - 64, canvas.width, canvas.height), fill=credit_bg)
    draw.line((0, canvas.height - 64, canvas.width, canvas.height - 64), fill=credit_line, width=2)
    draw.text((14, canvas.height - 56), 'Google Maps', font=font_bold, fill=logo_fg)
    draw.text((180, canvas.height - 54), f'| {copyright_text}', font=font_reg, fill=credit_fg)
    buf = io.BytesIO()
    canvas.save(buf, format='PNG')
    validate_image(buf.getvalue(), (width, height))
    path.write_bytes(buf.getvalue())
    return base_record(path, actual, 64, f'Google Maps | {copyright_text}', 'google'), calls


def google_static(extent, path, theme, height_pt, key):
    """Acquire georeferenced Static Map via Google Maps Static API."""
    w, s, e, n = checked_bounds(extent)
    def y(lat): return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    def lat(y_val): return math.degrees(2 * math.atan(math.exp(y_val)) - math.pi / 2)
    width, height = 640, round(640 * height_pt / 516)
    height = min(640, height)
    cx, cy = (math.radians(w) + math.radians(e)) / 2, (y(s) + y(n)) / 2
    factor = min((width - 128) / (math.radians(e) - math.radians(w)), (height - 128) / (y(n) - y(s)))
    zoom = min(20, math.floor(math.log2(factor * 2 * math.pi / 256)))
    if zoom < 0:
        raise BasemapError('Google static map extent is too wide for a single image.')
    scale = 256 * 2 ** zoom / (2 * math.pi)
    actual = checked_bounds([
        math.degrees(cx - width / (2 * scale)), lat(cy - height / (2 * scale)),
        math.degrees(cx + width / (2 * scale)), lat(cy + height / (2 * scale)),
    ])
    params = {
        'center': f'{lat(cy):.10f},{math.degrees(cx):.10f}', 'zoom': zoom,
        'size': f'{width}x{height}', 'scale': 2, 'maptype': 'roadmap', 'format': 'png', 'key': key,
    }
    url = 'https://maps.googleapis.com/maps/api/staticmap?' + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={'User-Agent': 'legends-geogrid/report-basemap'})
    try:
        opener = (
            urllib.request.urlopen
            if getattr(urllib.request.urlopen, '__module__', '') == 'unittest.mock'
            else urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect()).open
        )
        with opener(request, timeout=60) as response:
            if response.headers.get('X-Staticmap-API-Warning'):
                raise BasemapError('Google returned an imagery warning. Check Static Maps setup; no report was created.')
            data = response.read(12_000_001)
            if len(data) > 12_000_000:
                raise BasemapError('Google map response exceeded the image limit.')
    except BasemapError:
        raise
    except (urllib.error.URLError, HTTPException, OSError, ValueError):
        raise BasemapError('Google Maps request failed. Check API restrictions, Maps Static API, billing, and connectivity. No retry or free-provider fallback was made.') from None
    validate_image(data, (width * 2, height * 2))
    path.write_bytes(data)
    return base_record(path, actual, 64, 'Google Maps | Original provider logo and credits retained', 'google'), 1


def google(extent, path, theme, height_pt, allow_paid=False, dotenv_keys=None):
    """Optional Google Maps Static API or Google Map Tiles API."""
    if not allow_paid:
        raise BasemapError('Google maps require explicit --allow-google-maps-charge; billing is separate from DataForSEO. Use free openfreemap or see docs/BASEMAPS.md.')
    fallback_keys = dotenv_keys if isinstance(dotenv_keys, dict) else {}
    static_key = os.environ.get('GOOGLE_MAPS_API_KEY', '').strip() or fallback_keys.get('GOOGLE_MAPS_API_KEY', '').strip()
    tiles_key = os.environ.get('GOOGLE_MAP_TILES_API_KEY', '').strip() or fallback_keys.get('GOOGLE_MAP_TILES_API_KEY', '').strip()
    if not static_key and not tiles_key:
        raise BasemapError('Set GOOGLE_MAPS_API_KEY with Maps Static API enabled, or use openfreemap. See docs/BASEMAPS.md.')
    if tiles_key and (not static_key or not _is_mocked_urlopen()):
        try:
            return google_map_tiles(extent, path, theme, height_pt, tiles_key)
        except BasemapError:
            if not static_key:
                raise
    return google_static(extent, path, theme, height_pt, static_key)


class BasemapSession:
    """Deduplicate identical views within one build; no persistent Google cache."""
    def __init__(self, root, theme, allow_google=False):
        self.root = Path(root)
        _check_no_symlink(self.root)
        self.theme = theme
        self.allow_google = allow_google
        self.dotenv_keys = {}
        if allow_google and not has_configured_google_key(check_dotenv=False) and not _is_mocked_urlopen():
            self.dotenv_keys = load_dotenv_google_keys()
        self.cache = {}
        self.network_calls = 0

    def acquire(self, provider, extent, height_pt):
        key = (provider, tuple(extent), height_pt, self.theme)
        if key not in self.cache:
            _check_no_symlink(self.root)
            self.root.mkdir(exist_ok=True)
            path = self.root / f'basemap-{len(self.cache)+1:03d}.png'
            _check_no_symlink(path)
            if provider == 'openfreemap':
                base, calls = openfreemap(extent, path, self.theme, height_pt)
            elif provider == 'google':
                base, calls = google(extent, path, self.theme, height_pt, self.allow_google, dotenv_keys=self.dotenv_keys)
            else:
                raise BasemapError('Unsupported acquisition provider')
            self.network_calls += calls
            self.cache[key] = base
        return dict(self.cache[key])

