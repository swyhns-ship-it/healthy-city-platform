# -*- coding: utf-8 -*-
"""健康资源:急救站布局模拟(客户端 Leaflet 组件,落站/拖站 what-if)。
os / json 在用到的函数内局部 import(沿用原结构)。"""
import numpy as np
import streamlit as st

import heat_risk
from theme import page_header


@st.cache_data(show_spinner=False)
def _heat_component_data():
    """打包中暑风险组件所需数据(网格有效格 + 模型 + 病例点),供前端 JS 实时算图。"""
    import os
    g = heat_risk._state()["g"]; mdl = heat_risk.model_info()
    built = g["dw_built"].astype(float); dems = g["dis_ems"].astype(float)
    pop = np.nan_to_num(g["pop"].astype(float)) if "pop" in g else np.zeros_like(built)
    mask = np.isfinite(built) & np.isfinite(dems)
    iy, ix = np.where(mask)
    cells = {
        "ix": ix.astype(int).tolist(), "iy": iy.astype(int).tolist(),
        "built": np.round(built[mask] * 1000).astype(int).tolist(),   # 0-1000
        "dems": np.round(dems[mask]).astype(int).tolist(),            # 米
        "pop": np.round(pop[mask]).astype(int).tolist(),              # 每格人口
    }
    meta = {"lon0": float(g["lon0"]), "lat0": float(g["lat0"]), "res": float(g["res"]),
            "nx": int(g["nx"]), "ny": int(g["ny"])}
    cp = heat_risk.cases_points()
    cases = {"lon": [round(float(x), 5) for x in cp["lon"]],
             "lat": [round(float(x), 5) for x in cp["lat"]],
             "sev": [int(s) for s in cp["severe"]]} if cp is not None else {"lon": [], "lat": [], "sev": []}
    ems = {"lon": [], "lat": []}
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # views/ 上一级=仓库根
        E = np.load(os.path.join(_root, "heat_ems_points.npz"), allow_pickle=True)
        ems = {"lon": [round(float(x), 5) for x in E["lon"]],
               "lat": [round(float(x), 5) for x in E["lat"]]}
    except Exception:
        pass
    return {"cells": cells, "meta": meta, "model": mdl, "cases": cases, "ems": ems}


def _heat_component_html(basemap):
    import json
    d = _heat_component_data()
    if basemap == "浅色地图":
        turl = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
    else:
        turl = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
    payload = json.dumps({**d, "turl": turl}, separators=(",", ":"))
    tmpl = _HEAT_HTML_TMPL.replace("/*__DATA__*/null", payload)
    return tmpl


