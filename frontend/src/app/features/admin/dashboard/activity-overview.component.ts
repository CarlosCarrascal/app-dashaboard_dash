import { FormsModule } from '@angular/forms';

import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';

import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { Router } from '@angular/router';

import { forkJoin, map, of, Subscription, switchMap, timeout } from 'rxjs';

import type { EChartsOption } from 'echarts';

import { ApiClient } from '../../../core/api/api-client.service';

import { EvaluationCounts, EvaluationQuery } from '../../../core/api/models';

import { EvaluationData } from '../evaluaciones/datos/evaluation-data.service';

import { EvaluationChartComponent } from '../evaluaciones/evaluation-chart.component';

import { AppIconComponent } from '../../../shared/ui/app-icon.component';

import { weeklyCounts, weekRange, shiftDay, type ActivityPoint } from './activity-series';



type Family = NonNullable<EvaluationQuery['module_key']>;

type Snapshot = { hasta: string | null; grano: string | null; grains: string[] };

type Trend = { trend: ActivityPoint[] };

type Fund = { id: number; name: string };

type FundLine = Fund & { values: number[]; color: string };

@Component({

  selector:'app-activity-overview', standalone:true,

  imports: [FormsModule, EvaluationChartComponent, AppIconComponent], providers:[EvaluationData],

  templateUrl:'./activity-overview.component.html', styleUrl:'./activity-overview.component.scss',

})

export class ActivityOverviewComponent implements OnInit {

  private readonly api = inject(ApiClient);

  private readonly catalog = inject(EvaluationData);

  private readonly destroy = inject(DestroyRef);

  private readonly router = inject(Router);

  private request?: Subscription;

  readonly family = signal<Family>('estadios');

  readonly families = [{key:'estadios',label:'Estadios'},{key:'flores',label:'Flores'},{key:'baya',label:'Desarrollo de fruto'},{key:'pesos',label:'Peso de fruto'},{key:'brotes',label:'Brotes'},{key:'ramas',label:'Ramas'}];

  readonly weeks = signal(12);

  readonly grain = signal('');

  readonly grains = signal<string[]>([]);

  readonly loading = signal(true);

  readonly failed = signal(false);

  readonly end = signal('');

  readonly start = signal('');

  readonly summary = signal<EvaluationCounts | null>(null);

  readonly lines = signal<FundLine[]>([]);

  readonly hidden = signal<number[]>([]);

  readonly labels = computed(() => this.end() ? weekRange(this.start(),this.end()) : []);

  readonly options = computed<EChartsOption>(() => ({

    grid:{left:14,right:20,top:36,bottom:16,containLabel:true},

    tooltip:{trigger:'axis',confine:true,renderMode:'richText',backgroundColor:'#202622',borderWidth:0,textStyle:{color:'#fff',fontSize:12},valueFormatter:value => `${Number(value).toLocaleString('es-PE')} evaluaciones`},

    xAxis:{type:'category',boundaryGap:false,data:this.labels().map(d=>this.date(d)),axisLine:{show:false},axisTick:{show:false},axisLabel:{color:'#66716A',fontSize:11,hideOverlap:true}},

    yAxis:{type:'value',name:'Evaluaciones',nameTextStyle:{color:'#66716A',fontSize:11,align:'left'},minInterval:1,axisLabel:{color:'#66716A',fontSize:11},splitNumber:4,splitLine:{lineStyle:{color:'#edf0ed',type:'dashed'}}},

    series:this.lines().filter(l=>!this.hidden().includes(l.id)).map(l=>({

      name:l.name,type:'line',smooth:false,symbol:'circle',symbolSize:6,showSymbol:true,

      lineStyle:{width:2.5,color:l.color},itemStyle:{color:l.color},emphasis:{focus:'series'},

      data:l.values.map((value,i)=>({value,lot:`${l.id}|${this.labels()[i]}`})),

    })),

  }));

  ngOnInit() { this.load(); }

  changeFamily(value:string) {

    if (!this.families.some(f=>f.key===value)) return;

    this.family.set(value as Family); this.grain.set(''); this.load();

  }

