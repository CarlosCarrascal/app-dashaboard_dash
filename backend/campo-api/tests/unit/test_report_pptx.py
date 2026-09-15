from datetime import date
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as E
import pytest
from openpyxl import load_workbook
from aquanqa_campo_api.modules.admin.weekly_report import WeeklyReport, WeeklyReportPoint
from aquanqa_campo_api.modules.admin.report_pptx import export_weekly_report, C, P

def test_native_chart_and_embedded_excel_preserve_null_zero_and_all_funds():
    points=[]
    for fundo in [1,2]:
        for week,value,n in [(date(2026,9,7),0,1),(date(2026,9,14),None,0)]:
            points.append(WeeklyReportPoint(week=week,fundo_id=fundo,fundo=f'F{fundo}',modulo_id=fundo,modulo='M01',evaluations=1,available=n,total=value,mean=value))
    report=WeeklyReport(metric='n_flores',desde=date(2026,9,7),hasta=date(2026,9,14),grano='captura',grains=['captura'],points=points)
    with ZipFile(BytesIO(export_weekly_report(report))) as z:
        presentation=E.fromstring(z.read('ppt/presentation.xml'))
        assert len(presentation.findall('.//{'+P+'}sldId'))==2
        for i in [1,2]:
            chart=E.fromstring(z.read(f'ppt/slides/charts/chart{i}.xml'))
            vals=chart.findall('.//{'+C+'}numCache/{'+C+'}pt')
            assert [(v.get('idx'),v.find('{'+C+'}v').text) for v in vals]==[('0','0.0')]
            assert chart.find('.//{'+C+'}dispBlanksAs').get('val')=='gap'
            wb=load_workbook(BytesIO(z.read(f'ppt/embeddings/report{i}.xlsx')))
            assert wb.active['B2'].value==0 and wb.active['B3'].value is None
            assert '{{' not in z.read(f'ppt/slides/slide{i}.xml').decode()

def test_export_rejects_empty_query():
    with pytest.raises(ValueError):export_weekly_report(WeeklyReport(metric='cuajo',desde=None,hasta=None,grano=None,grains=[],points=[]))
