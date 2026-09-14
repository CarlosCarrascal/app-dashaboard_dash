import { AfterViewInit, Component, ElementRef, Input, OnChanges, OnDestroy, SimpleChanges, ViewChild } from '@angular/core';
import * as echarts from 'echarts';
import { ModuleTotal } from '../../core/api/models';

@Component({
  selector: 'app-module-chart',
  standalone: true,
  template: '<div #chart class="module-chart" aria-label="Evaluaciones por módulo"></div>',
  styleUrl: './module-chart.component.scss',
})
export class ModuleChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input() data: ModuleTotal[] = [];
  @ViewChild('chart') private chartElement?: ElementRef<HTMLDivElement>;
  private chart: echarts.EChartsType | null = null;
  private readonly resize = () => this.chart?.resize();

  ngAfterViewInit(): void {
    if (this.chartElement) {
      this.chart = echarts.init(this.chartElement.nativeElement);
      this.renderChart();
      window.addEventListener('resize', this.resize);
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['data'] && this.chart) {
      this.renderChart();
    }
  }

  ngOnDestroy(): void {
    window.removeEventListener('resize', this.resize);
    this.chart?.dispose();
  }

  private renderChart(): void {
    if (!this.chart) {
      return;
    }
    const displayNames: Record<string, string> = {
      estadios: 'Estadios', flores: 'Flores', baya: 'Fruto', pesos: 'Peso', brotes: 'Brotes', ramas: 'Ramas',
    };
    const labels = this.data.map((item) => displayNames[item.module_key] ?? item.module_key);
    const values = this.data.map((item) => item.total);
    this.chart.setOption({
      animationDuration: 450,
      grid: { top: 18, right: 12, bottom: 28, left: 48 },
      tooltip: { trigger: 'axis', backgroundColor: '#171b19', borderWidth: 0, textStyle: { color: '#fff', fontSize: 11 } },
      xAxis: {
        type: 'category',
        data: labels,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e3e7e4' } },
        axisLabel: { color: '#7c8681', fontSize: 10 },
      },
      yAxis: {
        type: 'value',
        splitLine: { lineStyle: { color: '#eef0ef' } },
        axisLabel: { color: '#8a938f', fontSize: 10 },
      },
      series: [
        {
          type: 'bar',
          data: values,
          barMaxWidth: 28,
          itemStyle: { color: '#4d9a78', borderRadius: [3, 3, 0, 0] },
        },
      ],
    });
  }
}
