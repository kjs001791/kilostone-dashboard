# 실제 구간에 오류를 심은 점수 (합의 문서 3절 3단계)

실제 데이터에서 모든 관계식을 통과하고 수정하지 않은 연속 구간(10행 이상) 3개, 행 1418개를 잘라 같은 오류 주입기로 오류 120칸을 심고 같은 알고리즘(typo kinds ['drop', 'insert', 'replace', 'transpose'], min-cell pass off, 고정 규칙 켬)으로 채점했습니다. 허용 오차는 이 데이터에서 추정한 표시 단위의 합입니다. 값은 이 문서에 없습니다.

| error type | injected cells | caught (TP) | missed (FN) | false alarms (FP) | recall | precision | F1 | repair precision | missed but in unresolved |
|---|---|---|---|---|---|---|---|---|---|
| adjacent_key | 27 | 25 | 2 | 1 | 0.926 | 0.962 | 0.943 | 0.962 | 0 |
| copy_previous | 15 | 13 | 2 | 0 | 0.867 | 1.000 | 0.929 | 1.000 | 0 |
| date_abnormal | 16 | 16 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 0 |
| digit_drop | 30 | 24 | 6 | 0 | 0.800 | 1.000 | 0.889 | 1.000 | 0 |
| transpose | 12 | 11 | 1 | 0 | 0.917 | 1.000 | 0.957 | 1.000 | 0 |
| two_cells | 20 | 19 | 1 | 0 | 0.950 | 1.000 | 0.974 | 1.000 | 0 |
| (no nearby injected error) | 0 | 0 | 0 | 0 | - | - | - | - | 0 |
| **all** | 120 | 108 | 12 | 1 | 0.900 | 0.991 | 0.943 | 0.991 | |

Sound cells changed (false alarms / sound cells): 1 / 4134 = 0.024% (limit 0.5%).

주의: 더미와 같은 주입기를 쓰므로 실제 오타 분포와는 다를 수 있습니다. 구간 사이는 날짜가 끊겨 부등식만 검사됩니다.
