"""
CJK-aware table formatter for terminal output.
Chinese chars = 2 display columns, ASCII = 1.
Usage:
    from cjk_table import Table
    t = Table(['Name', 'Value'])
    t.add_row(['上海英和智临', '1亿'])
    print(t)
"""

import shutil

def cjk_width(s):
    """Return display width of string using Unicode WCWIDTH standard."""
    from wcwidth import wcswidth
    return wcswidth(str(s))

def pad(s, width):
    s = str(s)
    return s + ' ' * (width - cjk_width(s))

class Table:
    def __init__(self, headers):
        self.headers = headers
        self.rows = []

    def add_row(self, row):
        self.rows.append(row)

    def __str__(self):
        cols = list(zip(self.headers, *self.rows))
        widths = [max(cjk_width(cell) for cell in col) for col in cols]
        # box-drawing characters
        TL = '┌';  TR = '┐';  BL = '└';  BR = '┘'
        VSEP = '┬';  HSEP = '┼';  ASEP = '┴'
        H = '─';  V = '│'
        lines = []
        # top border
        segs = [H * (w + 2) for w in widths]
        lines.append(TL + VSEP.join(segs) + TR)
        # header row
        lines.append(V + ' ' + ((' ' + V + ' ').join(pad(cell, w) for cell, w in zip(self.headers, widths))) + ' ' + V)
        # separator
        segs = [H * (w + 2) for w in widths]
        lines.append('├' + HSEP.join(segs) + '┤')
        # data rows
        for row in self.rows:
            lines.append(V + ' ' + ((' ' + V + ' ').join(pad(cell, w) for cell, w in zip(row, widths))) + ' ' + V)
        # bottom border
        segs = [H * (w + 2) for w in widths]
        lines.append(BL + ASEP.join(segs) + BR)
        return '\n'.join(lines)


if __name__ == '__main__':
    t = Table(['公司', '成立', '规模', '备注'])
    t.add_row(['深圳英众世纪', '2013', '537人', '专精特新+高新, IP3 Century'])
    t.add_row(['上海翊视皓瞳', '2015', '中外合资', '限制高消费+被执行人'])
    t.add_row(['上海英众翊视', '2016', '-', '曹亚联董事长'])
    print(t)