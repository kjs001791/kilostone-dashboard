"""Fake revenue and maintenance workbooks (invented values) shaped like the profile: group-label header rows,
client-specific columns, total rows, blank rows, a driving-layout sheet inside a revenue book, a picture in maintenance.
All names below are made up. Used only by tests."""
from __future__ import annotations

import datetime as dt
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CLIENTS = ["ZZCLIENT_ALPHA", "ZZCLIENT_BETA", "ZZCLIENT_GAMMA"]
SHEET_NAMES = ["ZZSHEET_ALPHA", "ZZSHEET_BETA", "ZZSHEET_GAMMA", "ZZSHEET_DELTA"]
OTHER_HEADER = "ZZNOTE_COLUMN"
MX_SHEET = "ZZSHEET_EPSILON"
MX_CLIENTS = [f"ZZMX_CLIENT_{i}" for i in range(1, 7)]
MX_PRICE_COMPANY = [1000 + 100 * i for i in range(6)]
MX_PRICE_INVOICE = [1200 + 100 * i for i in range(6)]
SECRET_STRINGS = CLIENTS + SHEET_NAMES + MX_CLIENTS + [MX_SHEET, OTHER_HEADER, "ZZSHOP", "ZZMEMO"]

# truth: rows expected per sheet of the revenue book A
TRUTH = {"A_sheet1": {"loaded": 6, "blank": 1, "total": 1, "header": 3, "quarantined": 0},
         "A_sheet2": {"loaded": 4, "blank": 0, "total": 1, "header": 3, "quarantined": 0}}


def _matrix_sheet(wb) -> None:
    """Horizontal sheet shaped like the real layout: title and percent block above the header (rows 1-2, cols J..O),
    merged 2-row header at row 3, dates in A, six client columns B..G (kilograms), row-sum column H, a number block in
    J52:K71, a total row (tons), then nine tail lines and blank lines, memos in column I. Values are invented."""
    ws = wb.create_sheet(MX_SHEET)
    ws.cell(1, 1, "ZZTITLE 1월분 거래내역")
    ws.merge_cells("A1:G1")
    for i, name in enumerate(MX_CLIENTS):
        ws.cell(1, 10 + i, name)
        ws.cell(2, 10 + i, 0.1 + 0.01 * i)
    ws.cell(3, 1, "거래처" + chr(10) + "날 짜")
    for i, name in enumerate(MX_CLIENTS):
        ws.cell(3, 2 + i, name)
    ws.cell(3, 8, "합   계")
    for c in range(1, 9):
        ws.merge_cells(start_row=3, start_column=c, end_row=4, end_column=c)
    first, last = 5, 81
    tot = [0.0] * 6
    day = 0
    for r in range(first, last + 1):
        if (r - first) % 3 == 0:
            day += 1
            ws.cell(r, 1, dt.datetime(2020, 1, day))
        vals = [((r * 7 + i * 13) % 40) * 25 + 100 if (r + i) % 4 else None for i in range(6)]
        for i, v in enumerate(vals):
            if v is not None:
                ws.cell(r, 2 + i, v)
                tot[i] += v
        ws.cell(r, 8, sum(v for v in vals if v is not None))
        if 52 <= r <= 71:
            ws.cell(r, 10, 123 + r)
            ws.cell(r, 11, 456 + r)
    tr = last + 1  # 82
    ws.cell(tr, 1, "합    계")
    tons = [t / 1000 for t in tot]
    for i, t in enumerate(tons):
        ws.cell(tr, 2 + i, t)
    ws.cell(tr, 8, sum(tons))

    def block(top, label_price, prices, tail_names):
        ws.cell(top, 1, label_price)
        sup = [p * t for p, t in zip(prices, tons)]
        for i in range(6):
            ws.cell(top, 2 + i, prices[i])
            ws.cell(top + 1, 2 + i, sup[i])
            ws.cell(top + 2, 2 + i, sup[i] * 0.1)
            ws.cell(top + 3, 2 + i, sup[i] * 1.1)
        for k, nm in enumerate(tail_names, start=1):
            ws.cell(top + k, 1, nm)
        ws.cell(top + 1, 8, sum(sup))

    block(84, "단가(회사인정)", MX_PRICE_COMPANY, ["공 급 가 액", "부  가  세", "회사받은금액"])
    ws.cell(84, 9, "마감자료제출시삭제")
    block(89, "단가(발행단가)", MX_PRICE_INVOICE, ["공 급 가 액", "부  가  세", "청구한 금액"])
    ws.cell(94, 1, "차이 금액")
    for i in range(6):
        ws.cell(94, 2 + i, (MX_PRICE_INVOICE[i] - MX_PRICE_COMPANY[i]) * tons[i] * 1.1)
    ws.cell(94, 9, "제출시삭제")


