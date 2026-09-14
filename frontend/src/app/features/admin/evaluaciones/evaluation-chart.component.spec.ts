import { ElementRef } from '@angular/core';
import { vi } from 'vitest';
import { EvaluationChartComponent } from './evaluation-chart.component';
const mocks = vi.hoisted(() => ({ init: vi.fn() }));
vi.mock('echarts/core', () => ({ use: vi.fn(), init: mocks.init }));
describe('Chart lifecycle and resize performance', () => {
  let callback: ResizeObserverCallback,
    disconnect: ReturnType<typeof vi.fn>,
    chart: {
      on: ReturnType<typeof vi.fn>;
      setOption: ReturnType<typeof vi.fn>;
      resize: ReturnType<typeof vi.fn>;
      dispose: ReturnType<typeof vi.fn>;
    },
    frames: Map<number, FrameRequestCallback>,
    next: number;
  beforeEach(() => {
    frames = new Map();
    next = 0;
    disconnect = vi.fn();
    chart = { on: vi.fn(), setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() };
    mocks.init.mockReset().mockReturnValue(chart);
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(cb: ResizeObserverCallback) {
          callback = cb;
        }
        observe() {}
        disconnect = disconnect;
      },
    );
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frames.set(++next, cb);
      return next;
    });
    vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  });
  afterEach(() => vi.unstubAllGlobals());
  function create(deferOffscreen = false) {
    const c = new EvaluationChartComponent();
    c.deferOffscreen = deferOffscreen;
    Object.assign(c, {
      canvas: new ElementRef({ clientWidth: 800, clientHeight: 400, closest: () => null }),
    });
    c.ngAfterViewInit();
    return c;
  }
  function resize(width: number, height: number) {
    callback([{ contentRect: { width, height } } as ResizeObserverEntry], {} as ResizeObserver);
  }
  it('keeps one instance across 100 hide/show notifications with the same dimensions', () => {
    const c = create();
    for (let i = 0; i < 100; i++) {
      resize(0, 0);
      resize(800, 400);
    }
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(chart.resize).not.toHaveBeenCalled();
    expect(chart.setOption).toHaveBeenCalledTimes(1);
    c.ngOnDestroy();
  });
  it('coalesces a resize burst and cancels queued work on destruction', () => {
    const c = create();
    resize(700, 400);
    resize(600, 400);
    resize(500, 400);
    expect(frames.size).toBe(1);
    const pending = [...frames.values()][0];
    frames.clear();
    pending(0);
    expect(chart.resize).toHaveBeenCalledTimes(1);
    resize(450, 400);
    c.ngOnDestroy();
    expect(frames.size).toBe(0);
    expect(disconnect).toHaveBeenCalledTimes(1);
    expect(chart.dispose).toHaveBeenCalledTimes(1);
  });
  it('disposes all instances when navigating repeatedly between modules', () => {
    for (let i = 0; i < 50; i++) {
      const c = create();
      c.ngOnDestroy();
    }
    expect(mocks.init).toHaveBeenCalledTimes(50);
    expect(chart.dispose).toHaveBeenCalledTimes(50);
    expect(disconnect).toHaveBeenCalledTimes(50);
    expect(frames.size).toBe(0);
  });
  function observeVisibility() {
    let notify: IntersectionObserverCallback;
    const stop = vi.fn();
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(cb: IntersectionObserverCallback) {
          notify = cb;
        }
        observe() {}
        disconnect = stop;
      },
    );
    return {
      stop,
      visible: (isIntersecting: boolean) =>
        notify([{ isIntersecting } as IntersectionObserverEntry], {} as IntersectionObserver),
    };
  }
  it('defers offscreen initialization and uses the latest options when approaching the viewport', () => {
    const visibility = observeVisibility();
    const c = create(true);
    resize(800, 400);
    visibility.visible(false);
    c.options = { title: { text: 'Updated selection' } };
    c.ngOnChanges();
    expect(mocks.init).not.toHaveBeenCalled();
    visibility.visible(true);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(chart.setOption.mock.calls[0][0].title.text).toBe('Updated selection');
    visibility.visible(false);
    visibility.visible(true);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    expect(visibility.stop).toHaveBeenCalled();
    c.ngOnDestroy();
  });
  it('never initializes a deferred chart after destruction', () => {
    const visibility = observeVisibility();
    const c = create(true);
    c.ngOnDestroy();
    visibility.visible(true);
    resize(800, 400);
    expect(mocks.init).not.toHaveBeenCalled();
    expect(visibility.stop).toHaveBeenCalledTimes(1);
  });
  it('falls back to immediate rendering without IntersectionObserver', () => {
    vi.stubGlobal('IntersectionObserver', undefined);
    const c = create(true);
    expect(mocks.init).toHaveBeenCalledTimes(1);
    c.ngOnDestroy();
  });
});
