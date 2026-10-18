# 실제 구간에 오류를 심은 점수 (합의 문서 3절 3단계)

실제 데이터에서 모든 관계식을 통과하고 수정하지 않은 연속 구간(10행 이상) 2개, 행 1418개를 잘라 같은 오류 주입기로 오류 116칸을 심고 같은 알고리즘(typo kinds ['drop', 'insert', 'replace', 'transpose'], min-cell pass off, 고정 규칙 켬)으로 채점했습니다. 허용 오차는 이 데이터에서 추정한 표시 단위의 합입니다. 값은 이 문서에 없습니다.

| error type | injected cells | caught (TP) | missed (FN) | false alarms (FP) | recall | precision | F1 | repair precision | missed but in unresolved |
|---|---|---|---|---|---|---|---|---|---|
| adjacent_key | 27 | 26 | 1 | 1 | 0.963 | 0.963 | 0.963 | 0.963 | 0 |
| copy_previous | 15 | 14 | 1 | 0 | 0.933 | 1.000 | 0.966 | 1.000 | 0 |
| date_abnormal | 16 | 16 | 0 | 0 | 1.000 | 1.000 | 1.000 | 1.000 | 0 |
| digit_drop | 28 | 24 | 4 | 0 | 0.857 | 1.000 | 0.923 | 1.000 | 0 |
| transpose | 12 | 11 | 1 | 0 | 0.917 | 1.000 | 0.957 | 1.000 | 0 |
| two_cells | 18 | 10 | 8 | 1 | 0.556 | 0.909 | 0.690 | 0.909 | 4 |
| (no nearby injected error) | 0 | 0 | 0 | 0 | - | - | - | - | 0 |
| **all** | 116 | 101 | 15 | 2 | 0.871 | 0.981 | 0.922 | 0.981 | |

Sound cells changed (false alarms / sound cells): 2 / 4138 = 0.048% (limit 0.5%).

주의: 더미와 같은 주입기를 쓰므로 실제 오타 분포와는 다를 수 있습니다. 구간 사이는 날짜가 끊겨 부등식만 검사됩니다.