def make(outdir: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XImage
    from PIL import Image

    if outdir.exists():
        shutil.rmtree(outdir)
    rev, mnt = outdir / "revenue", outdir / "maintenance"
    rev.mkdir(parents=True)
    mnt.mkdir(parents=True)

    # revenue book A: sheet1 flat table, sheet2 client-specific two-level header
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAMES[0]
    ws.cell(1, 1, "ZZTITLE monthly sheet")
    hdr = ["일자", "거래처", "품목", "수량", "단가", "금액", OTHER_HEADER, "비고"]
    for c, h in enumerate(hdr, 1):
        ws.cell(3, c, h)
    d0 = dt.datetime(2021, 3, 1)
    r = 4
    for i in range(6):
        vals = [d0 + dt.timedelta(days=i), CLIENTS[i % 3], "cement", 10 + i, 1000.5, (10 + i) * 1000.5, f"ZZMEMO{i}", None]
        for c, v in enumerate(vals, 1):
            ws.cell(r, c, v)
        r += 1
    r += 1  # blank row
    ws.cell(r, 1, "합계")
    ws.cell(r, 6, 99999)
    ws2 = wb.create_sheet(SHEET_NAMES[1])
    ws2.cell(1, 1, "일자")  # row 1: group labels with client names
    ws2.cell(2, 2, CLIENTS[0])
    ws2.cell(2, 4, CLIENTS[1])
    ws2.cell(3, 1, "일자")
    for c, h in enumerate(["일자", "수량", "금액", "수량", "금액"], 1):
        ws2.cell(3, c, h)
    ws2.cell(1, 1, None)
    for i in range(4):
        vals = [d0 + dt.timedelta(days=i), 5 + i, 100 * i, 7 + i, 200 * i]
        for c, v in enumerate(vals, 1):
            ws2.cell(4 + i, c, v)
    ws2.cell(8, 1, "합계")
    ws2.cell(8, 2, 1)
    wb.save(rev / "dummy_rev_001.xlsx")
    shutil.copyfile(rev / "dummy_rev_001.xlsx", rev / "dummy_rev_002_copy.xlsx")  # byte-identical

    # revenue book C: one driving-layout sheet (skipped) and one unrecognised sheet (quarantined)
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAMES[2]
    ws.cell(1, 1, "ZZTITLE driving")
    for c, h in enumerate(["일자", "1일 주행거리", "누적 주행거리", "연비", "1일 연료소모량"], 1):
        ws.cell(2, c, h)
    for i in range(5):
        vals = [d0 + dt.timedelta(days=i), 200.0 + i, 50000.0 + 200 * i, 3.1, 64.0]
        for c, v in enumerate(vals, 1):
            ws.cell(3 + i, c, v)
    ws3 = wb.create_sheet(SHEET_NAMES[3])
    for i in range(4):
        ws3.cell(1 + i, 1, f"ZZMEMO label {i}")
        ws3.cell(1 + i, 2, i)
    wb.save(rev / "dummy_rev_003.xlsx")

    # revenue book D: merged date, horizontal (matrix) sheet, summary sheet, unmatched sheet
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAMES[0]
    for c, h in enumerate(["일자", "거래처", "수량", "금액"], 1):
        ws.cell(1, c, h)
    qty, amt = [150, 250, 350, 100], [1000, 2000, 3000, 4000]
    for i in range(4):
        ws.cell(2 + i, 2, CLIENTS[i % 3])
        ws.cell(2 + i, 3, qty[i])
        ws.cell(2 + i, 4, amt[i])
    ws.cell(2, 1, d0)
    ws.merge_cells("A2:A4")  # date only in the top cell; rows 2-4 share it
    ws.cell(5, 1, d0 + dt.timedelta(days=1))
    wm = wb.create_sheet(SHEET_NAMES[1])
    wm.cell(1, 1, "ZZTITLE 합계")
    for c, h in enumerate(["거래처", CLIENTS[0], CLIENTS[1], CLIENTS[2], "합계"], 1):
        wm.cell(3, c, h)
    wm.cell(3, 8, 1)  # numeric header cell in the side block
    wm.cell(3, 9, 2)
    for i in range(4):
        wm.cell(4 + 2 * i, 1, d0 + dt.timedelta(days=i))
        wm.cell(4 + 2 * i, 2, 10 + i)
        wm.cell(5 + 2 * i, 3, 20 + i)  # continuation row of the same date
        wm.cell(4 + 2 * i, 4, 0 if i == 0 else 5)
        wm.cell(4 + 2 * i, 8, 0)  # zero outside label columns: dropped
    wsu = wb.create_sheet(SHEET_NAMES[2])
    for i, v in enumerate([850, 10000, 850, 99999]):
        wsu.cell(1 + i, 1, f"ZZMEMO tot {i}")
        wsu.cell(1 + i, 2, v)
    wun = wb.create_sheet(SHEET_NAMES[3])
    for i, v in enumerate([123456, 654321, 111111]):
        wun.cell(1 + i, 1, f"ZZMEMO other {i}")
        wun.cell(1 + i, 2, v)
    _matrix_sheet(wb)
    wb.save(rev / "dummy_rev_004.xlsx")

    # maintenance: text table plus one picture
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAMES[0]
    for c, h in enumerate(["일자", "차량", "정비내용", "정비업체", "비용", "주행거리", OTHER_HEADER], 1):
        ws.cell(2, c, h)
    for i in range(3):
        vals = [d0 + dt.timedelta(days=30 * i), "V-ZZ", "oil change", "ZZSHOP", 120000 + i, 100000 + 5000 * i, "ZZMEMO"]
        for c, v in enumerate(vals, 1):
            ws.cell(3 + i, c, v)
    ws.cell(7, 1, "ZZMEMO free text line")
    png = outdir / "_pic.png"
    Image.new("RGB", (4, 4), (200, 10, 10)).save(png)
    img = XImage(str(png))
    ws.add_image(img, "H3")
    wb.save(mnt / "dummy_mnt_001.xlsx")
    png.unlink()


if __name__ == "__main__":
    make(Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "revenue_dummy")
    print("fixtures written")
