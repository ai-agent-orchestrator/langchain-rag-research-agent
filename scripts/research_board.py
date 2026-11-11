"""Render the research-experiment board (one self-contained HTML file) from runs.jsonl records."""
from __future__ import annotations

import json

TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Graph Board</title>
<style>
:root{--bg:#f7f7f4;--panel:#fff;--ink:#1d1d1b;--muted:#6b6b66;--line:#e3e2dc;--accent:#2f5d8a;--good:#2e7d4f;--warn:#b26b00;--bad:#b23b3b;--base:#8a8a84;
--c0:#8a8a84;--c1:#2f5d8a;--c2:#6a4c93;--c3:#2e7d4f;--c4:#b26b00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121416;--panel:#1b1e21;--ink:#e8e8e3;--muted:#9a9a94;--line:#2c3034;--accent:#7fb0e0;--good:#6cc08e;--warn:#e0a54f;--bad:#e07a7a;--base:#9a9a94;--c0:#9a9a94;--c1:#7fb0e0;--c2:#b59ae0;--c3:#6cc08e;--c4:#e0a54f}}
:root[data-theme="dark"]{--bg:#121416;--panel:#1b1e21;--ink:#e8e8e3;--muted:#9a9a94;--line:#2c3034;--accent:#7fb0e0;--good:#6cc08e;--warn:#e0a54f;--bad:#e07a7a;--base:#9a9a94;--c0:#9a9a94;--c1:#7fb0e0;--c2:#b59ae0;--c3:#6cc08e;--c4:#e0a54f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,"Segoe UI","Noto Sans KR",sans-serif}
main{overflow-wrap:anywhere;max-width:1180px;margin:0 auto;padding:20px 16px 60px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}
.muted{color:var(--muted)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}.card .big{font-size:26px;font-weight:650}
.card .sub{font-size:12px;color:var(--muted)}.tag{display:inline-block;padding:1px 7px;border-radius:9px;font-size:11px;border:1px solid var(--line);color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--muted);font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}.scroll{overflow-x:auto}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}details summary{cursor:pointer}pre{white-space:pre-wrap;font-size:12px;margin:6px 0;color:var(--muted)}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden}.bar>i{display:block;height:100%;background:var(--accent)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}select{max-width:100%;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:4px 6px}
svg text{fill:var(--muted);font-size:11px}.legend span{margin-right:12px;font-size:12px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:middle}
</style></head><body><main>
<h1>Research Graph Board</h1>
<div class="muted" id="meta"></div>
<p class="muted" style="font-size:12px">합성 데이터 · 규칙 기반 노드(모델 호출 없음) · 토큰은 모델이었다면 썼을 <b>추정치(≈글자수/2)</b>입니다. 비율 옆 괄호는 Wilson 95% 구간입니다. 실제 모델 결과와 섞어 읽지 마세요.</p>
<div class="row"><label class="muted" style="display:flex;gap:6px;align-items:center;max-width:100%;min-width:0">실행 <select id="runSel" style="min-width:0;flex:1"></select></label></div>

<h2>설정별 요약</h2><div class="cards" id="cards"></div>

<h2>비용–품질 지도 <span class="tag">최적화</span></h2>
<div class="panel"><svg id="scatter" viewBox="0 0 640 300" width="100%" role="img" aria-label="cost quality scatter"></svg>
<div class="legend" id="legend"></div>
<p class="muted" style="font-size:12px;margin:6px 0 0">오른쪽 위로 갈수록 품질이 높고 비싸며, 왼쪽 위가 목표입니다. 회색은 단일 호출 기준선(전체 자료를 한 번에 읽는 비용)입니다. 그래프가 기준선보다 왼쪽에 있으면, 검색으로 줄인 입력이 루프 비용보다 큰 것입니다.</p></div>

<h2>자료 규모별 손익분기 <span class="tag">최적화</span></h2>
<div class="panel"><svg id="sweep" viewBox="0 0 640 260" width="100%" role="img" aria-label="cost by corpus size"></svg>
<div class="muted" style="font-size:12px" id="sweepNote"></div></div>

<h2>항목별 성적</h2><div class="panel scroll"><table id="breakdown"></table></div>

