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
SECRET_STRINGS = CLIENTS + SHEET_NAMES + [OTHER_HEADER, "ZZSHOP", "ZZMEMO"]

# truth: rows expected per sheet of the revenue book A
TRUTH = {"A_sheet1": {"loaded": 6, "blank": 1, "total": 1, "header": 3, "quarantined": 0},
         "A_sheet2": {"loaded": 4, "blank": 0, "total": 1, "header": 3, "quarantined": 0}}


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
