// Batch 3: pure, metadata-only filtering. Never inspect or alter raw conversation bytes.
export const normalize = value => String(value ?? '').normalize('NFKC').trim();
const HAN = '零〇○一二兩三四五六七八九十百';
const digit = c => ({'零':0,'〇':0,'○':0,'一':1,'二':2,'兩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9})[c];
export function chineseNumber(s) {
  if (!s || ![...s].every(c=>HAN.includes(c))) return null;
  let sum=0,part=0;
  for (const c of s) {
    if(c==='百'){sum+=(part||1)*100;part=0;}
    else if(c==='十'){sum+=(part||1)*10;part=0;}
    else {part=digit(c);if(part===undefined)return null;}
  }
  return sum+part;
}
export function seriesNumber(title, series) {
  const t=normalize(title), b=normalize(series);
  if(!b || !t.startsWith(b))return null;
  const tail=t.slice(b.length).trimStart();
  // Require an actual numeric identifier immediately after the series name.
  const m=tail.match(/^(?:\(\s*([0-9]+|[零〇○一二兩三四五六七八九十百]+)\s*\)|([0-9]+|[零〇○一二兩三四五六七八九十百]+))(?=$|[\s(【\[:：\-])/u);
  if(!m)return null;
  const s=m[1]||m[2], n=/^[0-9]+$/.test(s)?Number(s):chineseNumber(s);
  return Number.isSafeInteger(n)&&n>0?n:null;
}
export function isoDate(seconds) {
  if(typeof seconds!=='number'||!Number.isFinite(seconds))return null;
  const d=new Date(seconds*1000);
  return Number.isNaN(d.getTime())?null:d.toISOString().slice(0,10);
}
export function filterRows(rows,opts={}) {
  const q=normalize(opts.query).toLocaleLowerCase('zh-TW');
  const series=normalize(opts.series);
  const first=Number(opts.first),last=Number(opts.last);
  return rows.filter(row=>{
    if(q&&!normalize(row.title).toLocaleLowerCase('zh-TW').includes(q))return false;
    if(opts.from||opts.to){
      const d=isoDate(opts.dateField==='create'?row.create_time:row.update_time);
      if(!d || (opts.from&&d<opts.from)||(opts.to&&d>opts.to))return false;
    }
    if(series){
      const n=seriesNumber(row.title,series);
      if(n===null|| (opts.first!==''&&opts.first!=null&&(!Number.isSafeInteger(first)||first<1||n<first))||
        (opts.last!==''&&opts.last!=null&&(!Number.isSafeInteger(last)||last<1||n>last)))return false;
    }
    return true;
  });
}
export function report(rows,opts={}) {
  const byNumber=new Map(),unclassified=[];
  const series=normalize(opts.series);
  let nodes=0;
  for(const row of rows){
    nodes+=row.nodes||0;
    if(series){
      const n=seriesNumber(row.title,series);
      if(n==null)unclassified.push(row.title);
      else byNumber.set(n,(byNumber.get(n)||0)+1);
    }
  }
  const first=Number(opts.first||1),last=Number(opts.last||0);
  const bounded=series&&Number.isSafeInteger(first)&&Number.isSafeInteger(last)&&first>0&&last>=first&&last-first<=10000;
  const missing=bounded?Array.from({length:last-first+1},(_,i)=>i+first).filter(n=>!byNumber.has(n)):[];
  const duplicates=[...byNumber].filter(([,n])=>n>1).map(([n,count])=>({number:n,count})).sort((a,b)=>a.number-b.number);
  return {conversations:rows.length,nodes,missing,duplicates,unknownMessages:true,unclassified};
}