<h2>문항별 결과 <span class="tag">펼쳐서 보고서·경로 보기</span></h2><div class="panel scroll"><table id="cases"></table></div>

<h2>실행 기록</h2><div class="panel"><svg id="history" viewBox="0 0 640 220" width="100%" role="img" aria-label="quality history"></svg><div class="scroll"><table id="runs"></table></div></div>
</main>
<script>
const RUNS = __RUNS__;
const COLORS = ["--c0","--c1","--c2","--c3","--c4"];
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const pct = x => x==null ? "–" : Math.round(x*100)+"%";
const ci = r => r && r.ci ? ` <span class="muted">(${pct(r.ci[0])}–${pct(r.ci[1])})</span>` : "";
const esc = s => String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const allNames = [...new Set(RUNS.flatMap(r=>Object.keys(r.configs)))];
const color = n => css(COLORS[allNames.indexOf(n)%COLORS.length]);
const sel = document.getElementById("runSel");
RUNS.forEach((r,i)=>{const o=document.createElement("option");o.value=i;o.textContent=`${r.at} · ${r.split}${r.note?" · "+r.note:""}`;sel.appendChild(o)});
sel.value = RUNS.length-1; sel.onchange = () => draw(+sel.value);

function draw(i){
  const run = RUNS[i], cfgs = run.configs, names = Object.keys(cfgs);
  document.getElementById("meta").textContent = `실행 ${run.at} · 커밋 ${run.sha||"?"} · 분할 ${run.split} · ${run.dataset} · 문항 ${Object.values(cfgs)[0].summary.n_cases}개`;
  const base = cfgs.baseline_single ? cfgs.baseline_single.summary : null;
  document.getElementById("cards").innerHTML = names.map(n=>{const s=cfgs[n].summary;
    const dq = base && n!=="baseline_single" ? s.quality-base.quality : null, dt = base && n!=="baseline_single" ? s.tokens_mean/base.tokens_mean : null;
    return `<div class="panel card"><div class="row"><span class="dot" style="background:${color(n)}"></span><b>${n}</b></div>
    <div class="big">${pct(s.quality)}</div><div class="sub">품질(지표·인과·조건·균형 평균)</div>
    <div class="sub">추정 토큰 ${Math.round(s.tokens_mean)}${dt?` · 기준선의 <b class="${dt<1?"good":"warn"}">${dt.toFixed(2)}배</b>`:""}</div>
    <div class="sub">루프 평균 ${s.loops_mean.toFixed(1)} · 검수 통과 ${s.verify_pass}/${s.n_cases}${dq!=null?` · 품질 <b class="${dq>0?"good":"bad"}">${dq>0?"+":""}${Math.round(dq*100)}p</b>`:""}</div></div>`}).join("");
  scatter(cfgs); breakdown(cfgs); cases(cfgs); sweep(run.sweep||[]);
}
function scatter(cfgs){
  const svg=document.getElementById("scatter"), W=640,H=300,L=50,B=36,T=12,R=16;
  const pts=Object.entries(cfgs).map(([n,c])=>({n,x:c.summary.tokens_mean,y:c.summary.quality||0}));
  const xmax=Math.max(...pts.map(p=>p.x))*1.15||1;
  const X=x=>L+(W-L-R)*x/xmax, Y=y=>H-B-(H-B-T)*y;
  let g=`<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="${css("--line")}"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H-B}" stroke="${css("--line")}"/>`;
  for(const q of [0,.25,.5,.75,1]) g+=`<text x="${L-6}" y="${Y(q)+4}" text-anchor="end">${q*100}%</text><line x1="${L}" x2="${W-R}" y1="${Y(q)}" y2="${Y(q)}" stroke="${css("--line")}" stroke-dasharray="2 4"/>`;
  for(let k=0;k<=4;k++){const v=xmax*k/4;g+=`<text x="${X(v)}" y="${H-B+16}" text-anchor="middle">${Math.round(v)}</text>`}
  g+=`<text x="${(W+L)/2}" y="${H-4}" text-anchor="middle">추정 토큰 / 문항</text>`;
  const b=cfgs.baseline_single; if(b){g+=`<line x1="${X(b.summary.tokens_mean)}" x2="${X(b.summary.tokens_mean)}" y1="${T}" y2="${H-B}" stroke="${css("--base")}" stroke-dasharray="4 3"/>`}
  for(const p of pts) g+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="7" fill="${color(p.n)}"><title>${p.n}: 품질 ${pct(p.y)}, 토큰 ${Math.round(p.x)}</title></circle><text x="${X(p.x)+10}" y="${Y(p.y)-8}">${p.n}</text>`;
  svg.innerHTML=g;
  document.getElementById("legend").innerHTML=pts.map(p=>`<span><i class="dot" style="background:${color(p.n)}"></i>${p.n}</span>`).join("");
}
function breakdown(cfgs){
  const rows=[["필수 지표 포함","metric_coverage"],["인과관계 보존","causal_retention"],["조건·예외 보존","constraint_retention"],["반대 근거 반영","balance"]];
  const names=Object.keys(cfgs);
  let h=`<tr><th>항목</th>${names.map(n=>`<th class="num">${n}</th>`).join("")}</tr>`;
  for(const [label,key] of rows) h+=`<tr><td>${label}</td>${names.map(n=>{const r=cfgs[n].summary[key];return `<td class="num">${r.ok}/${r.n} · ${pct(r.rate)}${ci(r)}</td>`}).join("")}</tr>`;
  h+=`<tr><td>근거 없는 수치(개)</td>${names.map(n=>{const v=cfgs[n].summary.unsupported_numbers;return `<td class="num ${v?"bad":"good"}">${v}</td>`}).join("")}</tr>`;
  h+=`<tr><td>반대 근거 없음 명시</td>${names.map(n=>{const s=cfgs[n].summary;return `<td class="num">${s.no_con_noted}/${s.no_con_cases}</td>`}).join("")}</tr>`;
  document.getElementById("breakdown").innerHTML=h;
}
function caseScore(c){const xs=[...Object.values(c.metric_hits),...c.causal,...c.constraints,...c.balance];return xs.length?xs.filter(Boolean).length/xs.length:null}
function cases(cfgs){
  const names=Object.keys(cfgs), ids=cfgs[names[0]].cases.map(c=>c.case);
  let h=`<tr><th>문항</th>${names.map(n=>`<th>${n}</th>`).join("")}</tr>`;
  for(const id of ids){h+=`<tr><td><b>${id}</b></td>`+names.map(n=>{const c=cfgs[n].cases.find(x=>x.case===id);const q=caseScore(c);
    const miss=[...Object.entries(c.metric_hits).filter(([k,v])=>!v).map(([k])=>"지표:"+k),...c.causal.map((v,i)=>v?null:"인과"+(i+1)),...c.constraints.map((v,i)=>v?null:"조건"+(i+1)),...c.balance.map(v=>v?null:"반대근거")].filter(Boolean);
    return `<td><div class="row"><b class="${q>=.99?"good":q>=.6?"warn":"bad"}">${pct(q)}</b><span class="muted">${c.tokens_in+c.tokens_out} tok · 루프 ${c.gap_searches+c.rewrites}</span></div>
    <div class="bar"><i style="width:${(q||0)*100}%;background:${color(n)}"></i></div>
    ${miss.length?`<div class="muted" style="font-size:11px">빠짐: ${esc(miss.join(", "))}</div>`:""}
    ${c.verify_codes.length?`<div class="warn" style="font-size:11px">검수: ${esc(c.verify_codes.join(", "))}</div>`:""}
    <details><summary class="muted" style="font-size:12px">보고서·경로</summary><pre>${esc(c.report||"(빈 보고서)")}</pre><pre>${esc(c.log.join(" → "))}</pre></details></td>`}).join("")+`</tr>`}
  document.getElementById("cases").innerHTML=h;
}
function sweep(points){
  const svg=document.getElementById("sweep"),note=document.getElementById("sweepNote");
  if(!points.length){svg.innerHTML="";note.textContent="이 실행에는 규모 실험이 없습니다.";return}
  const W=640,H=260,L=56,B=36,T=12,R=16,xs=points.map(p=>p.extra_docs),xmax=Math.max(...xs)||1;
  const ymax=Math.max(...points.flatMap(p=>[p.baseline_single.tokens_mean,p.graph_full.tokens_mean]))*1.1;
  const X=x=>L+(W-L-R)*x/xmax,Y=y=>H-B-(H-B-T)*y/ymax;
  let g=`<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="${css("--line")}"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H-B}" stroke="${css("--line")}"/>`;
  for(let k=0;k<=4;k++){const v=ymax*k/4;g+=`<text x="${L-6}" y="${Y(v)+4}" text-anchor="end">${Math.round(v)}</text>`}
  for(const x of xs) g+=`<text x="${X(x)}" y="${H-B+16}" text-anchor="middle">+${x}</text>`;
  g+=`<text x="${(W+L)/2}" y="${H-4}" text-anchor="middle">문항당 추가 배경 문서 수</text>`;
  for(const name of ["baseline_single","graph_full"]){const pts=points.map(p=>[X(p.extra_docs),Y(p[name].tokens_mean)]);
    g+=`<polyline fill="none" stroke="${color(name)}" stroke-width="2.5" points="${pts.map(p=>p.join(",")).join(" ")}"/>`;
    points.forEach((p,i)=>{g+=`<circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="4" fill="${color(name)}"><title>${name} +${p.extra_docs}: 토큰 ${Math.round(p[name].tokens_mean)}, 품질 ${pct(p[name].quality)}</title></circle>`});
    const last=pts[pts.length-1];g+=`<text x="${last[0]-4}" y="${last[1]-8}" text-anchor="end">${name}</text>`}
  svg.innerHTML=g;
  const cross=points.find(p=>p.graph_full.tokens_mean<p.baseline_single.tokens_mean);
  note.innerHTML=(cross?`배경 문서가 문항당 <b>+${cross.extra_docs}개</b>일 때부터 그래프가 단일 호출보다 싸집니다 `:`이 범위에서는 그래프가 단일 호출보다 비쌉니다 `)+
   `(루프 비용 &lt; 검색으로 줄인 입력). 품질: `+points.map(p=>`+${p.extra_docs} → 기준선 ${pct(p.baseline_single.quality)} / 그래프 ${pct(p.graph_full.quality)}`).join(" · ");
}
function history(){
  const svg=document.getElementById("history"),W=640,H=220,L=50,B=30,T=10,R=16,n=RUNS.length;
  const X=i=>L+(W-L-R)*(n<2?.5:i/(n-1)),Y=y=>H-B-(H-B-T)*y;
  let g=`<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" stroke="${css("--line")}"/>`;
  for(const q of [0,.5,1]) g+=`<text x="${L-6}" y="${Y(q)+4}" text-anchor="end">${q*100}%</text>`;
  for(const name of allNames){const pts=RUNS.map((r,i)=>r.configs[name]?[X(i),Y(r.configs[name].summary.quality||0)]:null).filter(Boolean);
    if(pts.length>1) g+=`<polyline fill="none" stroke="${color(name)}" stroke-width="2" points="${pts.map(p=>p.join(",")).join(" ")}"/>`;
    for(const p of pts) g+=`<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="${color(name)}"><title>${name}</title></circle>`}
  RUNS.forEach((r,i)=>{g+=`<text x="${X(i)}" y="${H-B+16}" text-anchor="middle">#${i+1}</text>`});
  svg.innerHTML=g;
  document.getElementById("runs").innerHTML=`<tr><th>#</th><th>시각</th><th>커밋</th><th>분할</th><th>메모</th>${allNames.map(n=>`<th class="num">${n}</th>`).join("")}</tr>`+
    RUNS.map((r,i)=>`<tr><td>${i+1}</td><td>${r.at}</td><td>${r.sha||""}</td><td>${r.split}</td><td>${esc(r.note||"")}</td>${allNames.map(n=>`<td class="num">${r.configs[n]?pct(r.configs[n].summary.quality)+" · "+Math.round(r.configs[n].summary.tokens_mean):"–"}</td>`).join("")}</tr>`).join("");
}
draw(RUNS.length-1); history();
</script></body></html>"""


def render(runs: list[dict]) -> str:
    return TEMPLATE.replace("__RUNS__", json.dumps(runs, ensure_ascii=False).replace("</", "<\\/"))
