from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

root = Path(__file__).resolve().parent.parent
doc = Document()
section = doc.sections[0]
section.page_width = Cm(21)
section.page_height = Cm(29.7)
section.top_margin = section.bottom_margin = Cm(2)
section.left_margin = Cm(3)
section.right_margin = Cm(1.5)
normal = doc.styles['Normal']
normal.font.name = 'Times New Roman'
normal.font.size = Pt(14)
normal.font.color.rgb = RGBColor(0, 0, 0)
normal.paragraph_format.space_before = Pt(0)
normal.paragraph_format.space_after = Pt(0)
normal.paragraph_format.line_spacing = 1

table = doc.add_table(rows=5, cols=5)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
widths = [3.7, 3.1, 3.1, 3.1, 3.5]
headers = ['Количество\nрабочих задач', 'Замер 1,\nмс', 'Замер 2,\nмс', 'Замер 3,\nмс', 'Среднее\nвремя, мс']
for column, width in zip(table.columns, widths):
    column.width = Cm(width)
for i, row in enumerate(table.rows):
    row.height = Cm(1.4 if i == 0 else 1.1)
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    cant_split = OxmlElement('w:cantSplit')
    row._tr.get_or_add_trPr().append(cant_split)
    for j, cell in enumerate(row.cells):
        cell.width = Cm(widths[j])
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        text = headers[j] if i == 0 else (str([1,2,4,8][i-1]) if j == 0 else '')
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(14)
        run.font.color.rgb = RGBColor(0, 0, 0)
        run.bold = False
        fonts = run._element.get_or_add_rPr().rFonts
        for attr in ('ascii', 'hAnsi', 'eastAsia', 'cs'):
            fonts.set(qn('w:' + attr), 'Times New Roman')
        margins = OxmlElement('w:tcMar')
        for side in ('top', 'left', 'bottom', 'right'):
            item = OxmlElement('w:' + side)
            item.set(qn('w:w'), '80')
            item.set(qn('w:type'), 'dxa')
            margins.append(item)
        cell._tc.get_or_add_tcPr().append(margins)
properties = table._tbl.tblPr
borders = OxmlElement('w:tblBorders')
for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
    border = OxmlElement('w:' + side)
    border.set(qn('w:val'), 'single')
    border.set(qn('w:sz'), '4')
    border.set(qn('w:color'), '000000')
    borders.append(border)
properties.append(borders)
repeat = OxmlElement('w:tblHeader')
table.rows[0]._tr.get_or_add_trPr().append(repeat)
destination = root / 'Таблица замеров времени.docx'
doc.save(destination)
print(destination)
