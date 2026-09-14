import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  ViewChild,
} from '@angular/core';
import type { EChartsOption } from 'echarts';
import { BarChart, BoxplotChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  HeatmapChart,
  BoxplotChart,
  ScatterChart,
  LineChart,
  BarChart,
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

@Component({
  selector: 'app-evaluation-chart',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<div #canvas role="img" [attr.aria-label]="label"></div>',
  styles: [
    ':host { display:block; width:100%; height:100%; min-height:140px; } div { width:100%; height:100%; }',
  ],
})
export class EvaluationChartComponent implements AfterViewInit, OnChanges, OnDestroy {
  @Input({ required: true }) options: EChartsOption = {};
  @Input() label = 'Análisis de evaluaciones';
  @Input() deferOffscreen = false;
  @Output() itemSelected = new EventEmitter<string>();
  @ViewChild('canvas') private canvas?: ElementRef<HTMLDivElement>;
  private chart?: echarts.EChartsType;
  private observer?: ResizeObserver;
  private visibilityObserver?: IntersectionObserver;
  private ready = true;
  private destroyed = false;
  private resizeFrame?: number;
  private width = 0;
  private height = 0;
  ngAfterViewInit(): void {
    if (!this.canvas) return;
    this.ready = !this.deferOffscreen || typeof IntersectionObserver === 'undefined';
    if (!this.ready) {
      this.visibilityObserver = new IntersectionObserver(
        (entries) => {
          if (this.destroyed || !entries.some((entry) => entry.isIntersecting)) return;
          this.ready = true;
          this.visibilityObserver?.disconnect();
          this.initialize();
        },
        { root: this.canvas.nativeElement.closest('main'), rootMargin: '200px 0px' },
      );
      this.visibilityObserver.observe(this.canvas.nativeElement);
    }
    this.observer = new ResizeObserver((entries) => {
      const size = entries.find(
        (e) => e.contentRect.width > 0 && e.contentRect.height > 0,
      )?.contentRect;
      if (!size) return;
      if (!this.chart) {
        this.initialize();
        return;
      }
      if (size.width === this.width && size.height === this.height) return;
      this.width = size.width;
      this.height = size.height;
      if (this.resizeFrame !== undefined) return;
      this.resizeFrame = requestAnimationFrame(() => {
        this.resizeFrame = undefined;
        if (this.canvas?.nativeElement.clientWidth && this.canvas.nativeElement.clientHeight)
          this.chart?.resize();
      });
    });
    this.observer.observe(this.canvas.nativeElement);
    if (this.canvas.nativeElement.clientWidth > 0) this.initialize();
  }
  private initialize(): void {
    if (this.destroyed || !this.ready || this.chart || !this.canvas) return;
    if (!this.canvas.nativeElement.clientWidth || !this.canvas.nativeElement.clientHeight) return;
    this.width = this.canvas.nativeElement.clientWidth;
    this.height = this.canvas.nativeElement.clientHeight;
    this.chart = echarts.init(this.canvas.nativeElement);
    this.chart.on('click', (params) =>
      this.itemSelected.emit(String((params.data as { lot?: string })?.lot ?? params.name)),
    );
    this.render();
  }
  ngOnChanges(): void {
    this.render();
  }
  ngOnDestroy(): void {
    this.destroyed = true;
    this.observer?.disconnect();
    this.visibilityObserver?.disconnect();
    if (this.resizeFrame !== undefined) cancelAnimationFrame(this.resizeFrame);
    this.chart?.dispose();
    this.chart = undefined;
  }
  private render(): void {
    this.chart?.setOption(
      {
        ...this.options,
        textStyle: { fontFamily: 'Inter Variable, Inter, sans-serif' },
        aria: { enabled: true, label: { description: this.label } },
        animation: false,
      },
      { notMerge: true },
    );
  }
}
