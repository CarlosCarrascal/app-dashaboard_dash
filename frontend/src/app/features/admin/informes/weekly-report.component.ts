import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subscription } from 'rxjs';
import { ApiClient } from '../../../core/api/api-client.service';
import { EvaluationChartComponent } from '../evaluaciones/evaluation-chart.component';

import { WeeklyReport, reportOptions } from './weekly-series';
export { isoWeekLabel, reportOptions, type WeeklyReport } from './weekly-series';
import { grainLabel } from '../evaluaciones/evaluation-format';
@Component({selector:'app-weekly-report',standalone:true,imports:[FormsModule,RouterLink,EvaluationChartComponent],templateUrl:'./weekly-report.component.html'})
export class WeeklyReportComponent {
  private api=inject(ApiClient); private route=inject(ActivatedRoute); private router=inject(Router); private destroy=inject(DestroyRef); private request?:Subscription;
  metric=signal('n_flores'); weeks=signal(26); grain=signal(''); end=signal(''); start=signal('');
  readonly grainLabel=grainLabel;
  selectedFund=signal(''); slideIndex=signal(0);
  private scope:Record<string,unknown>={};
  slides=computed(()=>this.funds().filter(f=>!this.selectedFund()||String(f.id)===this.selectedFund()));
  preview=computed(()=>this.slides()[Math.min(this.slideIndex(),this.slides().length-1)]);
  previewIndex=computed(()=>Math.min(this.slideIndex(),Math.max(0,this.slides().length-1)));
  moveSlide(delta:number){this.slideIndex.set(Math.max(0,Math.min(this.slides().length-1,this.previewIndex()+delta)));}

  exporting=signal(false); exportError=signal(false);
  report=signal<WeeklyReport|null>(null); loading=signal(false); error=signal(false);
  title=computed(()=>(this.report()?.metric ?? this.metric())==='cuajo'?'Cuajos observados':'Flores observadas');
  funds=computed(()=>{const r=this.report();if(!r)return [];return [...new Map(r.points.map(p=>[p.fundo_id,p.fundo])).entries()].map(([id,name])=>{const points=r.points.filter(p=>p.fundo_id===id);return {id,name,points,options:reportOptions(r,points),available:points.reduce((n,p)=>n+p.available,0),evaluations:points.reduce((n,p)=>n+p.evaluations,0)};});});
  constructor(){this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroy)).subscribe(p=>{
    this.metric.set(p.get('indicador')==='cuajo'?'cuajo':'n_flores');this.weeks.set([8,12,26,53].includes(Number(p.get('semanas')))?Number(p.get('semanas')):26);
    this.grain.set(p.get('grano')||'');this.end.set(p.get('hasta')||'');this.start.set(p.get('desde')||'');
    this.scope={};for(const k of ['empresa_id','fundo_id','modulo_id','lote_id','evaluador_id','search']){if(p.get(k))this.scope[k]=p.get(k);}
    this.load();
  });}
  apply(){void this.router.navigate([],{relativeTo:this.route,queryParams:{...this.scope,indicador:this.metric(),semanas:this.weeks(),grano:this.grain()||null,desde:this.start()||null,hasta:this.end()||null}});}
  load(){this.request?.unsubscribe();this.loading.set(true);this.error.set(false);this.report.set(null);
    this.request=this.api.weeklyReport<WeeklyReport>({...this.scope,metric:this.metric(),weeks:this.weeks(),grano:this.grain()||undefined,desde:this.start()||undefined,hasta:this.end()||undefined}).pipe(takeUntilDestroyed(this.destroy)).subscribe({next:r=>{this.report.set(r);this.slideIndex.set(0);this.selectedFund.set('');this.loading.set(false);},error:()=>{this.error.set(true);this.loading.set(false);}});
  }
  openPoint(key:string){const [id,week]=key.split('|');const r=this.report();if(!id||!week||!r)return;const until=new Date(week+'T00:00:00Z');until.setUTCDate(until.getUTCDate()+6);void this.router.navigate(['/admin/evaluaciones/flores'],{queryParams:{vista:'registros',periodo:'rango',desde:week,hasta:until.toISOString().slice(0,10)<r.hasta! ? until.toISOString().slice(0,10):r.hasta,modulo_id:id,grano:r.grano}});}
  export(){const r=this.report();if(!r||!r.points.length||this.exporting())return;this.exporting.set(true);this.exportError.set(false);
    this.api.exportWeeklyReport({...this.scope,metric:r.metric,desde:r.desde,hasta:r.hasta,grano:r.grano,...(this.selectedFund()?{fundo_id:Number(this.selectedFund())}:{})}).pipe(takeUntilDestroyed(this.destroy)).subscribe({next:blob=>{
      const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=`evaluaciones-${r.metric}-${r.hasta}.pptx`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);this.exporting.set(false);
    },error:()=>{this.exporting.set(false);this.exportError.set(true);}});
  }
  number(n:number){return n.toLocaleString('es-PE',{maximumFractionDigits:1});}
}
