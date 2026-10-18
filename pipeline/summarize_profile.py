"""Summarize revenue and maintenance structure from pipeline/profiles/raw_profile.json into reports/revenue_maintenance_profile.md.

Counts only: no sheet names, no cell text, no client names.
"""
from __future__ import annotations

import io
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import load_config, path_from, write_text  # noqa: E402

TYPE_KO = {"N": "숫자", "S": "글자", "D": "날짜", "B": "빈칸", "O": "기타"}


def dominant(ct: dict) -> str:
    nb = {k: v for k, v in ct.items() if k != "B"}
    return max(nb, key=nb.get) if nb else "B"


def summarize(kind: str, p: dict) -> list:
    L = [f"## {kind}", ""]
    files = p["file_list"]
    sheets = [(f["file"], s) for f in files for s in f["sheets"]]
    per_file = Counter(len(f["sheets"]) for f in files)
    L += [f"- 파일 {p['files']}개, 시트 {len(sheets)}개, 읽기 실패 {sum(p['problems'].values()) if p['problems'] else 0}개",
          "- 파일당 시트 수 분포: " + ", ".join(f"{k}개짜리 {v}파일" for k, v in sorted(per_file.items()))]
    rows = np.array([s["max_row"] or 0 for _, s in sheets])
    cols = np.array([s["max_col"] or 0 for _, s in sheets])
    if len(rows):
        L += [f"- 시트당 사용 행 수: 중앙값 {int(np.median(rows))}, 최소 {int(rows.min())}, 최대 {int(rows.max())}",
              f"- 시트당 사용 열 수: 중앙값 {int(np.median(cols))}, 최소 {int(cols.min())}, 최대 {int(cols.max())}"]
    merged = np.array([s["n_merged"] for _, s in sheets])
    pics = [len(s["pictures"]) if isinstance(s["pictures"], list) else -1 for _, s in sheets]
    L += [f"- 셀 병합이 있는 시트 {int((merged > 0).sum())}개 (병합 범위 합계 {int(merged.sum())}개, 시트당 최대 {int(merged.max()) if len(merged) else 0}개)",
          f"- 사진이 있는 시트 {sum(1 for x in pics if x > 0)}개 (사진 합계 {sum(x for x in pics if x > 0)}개), 사진 위치를 못 읽은 시트 {sum(1 for x in pics if x < 0)}개", ""]
    fam = Counter()
    ex = {}
    for fno, s in sheets:
        sig = "".join(dominant(c) for c in s["column_types"][:30])
        sig = sig.rstrip("B")
        fam[sig] += 1
        ex.setdefault(sig, (fno, s["sheet"]))
    L += [f"열 종류 서명(열마다 가장 많은 칸 종류, N 숫자 S 글자 D 날짜 B 빈칸)이 같은 시트끼리 묶으면 {len(fam)}가지입니다. 상위 10:", "",
          "| 서명 | 시트 수 | 예시(파일 순번, 시트 순번) |", "|---|---|---|"]
    for sig, n in fam.most_common(10):
        L.append(f"| `{sig}` | {n} | {ex[sig][0]}, {ex[sig][1]} |")
    # decimals of numeric columns
    dec = Counter()
    for _, s in sheets:
        for c in s["numeric_decimals_by_column"]:
            for k, v in c.items():
                dec[k] += v
    tot = sum(dec.values())
    if tot:
        L += ["", "숫자 칸의 소수 자릿수 분포(허용 오차 근거, 전체 칸 기준): " + ", ".join(f"{k}자리 {v}개 ({v / tot:.1%})" for k, v in sorted(dec.items())), ""]
    # top rows pattern
    firsts = Counter()
    for _, s in sheets:
        g = s["type_grid_first_rows_rle"]
        firsts[len(g)] += 1
    L += [f"위쪽 30행의 행 모양 변화 횟수(같은 모양이 이어지면 한 번으로 셈) 분포: " + ", ".join(f"{k}번 {v}시트" for k, v in sorted(firsts.items())[:12]), ""]
    return L


def main() -> int:
    cfg = load_config()
    prof = json.load(io.open(path_from(cfg, "profile_dir") / "raw_profile.json", encoding="utf-8"))
    L = ["# 매출, 정비 구조 요약", "",
         "`pipeline/profile_raw.py` 결과를 건수로만 줄인 문서입니다. 시트 이름, 셀 글자, 거래처 이름은 없습니다. 파서는 다음 단계입니다. 원본은 `profiles/raw_profile.json` 에 시트별 병합 범위, 사진 위치, 열 종류, 위쪽 30행의 칸 종류 격자가 있습니다.", ""]
    for kind in ("revenue", "maintenance"):
        if "file_list" in prof.get(kind, {}):
            L += summarize(kind, prof[kind])
        else:
            L += [f"## {kind}", "", "폴더를 못 찾았습니다.", ""]
    write_text(path_from(cfg, "reports_dir") / "revenue_maintenance_profile.md", "\n".join(L))
    print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
