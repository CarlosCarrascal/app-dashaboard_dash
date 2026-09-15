import type { EChartsOption } from 'echarts';
import { weekRange } from '../dashboard/activity-series';
export interface ReportPoint { week:string; fundo_id:number; fundo:string; modulo_id:number; modulo:string; evaluations:number; available:number; total:number|null; mean:number|null; }
export interface WeeklyReport { metric:string; unit:string; desde:string|null; hasta:string|null; grano:string|null; grains:string[]; points:ReportPoint[]; }
export function isoWeekLabel(value:string):string {
  const date=new Date(value+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+4-(date.getUTCDay()||7));
  const start=new Date(Date.UTC(date.getUTCFullYear(),0,1));
  return 'S'+String(Math.ceil((((date.getTime()-start.getTime())/86400000)+1)/7)).padStart(2,'0');
}
export function reportOptions(report:WeeklyReport, points:ReportPoint[]):EChartsOption {
  const weeks=report.desde && report.hasta ? weekRange(report.desde,report.hasta) : [];
  const modules=[...new Map(points.map(p=>[p.modulo_id,p.modulo])).entries()].sort((a,b)=>a[1].localeCompare(b[1]));
  const colors=['#145B45','#23946F','#6D82B8','#D6913D','#9477A9','#358EAA','#AC625B'];
  return {
    color:colors, legend:{type:'scroll',bottom:0,textStyle:{color:'#66716A',fontSize:12}},
    grid:{left:48,right:44,top:22,bottom:72}, tooltip:{trigger:'axis',confine:true,valueFormatter:v=>v == null ? 'Sin dato' : Number(v).toLocaleString('es-PE',{maximumFractionDigits:2})},
    xAxis:{type:'category',data:weeks,boundaryGap:false,axisLabel:{formatter:(v:string)=>isoWeekLabel(v),hideOverlap:true},axisTick:{show:false}},
    yAxis:{type:'value',name:'Promedio',splitLine:{lineStyle:{color:'#EDF0ED'}},axisLine:{show:false}},
    series:modules.map(([id,name])=>({name,type:'line',connectNulls:false,symbol:'circle',symbolSize:6,
      lineStyle:{width:2.5},labelLayout:{moveOverlap:'shiftY'},endLabel:{show:true,formatter:(p:any)=>p.value == null ? '' : Number(p.value).toLocaleString('es-PE',{maximumFractionDigits:1})},
      data:weeks.map(week=>{const p=points.find(p=>p.modulo_id===id && p.week===week);return {value:p?.mean ?? null,lot:`${id}|${week}`};})})),
  };
}
