"""Online street-map panel for saved scan HTML; diagnostic grid remains explicit."""
import json


def street_map_panel(args, results):
    from report_basemaps import MAPLIBRE_JS
    colors={'rank-one':'#155eef','rank-top3':'#8bd450','rank-visible':'#ffd166',
            'rank-buried':'#f79d65','rank-none':'#e55b5b','rank-short':'#c3cad3',
            'rank-empty':'#f1f4f7','rank-error':'#3e4c59'}
    from local_heatmap_poc import result_class
    features=[]
    for result in results:
        label=str(result.rank) if result.rank is not None else ('E' if result.error else '?')
        features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[result.point.lng,result.point.lat]},
                         'properties':{'label':label,'fill':colors[result_class(result)]}})
    # Only coordinates and rank/status are sent into the local browser map.
    payload=json.dumps({'center':[args.center_lng,args.center_lat],
                        'data':{'type':'FeatureCollection','features':features}},allow_nan=False).replace('<','\\u003c')
    return '''<h2>Rank origins on a street map</h2>
<p id="street-status" role="status">Loading OpenFreeMap street imagery. Internet access is required; no API key is needed.</p>
<div id="street-map" style="width:100%;height:600px;visibility:hidden"></div>
<p class="notes">Free street maps use OpenStreetMap data through OpenFreeMap. Google Maps imagery is optional for PDF reports: see the basemap setup guide. Ranking data is unchanged by the background provider.</p>
<p><a href="https://github.com/avalonreset/legends-geogrid/blob/main/docs/BASEMAPS.md">Basemap setup and optional Google Maps</a></p>
<noscript>JavaScript is disabled: street imagery cannot load. The coordinate-only diagnostic below is not a street-map report.</noscript>
<link rel="stylesheet" href="'''+MAPLIBRE_JS[:-3]+'''.css">
<script src="'''+MAPLIBRE_JS+'''"></script>
<script>
(()=>{
 const config='''+payload+''';
 const status=document.getElementById('street-status'),view=document.getElementById('street-map');
 let failed=false,loaded=false;
 function fail(){failed=true;view.style.visibility='hidden';status.textContent='Street map unavailable. Check internet access and reload. Your saved rankings are intact; no coordinate-only map has been substituted.';status.style.color='#b00020';}
 const timer=setTimeout(fail,60000);
 try {
  const points=config.data.features.map(f=>f.geometry.coordinates);
  if(!points.length){clearTimeout(timer);fail();return;}
  const lngs=points.map(p=>p[0]),lats=points.map(p=>p[1]);
  const west=Math.min(config.center[0],...lngs),east=Math.max(config.center[0],...lngs);
  if(east-west>=180){clearTimeout(timer);fail();return;}
  const map=new maplibregl.Map({container:'street-map',style:'https://tiles.openfreemap.org/styles/liberty',
   center:config.center,zoom:12,renderWorldCopies:false,attributionControl:{compact:false}});
  map.addControl(new maplibregl.NavigationControl({showCompass:false}));
  map.on('error',()=>{clearTimeout(timer);fail()});
  map.on('load',()=>{
   map.fitBounds([[west,Math.min(config.center[1],...lats)],[east,Math.max(config.center[1],...lats)]],{padding:50,maxZoom:16,duration:0});
   map.addSource('ranks',{type:'geojson',data:config.data});
   map.addLayer({id:'rank-circles',type:'circle',source:'ranks',paint:{'circle-radius':12,'circle-color':['get','fill'],'circle-stroke-color':'#333333','circle-stroke-width':1}});
   map.addLayer({id:'rank-labels',type:'symbol',source:'ranks',layout:{'text-field':['get','label'],'text-font':['Noto Sans Regular'],'text-size':12,'text-allow-overlap':true},paint:{'text-color':'#000000','text-halo-color':'#ffffff','text-halo-width':1}});
   map.once('idle',()=>{if(!failed&&map.areTilesLoaded()){loaded=true;clearTimeout(timer);view.style.visibility='visible';status.textContent='Street map loaded. Rankings: DataForSEO; basemap: OpenFreeMap / OpenStreetMap.';}});
  });
 }catch(e){clearTimeout(timer);fail();}
})();
</script>'''