  changeWeeks(value:string) { this.weeks.set(Number(value) === 8 ? 8 : Number(value) === 24 ? 24 : 12); this.load(); }

  changeGrain(value:string) { if(this.grains().includes(value)) { this.grain.set(value);this.load(); } }

  toggle(id:number) { this.hidden.update(v=>v.includes(id)?v.filter(n=>n!==id):[...v,id]); }

  load() {

    this.request?.unsubscribe(); this.loading.set(true);this.failed.set(false);this.summary.set(null);this.lines.set([]);this.hidden.set([]);

    const family = this.family();

    this.request = forkJoin({

      snapshot:this.api.evaluationAnalytics<Snapshot>({module_key:family,snapshot:true,include_trend:false,grano:this.grain() || undefined}),

      catalog:this.catalog.loadCatalog('fundos'),

    }).pipe(switchMap(({snapshot,catalog})=>{

      this.grains.set(snapshot.grains);this.grain.set(snapshot.grano || '');

      this.end.set(snapshot.hasta || '');

      if(!snapshot.hasta || !snapshot.grano) return of(null);

      const end = snapshot.hasta;

      const start = shiftDay(weekRange(end,end)[0], -(this.weeks()-1)*7);

      this.start.set(start);

      const query = {module_key:family,desde:start,hasta:end,grano:snapshot.grano};

      const funds:Fund[] = catalog.items.map(r=>({id:Number(r['fundo_id']),name:String(r['nombre'] || r['codigo'] || r['fundo_id'])})).filter(f=>Number.isFinite(f.id));

      return forkJoin({

        summary:this.api.evaluationCounts(query),

        total:this.api.evaluationAnalytics<Trend>({...query,series_only:true},true),

        funds:funds.length ? forkJoin(funds.map(f=>this.api.evaluationAnalytics<Trend>({...query,fundo_id:f.id,series_only:true},true).pipe(map(t=>({...f,values:weeklyCounts(t.trend,start,end)}))))) : of([]),

      }).pipe(map(result=>({...result,start,end})));

    }),timeout(30000),takeUntilDestroyed(this.destroy)).subscribe({next:result=>{

      if(result) {

        this.summary.set(result.summary);

        const colors=['#145B45','#42A383','#ADBA5E','#B48250','#6A8FAD','#866F91'];

        const funds=result.funds.filter(f=>f.values.some(n=>n>0));

        const totals=weeklyCounts(result.total.trend,result.start,result.end);

        const residual=totals.map((n,i)=>Math.max(0,n-result.funds.reduce((sum,f)=>sum+f.values[i],0)));

        if(residual.some(n=>n>0)) funds.push({id:0,name:'Sin fundo catalogado',values:residual});

        this.lines.set(funds.map((f,i)=>({...f,color:colors[i%colors.length]})));

      }

      this.loading.set(false);

    },error:()=>{this.failed.set(true);this.loading.set(false);}});

  }

  openPoint(key:string) {

    const [id,date]=key.split('|');

    if(!Number(id) || !this.labels().includes(date)) return;

    this.router.navigate(['/admin/evaluaciones',this.family()],{queryParams:this.recordQuery(date,Number(id))});

  }

  recordQuery(date:string, fundo?:number) {

    return {vista:'registros',periodo:'rango',desde:date,hasta:shiftDay(date,6)>this.end()?this.end():shiftDay(date,6),grano:this.grain(),fundo_id:fundo || undefined};

  }

  total(line:FundLine) { return line.values.reduce((a,b)=>a+b,0); }

  number(value:number) { return new Intl.NumberFormat('es-PE').format(value); }

  date(value:string) { const parsed = new Date(value.slice(0,10)+'T00:00:00Z'); return Number.isNaN(parsed.getTime()) ? '—' : new Intl.DateTimeFormat('es-PE',{day:'numeric',month:'short',timeZone:'UTC'}).format(parsed); }

  grainLabel(value:string) { return ({grupo_historico_planta:'Grupo histórico por planta',grupo_historico_hilera:'Grupo histórico por hilera',registro_access:'Registro histórico',captura:'Captura de campo',planta:'Evaluación por planta'} as Record<string,string>)[value] || value.replaceAll('_',' '); }

}

