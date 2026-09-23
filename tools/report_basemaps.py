"""Street-map acquisition for reports. No ranking queries, no silent fallback."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

MAPLIBRE_JS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.6.1/dist/maplibre-gl.js'
OPEN_STYLES = {'geogrid': 'fiord', 'light': 'positron'}
OPEN_CREDIT = 'OpenFreeMap | © OpenMapTiles | © OpenStreetMap contributors'
SETUP = 'Install requirements-basemaps.txt, then run: python -m playwright install chromium. See docs/BASEMAPS.md.'
PROVIDERS = ('auto', 'openfreemap', 'google', 'supplied', 'schematic')


class BasemapError(ValueError):
    pass


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
                page.set_content('<!doctype html><html><head><style>html,body,#map{margin:0;width:100%;height:100%;overflow:hidden}</style></head><body><div id="map"></div></body></html>')
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
                draw.rectangle((0,im.height-72,im.width,im.height),fill='white')
                draw.text((12,im.height-68),OPEN_CREDIT,font=font,fill='#111111')
                draw.text((12,im.height-36),'openstreetmap.org/copyright',font=font,fill='#111111')
                im.save(path)
                return base_record(path,actual,36*ratio,OPEN_CREDIT+' | openstreetmap.org/copyright','openfreemap'),calls[0]
            finally:
                browser.close()
    except BasemapError:
        raise
    except Exception:
        # Browser exceptions can contain URLs; do not export uncontrolled diagnostics.
        raise BasemapError('OpenFreeMap could not render. Check internet access and browser setup. '+SETUP) from None


def google(extent, path, theme, height_pt, allow_paid=False):
    """Optional Maps Static API; never enabled merely because a key is present."""
    if not allow_paid:
        raise BasemapError('Google maps require explicit --allow-google-maps-charge; billing is separate from DataForSEO. Use free openfreemap or see docs/BASEMAPS.md.')
    key=os.environ.get('GOOGLE_MAPS_API_KEY','').strip()
    if not key:
        raise BasemapError('Set GOOGLE_MAPS_API_KEY with Maps Static API enabled, or use openfreemap. See docs/BASEMAPS.md.')
    w,s,e,n=checked_bounds(extent)
    def y(lat):return math.log(math.tan(math.pi/4+math.radians(lat)/2))
    def lat(y):return math.degrees(2*math.atan(math.exp(y))-math.pi/2)
    width,height=640,round(640*height_pt/516)
    height=min(640,height)
    cx,cy=(math.radians(w)+math.radians(e))/2,(y(s)+y(n))/2
    factor=min((width-128)/(math.radians(e)-math.radians(w)),(height-128)/(y(n)-y(s)))
    zoom=min(20,math.floor(math.log2(factor*2*math.pi/256)))
    if zoom < 0:
        raise BasemapError('Google static map extent is too wide for a single image.')
    scale=256*2**zoom/(2*math.pi)
    actual=checked_bounds([math.degrees(cx-width/(2*scale)),lat(cy-height/(2*scale)),
                           math.degrees(cx+width/(2*scale)),lat(cy+height/(2*scale))])
    params={'center':f'{lat(cy):.10f},{math.degrees(cx):.10f}','zoom':zoom,
            'size':f'{width}x{height}','scale':2,'maptype':'roadmap','format':'png','key':key}
    url='https://maps.googleapis.com/maps/api/staticmap?'+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={'User-Agent':'legends-geogrid/report-basemap'})
    try:
        with urllib.request.urlopen(request,timeout=60) as response:
            if response.headers.get('X-Staticmap-API-Warning'):
                raise BasemapError('Google returned an imagery warning. Check Static Maps setup; no report was created.')
            data=response.read(12_000_001)
            if len(data)>12_000_000:
                raise BasemapError('Google map response exceeded the image limit.')
    except (urllib.error.URLError,OSError):
        raise BasemapError('Google Maps request failed. Check API restrictions, Maps Static API, billing, and connectivity. No retry or free-provider fallback was made.') from None
    validate_image(data,(width*2,height*2))
    path.write_bytes(data)
    return base_record(path,actual,64,'Google Maps | Original provider logo and credits retained','google'),1


class BasemapSession:
    """Deduplicate identical views within one build; no persistent Google cache."""
    def __init__(self, root, theme, allow_google=False):
        self.root=Path(root)
        self.theme=theme
        self.allow_google=allow_google
        self.cache={}
        self.network_calls=0

    def acquire(self, provider, extent, height_pt):
        key=(provider,tuple(extent),height_pt,self.theme)
        if key not in self.cache:
            self.root.mkdir(exist_ok=True)
            path=self.root/f'basemap-{len(self.cache)+1:03d}.png'
            if provider=='openfreemap':
                base,calls=openfreemap(extent,path,self.theme,height_pt)
            elif provider=='google':
                base,calls=google(extent,path,self.theme,height_pt,self.allow_google)
            else:
                raise BasemapError('Unsupported acquisition provider')
            self.network_calls+=calls
            self.cache[key]=base
        return dict(self.cache[key])

