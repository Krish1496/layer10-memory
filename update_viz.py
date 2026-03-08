"""
update_viz.py — Builds or updates viz/index.html from outputs/graph.json

Run:  python update_viz.py

- If viz/index.html already exists  →  updates the data inside it
- If viz/index.html does NOT exist  →  builds a brand new one from scratch
"""

import json
import re
import os

GRAPH_JSON = os.path.join("outputs", "graph.json")
VIZ_DIR    = "viz"
VIZ_HTML   = os.path.join(VIZ_DIR, "index.html")

# ── Load graph data ───────────────────────────────────────────────────────────

if not os.path.exists(GRAPH_JSON):
    print(f"ERROR: {GRAPH_JSON} not found.")
    print("Run the pipeline first:  python run_pipeline.py")
    exit(1)

with open(GRAPH_JSON, "r", encoding="utf-8") as f:
    graph_data = json.load(f)

DATA_JS = json.dumps(graph_data)


# ── Full HTML page (used when building from scratch) ─────────────────────────

def build_html(data_js):
    return (
        HTML_BEFORE_DATA
        + data_js
        + HTML_AFTER_DATA
    )


HTML_BEFORE_DATA = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Layer10 Memory Graph Explorer</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"></script>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f1117;color:#e2e8f0;height:100vh;display:flex;flex-direction:column}
    header{background:#1a1d27;border-bottom:1px solid #2d3148;padding:12px 20px;display:flex;align-items:center;gap:16px;flex-shrink:0}
    header h1{font-size:16px;font-weight:600;color:#a78bfa}
    header span{font-size:12px;color:#64748b}
    .fg{display:flex;gap:8px;margin-left:auto;align-items:center}
    .fg label{font-size:12px;color:#94a3b8}
    select,input[type=text]{background:#252836;border:1px solid #374151;color:#e2e8f0;border-radius:6px;padding:4px 8px;font-size:12px}
    .btn{background:#7c3aed;color:#fff;border:none;border-radius:6px;padding:4px 12px;font-size:12px;cursor:pointer}
    .btn:hover{background:#6d28d9}
    .bto{background:transparent;border:1px solid #4b5563;color:#94a3b8}
    .bto:hover{border-color:#7c3aed;color:#a78bfa}
    .main{display:flex;flex:1;overflow:hidden}
    #gc{flex:1;position:relative;border-right:1px solid #2d3148}
    #network{width:100%;height:100%}
    .leg{position:absolute;bottom:16px;left:16px;background:rgba(26,29,39,.92);border:1px solid #2d3148;border-radius:8px;padding:10px 14px;font-size:11px}
    .li{display:flex;align-items:center;gap:8px;margin:4px 0;color:#94a3b8}
    .dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
    #sp{width:380px;flex-shrink:0;display:flex;flex-direction:column;overflow:hidden;background:#13151f}
    .tabs{display:flex;border-bottom:1px solid #2d3148;background:#1a1d27;flex-shrink:0}
    .tab{padding:10px 16px;font-size:12px;cursor:pointer;border-bottom:2px solid transparent;color:#64748b;transition:all .15s}
    .tab.active{border-bottom-color:#7c3aed;color:#a78bfa}
    .tc{display:none;flex:1;overflow-y:auto;padding:16px}
    .tc.active{display:block}
    .eh{background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:12px 14px;margin-bottom:12px}
    .en{font-size:16px;font-weight:600;color:#f1f5f9}
    .et{font-size:11px;color:#a78bfa;text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
    .al{margin-top:6px;font-size:11px;color:#64748b}
    .ac{display:inline-block;background:#252836;border:1px solid #374151;border-radius:4px;padding:2px 6px;margin:2px;font-size:11px;color:#94a3b8}
    .st{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;margin:12px 0 8px}
    .cc{background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:10px 12px;margin-bottom:8px;cursor:pointer;transition:border-color .15s}
    .cc:hover{border-color:#7c3aed}
    .cc.active{border-color:#7c3aed;background:#1e1b3a}
    .cr{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
    .cs{color:#93c5fd;font-size:12px;font-weight:500}
    .cp{background:#312e81;color:#a5b4fc;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:.06em}
    .cp.h{background:#292524;color:#78716c}
    .co{color:#86efac;font-size:12px;font-weight:500}
    .cm{display:flex;gap:8px;margin-top:5px}
    .b{font-size:10px;padding:2px 6px;border-radius:4px}
    .bc{background:#14532d;color:#86efac}
    .bh{background:#292524;color:#78716c}
    .bf{background:#1e293b;color:#94a3b8}
    .ec{font-size:10px;color:#64748b;margin-left:auto}
    .ep{background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:12px;margin-top:8px}
    .ei{margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid #252836}
    .ei:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
    .em{font-size:10px;color:#64748b;margin-bottom:4px}
    .ef{color:#94a3b8}
    .ex{font-size:12px;color:#cbd5e1;background:#0f1117;border-left:3px solid #7c3aed;padding:6px 10px;border-radius:0 4px 4px 0;line-height:1.5}
    .es{font-size:10px;color:#4b5563;margin-top:4px}
    .mc{background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:10px 12px;margin-bottom:8px;font-size:12px}
    .ma{color:#7c3aed;margin:0 6px}
    .mr{color:#64748b;font-size:11px;margin-top:4px}
    .mt{color:#a78bfa;font-size:10px;text-transform:uppercase}
    .sb{display:flex;gap:8px;margin-bottom:16px}
    .sb input{flex:1}
    .rc{background:#1a1d27;border:1px solid #2d3148;border-radius:8px;padding:10px 12px;margin-bottom:8px;cursor:pointer}
    .nr{color:#4b5563;font-size:13px;text-align:center;margin-top:40px}
    .sbar{display:flex;gap:16px;padding:8px 16px;background:#1a1d27;border-top:1px solid #2d3148;font-size:11px;color:#64748b;flex-shrink:0}
    .st2{display:flex;gap:4px}
    .st2 strong{color:#94a3b8}
    ::-webkit-scrollbar{width:5px}
    ::-webkit-scrollbar-track{background:transparent}
    ::-webkit-scrollbar-thumb{background:#374151;border-radius:3px}
  </style>
</head>
<body>
<header>
  <h1>Layer10 Memory Graph</h1>
  <span id="hs">Loading…</span>
  <div class="fg">
    <label>Show:</label>
    <select id="fc">
      <option value="all">All claims</option>
      <option value="current" selected>Current only</option>
      <option value="historical">Historical only</option>
    </select>
    <label>Type:</label>
    <select id="ft">
      <option value="all">All types</option>
      <option value="Person">Person</option>
      <option value="Project">Project</option>
      <option value="Component">Component</option>
      <option value="Technology">Technology</option>
      <option value="Infrastructure">Infrastructure</option>
    </select>
    <button class="btn bto" style="font-size:11px;padding:3px 8px" onclick="network.fit({animation:true})">Reset view</button>
  </div>
</header>
<div class="main">
  <div id="gc">
    <div id="network"></div>
    <div class="leg">
      <div class="li"><div class="dot" style="background:#6366f1"></div>Person</div>
      <div class="li"><div class="dot" style="background:#10b981"></div>Project</div>
      <div class="li"><div class="dot" style="background:#f59e0b"></div>Component</div>
      <div class="li"><div class="dot" style="background:#ef4444"></div>Technology</div>
      <div class="li"><div class="dot" style="background:#8b5cf6"></div>Infrastructure</div>
      <div class="li" style="margin-top:6px"><div style="width:28px;height:2px;background:#5eead4"></div>Current</div>
      <div class="li"><div style="width:28px;height:2px;background:#374151;border-top:1px dashed #4b5563"></div>Historical</div>
    </div>
  </div>
  <div id="sp">
    <div class="tabs">
      <div class="tab active" onclick="sw('details')">Details</div>
      <div class="tab" onclick="sw('search')">Search</div>
      <div class="tab" onclick="sw('merges')">Merges</div>
    </div>
    <div id="tab-details" class="tc active">
      <div id="ph" style="color:#4b5563;font-size:13px;margin-top:40px;text-align:center">← Click a node to explore it</div>
      <div id="ed" style="display:none">
        <div class="eh"><div class="en" id="dn"></div><div class="et" id="dt"></div><div class="al" id="da"></div></div>
        <div class="st">Claims</div>
        <div id="cl"></div>
        <div id="evs" style="display:none">
          <div class="st">Evidence for selected claim</div>
          <div id="evl" class="ep"></div>
        </div>
      </div>
    </div>
    <div id="tab-search" class="tc">
      <div class="sb">
        <input type="text" id="si" placeholder="Search entities or claims…" onkeydown="if(event.key==='Enter')doSearch()"/>
        <button class="btn" style="font-size:11px;padding:3px 8px" onclick="doSearch()">Search</button>
      </div>
      <div id="sr"></div>
    </div>
    <div id="tab-merges" class="tc">
      <div class="st">Merge Audit Log</div>
      <div id="ml"></div>
    </div>
  </div>
</div>
<div class="sbar">
  <div class="st2"><strong id="se">—</strong>&nbsp;entities</div>
  <div class="st2"><strong id="sc">—</strong>&nbsp;claims</div>
  <div class="st2"><strong id="sv">—</strong>&nbsp;evidence</div>
  <div class="st2"><strong id="sm">—</strong>&nbsp;merges</div>
  <div style="margin-left:auto;color:#4b5563">Click a node → see claims · Click a claim → see evidence</div>
</div>
<script>
const G = """

HTML_AFTER_DATA = """\
;
function byId(id){return G.entities.find(e=>e.id===id)}
function aliases(id){return G.aliases.filter(a=>a.entity_id===id).map(a=>a.alias)}
function evFor(cid){return G.evidence.filter(e=>e.claim_id===cid)}
function claimsFor(id){return G.claims.filter(c=>c.subject_id===id||c.object_id===id)}
const TC={Person:{bg:"#3730a3",bo:"#6366f1",f:"#e0e7ff"},Project:{bg:"#065f46",bo:"#10b981",f:"#d1fae5"},Component:{bg:"#92400e",bo:"#f59e0b",f:"#fef3c7"},Technology:{bg:"#7f1d1d",bo:"#ef4444",f:"#fee2e2"},Infrastructure:{bg:"#4c1d95",bo:"#8b5cf6",f:"#ede9fe"}};
let network,nDS,eDS,cf={cur:"current",typ:"all"};
function buildVis(){
  const ents=G.entities.filter(e=>cf.typ==="all"||e.type===cf.typ);
  const eids=new Set(ents.map(e=>e.id));
  let claims=G.claims.filter(c=>eids.has(c.subject_id)&&(c.object_id?eids.has(c.object_id):true));
  if(cf.cur==="current")claims=claims.filter(c=>c.is_current);
  if(cf.cur==="historical")claims=claims.filter(c=>!c.is_current);
  const nodes=ents.map(e=>{const t=TC[e.type]||TC.Person;return{id:e.id,label:e.name,color:{background:t.bg,border:t.bo,highlight:{background:t.bo,border:"#fff"}},font:{color:t.f,size:12},shape:e.type==="Project"?"box":e.type==="Technology"?"diamond":e.type==="Infrastructure"?"triangle":"dot",size:e.type==="Project"?22:16,borderWidth:2,shadow:true}});
  const em={};const edges=[];
  claims.filter(c=>c.object_id).forEach(c=>{const k=`${c.subject_id}|${c.predicate}|${c.object_id}`;if(em[k])return;em[k]=true;edges.push({id:c.id,from:c.subject_id,to:c.object_id,label:c.predicate,color:{color:c.is_current?"#5eead4":"#374151",highlight:"#a78bfa",opacity:c.is_current?1:.5},font:{color:c.is_current?"#5eead4":"#4b5563",size:9,background:"#13151f"},dashes:!c.is_current,arrows:{to:{enabled:true,scaleFactor:.6}},smooth:{type:"curvedCW",roundness:.1},width:c.is_current?1.5:1})});
  return{nodes,edges};
}
function initNet(){
  const{nodes,edges}=buildVis();
  nDS=new vis.DataSet(nodes);eDS=new vis.DataSet(edges);
  network=new vis.Network(document.getElementById("network"),{nodes:nDS,edges:eDS},{physics:{barnesHut:{gravitationalConstant:-8000,springLength:180,springConstant:.04},stabilization:{iterations:150}},interaction:{hover:true}});
  network.on("click",p=>{if(p.nodes.length>0)showEnt(p.nodes[0])});
}
function updNet(){const{nodes,edges}=buildVis();nDS.clear();eDS.clear();nDS.add(nodes);eDS.add(edges)}
function showEnt(eid){
  sw("details");
  const e=byId(eid);if(!e)return;
  document.getElementById("ph").style.display="none";
  document.getElementById("ed").style.display="block";
  document.getElementById("evs").style.display="none";
  document.getElementById("dn").textContent=e.name;
  document.getElementById("dt").textContent=e.type;
  const al=aliases(eid);
  document.getElementById("da").innerHTML=al.length?"Also known as: "+al.map(a=>`<span class="ac">${a}</span>`).join(" "):"";
  const claims=claimsFor(eid);
  const fil=cf.cur==="current"?claims.filter(c=>c.is_current):cf.cur==="historical"?claims.filter(c=>!c.is_current):claims;
  const list=document.getElementById("cl");
  if(!fil.length){list.innerHTML='<div style="color:#4b5563;font-size:12px">No matching claims.</div>';return}
  list.innerHTML=fil.map(c=>{
    const subj=c.subject_name||c.subject_id;
    const obj=c.object_name||c.object_value||"—";
    const ev=evFor(c.id);
    return`<div class="cc" onclick="showEv('${c.id}',this)"><div class="cr"><span class="cs">${subj}</span><span class="cp ${c.is_current?'':'h'}">${c.predicate}</span><span class="co">${obj}</span></div><div class="cm"><span class="b ${c.is_current?'bc':'bh'}">${c.is_current?"● current":"○ historical"}</span><span class="b bf">${Math.round((c.confidence||.8)*100)}%</span><span class="ec">${ev.length} evidence</span></div></div>`;
  }).join("");
}
function showEv(cid,el){
  document.querySelectorAll(".cc").forEach(x=>x.classList.remove("active"));el.classList.add("active");
  const ev=evFor(cid);const sec=document.getElementById("evs");
  if(!ev.length){sec.style.display="none";return}
  sec.style.display="block";
  document.getElementById("evl").innerHTML=ev.map(e=>`<div class="ei"><div class="em"><span class="ef">${e.author||"?"}</span> · ${(e.ts||"").slice(0,10)} · "${e.subject||""}"</div><div class="ex">"${e.excerpt||""}"</div><div class="es">Source: ${e.source_id||"?"}</div></div>`).join("");
  document.getElementById("evl").scrollIntoView({behavior:"smooth",block:"nearest"});
}
function doSearch(){
  const q=document.getElementById("si").value.trim().toLowerCase();if(!q)return;
  const toks=new Set(q.split(/\\s+/).filter(t=>t.length>2));
  const res=G.claims.map(c=>{
    const txt=[c.subject_name,c.predicate,c.object_name,c.object_value].filter(Boolean).join(" ").toLowerCase();
    let s=0;toks.forEach(t=>{if(txt.includes(t))s++});if(c.is_current)s+=.5;return{s,c};
  }).filter(x=>x.s>0).sort((a,b)=>b.s-a.s).slice(0,8);
  const div=document.getElementById("sr");
  if(!res.length){div.innerHTML='<div class="nr">No results found.</div>';return}
  div.innerHTML=`<div style="font-size:11px;color:#64748b;margin-bottom:8px">Results for: "${q}"</div>`+
  res.map(({c})=>{
    const subj=c.subject_name||c.subject_id,obj=c.object_name||c.object_value||"—";
    const ev=evFor(c.id)[0];
    return`<div class="rc" onclick="network.selectNodes(['${c.subject_id}']);network.focus('${c.subject_id}',{scale:1.2,animation:true});showEnt('${c.subject_id}')"><div class="cr"><span class="cs">${subj}</span><span class="cp ${c.is_current?'':'h'}">${c.predicate}</span><span class="co">${obj}</span></div><div class="cm"><span class="b ${c.is_current?'bc':'bh'}">${c.is_current?"● current":"○ historical"}</span><span class="b bf">${Math.round((c.confidence||.8)*100)}%</span></div>${ev?`<div class="ex" style="margin-top:6px">"${ev.excerpt.slice(0,120)}"</div>`:""}</div>`;
  }).join("");
}
function renderMerges(){
  const m=G.merges,list=document.getElementById("ml");
  if(!m||!m.length){list.innerHTML='<div style="color:#4b5563;font-size:12px">No merges recorded.</div>';return}
  list.innerHTML=m.map(x=>`<div class="mc"><div><span class="mt">${x.merge_type}</span><span style="color:#94a3b8;margin-left:8px">${x.from_id}</span><span class="ma">→</span><span style="color:#a78bfa">${x.to_id}</span></div><div class="mr">${x.reason}</div><div style="font-size:10px;color:#374151;margin-top:3px">${(x.merged_at||"").slice(0,16)}</div></div>`).join("");
}
function sw(name){
  ["details","search","merges"].forEach((n,i)=>{document.querySelectorAll(".tab")[i].classList.toggle("active",n===name);document.getElementById("tab-"+n).classList.toggle("active",n===name)});
}
document.getElementById("fc").addEventListener("change",function(){cf.cur=this.value;updNet()});
document.getElementById("ft").addEventListener("change",function(){cf.typ=this.value;updNet()});
document.getElementById("hs").textContent=`${G.entities.length} entities · ${G.claims.length} claims · ${G.evidence.length} evidence · ${G.merges.length} merges`;
document.getElementById("se").textContent=G.entities.length;
document.getElementById("sc").textContent=G.claims.length;
document.getElementById("sv").textContent=G.evidence.length;
document.getElementById("sm").textContent=G.merges.length;
initNet();renderMerges();
</script>
</body>
</html>"""


# ── Write the file ────────────────────────────────────────────────────────────

os.makedirs(VIZ_DIR, exist_ok=True)

if os.path.exists(VIZ_HTML):
    print("Found existing viz/index.html — updating data...")
    with open(VIZ_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    replacement = "const G = " + DATA_JS + ";"
    # Handle both old format (EMBEDDED_DEMO_DATA) and new format (G = ...)
    if "const G = " in html:
        html = re.sub(r"const G = .*?;", lambda m: replacement, html, flags=re.DOTALL)
    elif "EMBEDDED_DEMO_DATA" in html:
        html = re.sub(r"const EMBEDDED_DEMO_DATA = .*?;", lambda m: "const EMBEDDED_DEMO_DATA = " + DATA_JS + ";", html, flags=re.DOTALL)
    else:
        # Can't find the data marker — rebuild from scratch
        print("Could not find data marker in existing HTML — rebuilding from scratch...")
        html = build_html(DATA_JS)

    with open(VIZ_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ Data updated in existing viz/index.html")

else:
    print("viz/index.html not found — building brand new file...")
    html = build_html(DATA_JS)
    with open(VIZ_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ New viz/index.html created from scratch")

print(f"\nGraph contains:")
print(f"  {len(graph_data['entities'])} entities")
print(f"  {len(graph_data['claims'])} claims")
print(f"  {len(graph_data['evidence'])} evidence items")
print(f"  {len(graph_data['merges'])} merges")
print(f"\nOpen this file in your browser:")
print(f"  {os.path.abspath(VIZ_HTML)}")
