export interface ActivityPoint { key:string; evaluations:number; }
export function shiftDay(value:string,days:number):string {
  const date=new Date(value+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+days);return date.toISOString().slice(0,10);
}
function monday(value:string):string { const day=new Date(value+'T00:00:00Z').getUTCDay();return shiftDay(value,-((day+6)%7)); }
export function weekRange(start:string,end:string):string[] {
  const weeks:string[]=[];for(let date=monday(start);date<=end;date=shiftDay(date,7)) weeks.push(date);return weeks;
}
export function weeklyCounts(points:ActivityPoint[],start:string,end:string):number[] {
  const totals=new Map<string,number>();
  for(const point of points) if(point.key>=start && point.key<=end) {
    const week=monday(point.key);totals.set(week,(totals.get(week) ?? 0)+point.evaluations);
  }
  return weekRange(start,end).map(date=>totals.get(date) ?? 0);
}
