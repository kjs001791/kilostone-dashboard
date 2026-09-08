"""
Excel 파일 구조 분석 스크립트
- 실제 데이터 값은 출력하지 않음
- 시트명, 컬럼명, 헤더 위치만 분석
- 결과를 data/staging/schema_analysis.md 로 저장
"""

import sys
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "staging" / "schema_analysis.md"

HEADER_KEYWORDS = ['날짜', '일자', 'date']


def detect_header_row(df_raw):
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x) for x in row.values if str(x) != 'nan'])
        if any(kw in row_str for kw in HEADER_KEYWORDS):
            return i
    return None


def analyze_sheet(file_path, sheet_name):
    try:
        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, nrows=30)
    except Exception as e:
        return {"error": str(e)}

    top_text = []
    for i in range(min(3, len(df_raw))):
        for val in df_raw.iloc[i].values:
            s = str(val).strip()
            if s and s != 'nan' and len(s) < 30:
                top_text.append(s)

    header_idx = detect_header_row(df_raw)

    if header_idx is None:
        return {
            "header_found": False,
            "top_cells": top_text[:5],
        }

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx, nrows=3)
    columns = [str(c).strip() for c in df.columns if str(c) != 'nan']

    # 헤더 위 행들 캡처 (다중 헤더 구조 파악용)
    rows_above = {}
    for offset in range(1, min(4, header_idx + 1)):
        row_idx = header_idx - offset
        row_vals = [str(v).strip() for v in df_raw.iloc[row_idx].values if str(v).strip() not in ('', 'nan')]
        if row_vals:
            rows_above[f"row_{row_idx}"] = row_vals

    df_full = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)
    data_rows = len(df_full.dropna(how='all'))

    return {
        "header_found": True,
        "header_row": header_idx,
        "top_cells": top_text[:5],
        "rows_above_header": rows_above,
        "columns": columns,
        "column_count": len(columns),
        "data_rows": data_rows,
    }


def analyze_file(file_path):
    path = Path(file_path)
    lines = []
    lines.append(f"\n## {path.name}\n")

    try:
        xls = pd.ExcelFile(path)
    except Exception as e:
        lines.append(f"- 파일 열기 실패: {e}\n")
        return lines

    for sheet in xls.sheet_names:
        lines.append(f"\n### 시트: `{sheet}`\n")
        result = analyze_sheet(path, sheet)

        if "error" in result:
            lines.append(f"- 오류: {result['error']}\n")
            continue

        if not result["header_found"]:
            lines.append(f"- 날짜 헤더 미발견 (운행기록 시트 아닐 수 있음)\n")
            lines.append(f"- 상단 셀 힌트: `{result['top_cells']}`\n")
            continue

        lines.append(f"- 헤더 위치: {result['header_row']}행\n")
        lines.append(f"- 상단 힌트: `{result['top_cells']}`\n")
        if result.get("rows_above_header"):
            lines.append(f"- 헤더 위 행 내용 (다중헤더 구조):\n")
            for row_key, row_vals in result["rows_above_header"].items():
                lines.append(f"  - `{row_key}`: `{row_vals}`\n")
        lines.append(f"- 데이터 행수: {result['data_rows']}행\n")
        lines.append(f"- 컬럼 {result['column_count']}개 (헤더행 기준):\n")
        for col in result["columns"]:
            lines.append(f"  - `{col}`\n")

    return lines


def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/analyze_schema.py <파일경로 또는 폴더경로>")
        print("예시:")
        print("  python scripts/analyze_schema.py data/raw/2024_01.xlsx")
        print("  python scripts/analyze_schema.py data/raw/")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_dir():
        files = sorted(target.glob("*.xlsx")) + sorted(target.glob("*.xls"))
        if not files:
            print(f"❌ {target} 에 Excel 파일 없음")
            sys.exit(1)
        print(f"📂 {len(files)}개 파일 분석 중...")
        all_lines = [f"# Schema Analysis\n\n생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
        all_lines.append(f"대상 폴더: `{target}`  |  파일 수: {len(files)}\n")
        for f in files:
            print(f"  분석 중: {f.name}")
            all_lines.extend(analyze_file(f))
    elif target.is_file():
        print(f"파일 분석 중: {target.name}")
        all_lines = [f"# Schema Analysis\n\n생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
        all_lines.extend(analyze_file(target))
    else:
        print(f"❌ 경로 없음: {target}")
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("".join(all_lines), encoding="utf-8")

    print(f"\n✅ 분석 완료 → {OUTPUT_PATH}")
    print("이 파일을 Claude에게 붙여넣으세요.\n")


if __name__ == "__main__":
    main()