_HEAT_HTML_TMPL = r"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
 body{margin:0;font-family:'Noto Sans SC','Microsoft YaHei',sans-serif;}
 #map{height:560px;width:100%;border-radius:10px;}
 .panel{background:#F6FCF8;border:1px solid #DCEEE3;border-radius:10px;padding:10px 14px;margin-bottom:8px;
   display:flex;flex-wrap:wrap;gap:18px;align-items:center;}
 .ctl{display:flex;flex-direction:column;font-size:13px;color:#33574a;min-width:150px;}
 .ctl b{color:#1B6B3A;font-size:13px;}
 input[type=range]{width:170px;accent-color:#2E9E5B;}
 .seg button{border:1px solid #2E9E5B;background:#fff;color:#1B6B3A;padding:3px 10px;cursor:pointer;font-size:12px;}
 .seg button.on{background:#2E9E5B;color:#fff;}
 .seg button:first-child{border-radius:6px 0 0 6px;} .seg button:last-child{border-radius:0 6px 6px 0;}
 .btn{border:1px solid #2E9E5B;background:#fff;color:#1B6B3A;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;}
 .stat{font-size:13px;color:#33574a;} .stat b{font-size:18px;color:#1B6B3A;}
 .legend{position:absolute;z-index:500;bottom:14px;right:10px;background:rgba(255,255,255,.9);
   padding:6px 9px;border-radius:6px;font-size:11px;color:#444;box-shadow:0 1px 3px rgba(0,0,0,.2);}
 .lgbar{height:9px;width:120px;border-radius:3px;margin:3px 0;}
</style></head><body>
<div class="panel">
  <div class="ctl"><b>当天地表温度 <span id="vlst"></span>°C</b><input id="lst" type="range" step="0.5"></div>
  <div class="ctl"><b>地图显示</b><div class="seg"><button id="vr" class="on">风险水平</button><button id="vd">相对基线 Δ</button><button id="ve">急救站效果</button></div></div>
  <div class="ctl"><b>急救站 what-if</b>
    <div><label style="font-size:12px"><input type="checkbox" id="addems"> 点击地图落站</label>
    <button class="btn" id="clr">清除</button> <span id="nems" style="font-size:12px"></span></div></div>
  <div class="ctl"><label style="font-size:12px"><input type="checkbox" id="exems" checked> 现状急救站</label>
    <label style="font-size:12px"><input type="checkbox" id="cases"> 叠加病例点</label></div>
  <div class="stat">平均重症风险 <b id="smean">–</b> &nbsp; 高风险面积 <b id="shigh">–</b> &nbsp; <span id="emsbox" style="display:none">急救站效果:<b id="sems">–</b></span></div>
</div>
<div style="position:relative"><div id="map"></div>
  <div class="legend"><div id="lgttl">重症风险</div><div class="lgbar" id="lgbar"></div>
   <div style="display:flex;justify-content:space-between"><span id="lglo"></span><span id="lghi"></span></div></div>
</div>
<script>
var D = /*__DATA__*/null;
var M=D.meta, MO=D.model, C=D.cells;
var b=MO.beta, mu=MO.mean, sd=MO.std;
var N=C.ix.length;
// 预存每格 lon/lat
var clon=new Float64Array(N), clat=new Float64Array(N);
for(var i=0;i<N;i++){clon[i]=M.lon0+(C.ix[i]+0.5)*M.res; clat[i]=M.lat0+(C.iy[i]+0.5)*M.res;}
var south=M.lat0, west=M.lon0, north=M.lat0+M.ny*M.res, east=M.lon0+M.nx*M.res;
var bounds=[[south,west],[north,east]];

var map=L.map('map',{center:[31.17,121.45],zoom:9});
L.tileLayer(D.turl,{subdomains:'abcd',maxZoom:19,attribution:'© OpenStreetMap © CARTO'}).addTo(map);
map.fitBounds(bounds);
// 组件在隐藏标签里初始化时容器高度为0,Leaflet取不到尺寸→会退回全球视野。
// 等容器获得真实尺寸(切到本标签)时刷新尺寸并定位到上海,仅首次自动 fitBounds。
var _fitted=false;
function _fixmap(){ var el=document.getElementById('map');
  if(el && el.clientWidth>50 && el.clientHeight>50){ map.invalidateSize();
    if(!_fitted){ map.fitBounds(bounds); _fitted=true; } } }
setTimeout(_fixmap,300); setTimeout(_fixmap,1200);
try{ new ResizeObserver(_fixmap).observe(document.getElementById('map')); }catch(e){}

var cv=document.createElement('canvas'); cv.width=M.nx; cv.height=M.ny;
var ctx=cv.getContext('2d'); var imgd=ctx.createImageData(M.nx,M.ny);
var overlay=L.imageOverlay(cv.toDataURL(),bounds,{opacity:0.72}).addTo(map);

var emsPts=[], emsMarkers=[], caseLayer=null, addMode=false, view='risk';
var baseProb=null;
// 现状急救站(202个,灰色)
var exLayer=L.layerGroup();
for(var i=0;i<D.ems.lon.length;i++){
  L.circleMarker([D.ems.lat[i],D.ems.lon[i]],{radius:3,weight:1,color:'#444',
    fillColor:'#999',fillOpacity:0.85}).bindTooltip('现状急救站').addTo(exLayer);}
exLayer.addTo(map);
document.getElementById('exems').onchange=function(){ if(this.checked)exLayer.addTo(map); else map.removeLayer(exLayer); };

function sig(z){return 1/(1+Math.exp(-z));}
function computeProb(lst,ems){
  var p=new Float64Array(N);
  var zc=MO.const + b.MODIS_LST*(lst-mu.MODIS_LST)/sd.MODIS_LST;
  for(var i=0;i<N;i++){
    var dem=C.dems[i];
    for(var k=0;k<ems.length;k++){
      var dx=(clon[i]-ems[k][0])*111000*Math.cos(clat[i]*Math.PI/180);
      var dy=(clat[i]-ems[k][1])*111000; var dd=Math.sqrt(dx*dx+dy*dy);
      if(dd<dem)dem=dd;
    }
    var z=zc + b.dis_ems*(dem-mu.dis_ems)/sd.dis_ems;
    p[i]=sig(z);
  }
  return p;
}
function lerp(a,c,t){return [a[0]+(c[0]-a[0])*t,a[1]+(c[1]-a[1])*t,a[2]+(c[2]-a[2])*t];}
function riskColor(v){ // 0..1 蓝→黄→红
  if(v<0.5)return lerp([44,123,182],[255,255,191],v/0.5);
  return lerp([255,255,191],[215,25,28],(v-0.5)/0.5);
}
function deltaColor(v,vmax){ // 蓝(降)白(0)红(升)
  var t=Math.min(Math.abs(v)/vmax,1);
  if(v<=0)return lerp([247,247,247],[44,123,182],t);
  return lerp([247,247,247],[215,25,28],t);
}
function draw(){
  var lst=+document.getElementById('lst').value;
  var prob=computeProb(lst,emsPts);
  var arr=prob, vmax=0.3, emsmsg='–';
  if(view==='delta'){ arr=new Float64Array(N); var mx=1e-6;
    for(var i=0;i<N;i++){arr[i]=prob[i]-baseProb[i]; if(Math.abs(arr[i])>mx)mx=Math.abs(arr[i]);} vmax=mx; }
  else if(view==='ems'){ // 加站 vs 不加站(同情景),隔离急救站效果
    var noems=computeProb(lst,[]); arr=new Float64Array(N); var mx2=1e-4, ben=0, sumd=0, mind=0, popben=0;
    for(var i=0;i<N;i++){ arr[i]=prob[i]-noems[i];
      if(Math.abs(arr[i])>mx2)mx2=Math.abs(arr[i]);
      if(arr[i]<-0.002){ben++; sumd+=arr[i]; if(arr[i]<mind)mind=arr[i]; popben+=C.pop[i];} }
    vmax=mx2;
    emsmsg = emsPts.length? ('受益面积 '+(ben*0.25).toFixed(1)+' km²,覆盖人口 '
             +Math.round(popben).toLocaleString()+';重症化概率平均降 '
             +(ben?(-sumd/ben*100).toFixed(2):'0')+' 个百分点,最大降 '+(-mind*100).toFixed(2)+' 个百分点')
             : '勾选「点击地图落站」后点图落站(站点可拖动)';
  }
  var dat=imgd.data; for(var j=0;j<dat.length;j++)dat[j]=0;
  var sum=0,high=0;
  for(var i=0;i<N;i++){
    var col, al;
    if(view==='risk'){ col=riskColor(prob[i]); al=185; }
    else if(view==='delta'){ col=deltaColor(arr[i],vmax); al=185; }
    else { col=deltaColor(arr[i],vmax); al=30+210*Math.min(Math.abs(arr[i])/vmax,1); } // ems:按降幅放大对比
    var px=C.ix[i], py=M.ny-1-C.iy[i]; var o=(py*M.nx+px)*4;
    dat[o]=col[0];dat[o+1]=col[1];dat[o+2]=col[2];dat[o+3]=al;
    sum+=prob[i]; if(prob[i]>=0.7)high++;
  }
  ctx.putImageData(imgd,0,0); overlay.setUrl(cv.toDataURL());
  document.getElementById('vlst').textContent=lst.toFixed(1);
  document.getElementById('smean').textContent=(sum/N).toFixed(2);
  document.getElementById('shigh').textContent=(100*high/N).toFixed(0)+'%';
  document.getElementById('emsbox').style.display = (view==='ems')?'inline':'none';
  document.getElementById('sems').textContent = emsmsg;
  updLegend(vmax);
}
function updLegend(vmax){
  var bar=document.getElementById('lgbar');
  if(view==='delta'||view==='ems'){
    document.getElementById('lgttl').textContent = view==='ems'?'急救站效果(风险下降)':'风险变化 Δ';
    bar.style.background='linear-gradient(90deg,#2C7BB6,#F7F7F7,#D7191C)';
    document.getElementById('lglo').textContent='降 −'+vmax.toFixed(3);
    document.getElementById('lghi').textContent='升 +'+vmax.toFixed(3);}
  else{document.getElementById('lgttl').textContent='重症风险';
    bar.style.background='linear-gradient(90deg,#2C7BB6,#FFFFBF,#D7191C)';
    document.getElementById('lglo').textContent='低';document.getElementById('lghi').textContent='高';}
}
// 初始化滑块范围
var sl=document.getElementById('lst');
sl.min=MO.modis_lst_p10; sl.max=(MO.modis_lst_p90+2); sl.value=MO.modis_lst_ref;
baseProb=computeProb(MO.modis_lst_ref,[]);
sl.addEventListener('input',draw);
function setView(v){view=v;['vr','vd','ve'].forEach(function(id){document.getElementById(id).classList.remove('on');});
  document.getElementById({risk:'vr',delta:'vd',ems:'ve'}[v]).classList.add('on');draw();}
document.getElementById('vr').onclick=function(){setView('risk');};
document.getElementById('vd').onclick=function(){setView('delta');};
document.getElementById('ve').onclick=function(){setView('ems');};
document.getElementById('addems').onchange=function(){addMode=this.checked;};
document.getElementById('clr').onclick=function(){emsPts=[];emsMarkers.forEach(function(m){map.removeLayer(m);});emsMarkers=[];document.getElementById('nems').textContent='';draw();};
document.getElementById('cases').onchange=function(){
  if(this.checked){caseLayer=L.layerGroup();for(var i=0;i<D.cases.lon.length;i++){
    L.circleMarker([D.cases.lat[i],D.cases.lon[i]],{radius:2.5,weight:0,
      fillColor:D.cases.sev[i]?'#C62828':'#1f6feb',fillOpacity:0.7}).addTo(caseLayer);}
    caseLayer.addTo(map);} else if(caseLayer){map.removeLayer(caseLayer);}};
map.on('click',function(e){ if(!addMode)return;
  var idx=emsPts.length;
  emsPts.push([e.latlng.lng,e.latlng.lat]);
  var mk=L.marker([e.latlng.lat,e.latlng.lng],{draggable:true});
  mk.bindTooltip('新增急救站(可拖动)');
  mk.on('drag',function(ev){ var ll=ev.target.getLatLng(); emsPts[idx]=[ll.lng,ll.lat];
    if(view!=='ems'){view='ems';['vr','vd','ve'].forEach(function(id){document.getElementById(id).classList.remove('on');});document.getElementById('ve').classList.add('on');}
    draw(); });
  mk.addTo(map); emsMarkers.push(mk);
  document.getElementById('nems').textContent='已加'+emsPts.length+'个'; setView('ems');});
draw();
</script></body></html>
"""


def _heat_ems():
    """② 急救站布局模拟(客户端实时组件:现状站点 + 落站/拖站 what-if)。"""
    import streamlit.components.v1 as components
    st.caption("灰点为现状 202 个急救站,底图为重症风险预测。拖动「当天地表温度」看高温日风险;"
               "勾选「点击地图落站」后点图新增急救站(可拖动),实时显示重症化概率下降、受益面积与覆盖人口。")
    basemap = st.selectbox("底图", ["街道地图", "浅色地图"], index=0, key="heat_base")
    components.html(_heat_component_html(basemap), height=660, scrolling=False)


def page_health_resource():
    """健康资源维度 · 急救站布局模拟(现状站点 + 落站/拖站 what-if)。"""
    page_header(
        "健康资源 · 急救站布局模拟",
        "以中暑重症风险预测为底图,模拟新增急救站对风险的改善,辅助应急资源选址。")
    _heat_ems()
