# 허브(3층) 테이블

- 파일: `db/schema.sql` (PostgreSQL 17, 스키마 `hub`)
- 다시 실행해도 같은 상태 (맨 위 `DROP SCHEMA ... CASCADE` 후 재생성)
- 예약어 `user` 는 `"user"` 로 생성
- 날짜 칸은 `date`, 앱 저장 시각은 `timestamptz` 에 이름 끝 `_kst`
- 금액과 계기판 숫자는 `numeric`

| 테이블 | 한 행 | 기본키 | 외래키 |
| --- | --- | --- | --- |
| region | 지역 하나(법정동코드 단위) | region_code | parent_code -> region |
| vehicle | 차량 한 대 | vehicle_id | - |
| user | 앱 사용자 한 명 | user_id | - |
| place | 장소 한 곳(상차지, 하차지, 거래처 위치) | place_id | region_code -> region |
| place_alias | 원본에 적힌 장소 이름 하나 | alias | place_id -> place |
| client | 정리된 거래처 한 곳 | client_id | place_id -> place |
| client_alias | 원본에 적힌 거래처 이름 하나 | alias | client_id -> client |
| route | 상차지와 하차지 쌍 하나 | route_id | origin_place_id -> place, dest_place_id -> place |
| event | 운행에 영향을 주는 사건 하나(행사, 휴일, 공사 등) | event_id | region_code -> region |
| product | 거래처 한 곳의 한 기간, 한 단가 기준의 톤당 단가 하나 | product_id | client_id -> client, route_id -> route |
| driving | 차량 한 대의 하루 계기판 기록 | driving_id | vehicle_id -> vehicle, user_id -> user |
| driving_correction | 운행 기록의 한 칸을 한 번 고친 일 | correction_id | driving_id -> driving |
| delivery | 원본 한 줄 또는 가로형 시트의 거래처×날짜 칸 하나 | delivery_id | vehicle_id -> vehicle, client_id -> client, route_id -> route, origin_place_id -> place, dest_place_id -> place |
| maintenance | 정비 내역 한 줄 | maintenance_id | vehicle_id -> vehicle |
| fueling | 주유 한 번 | fueling_id | vehicle_id -> vehicle |
| fuel_price | 하루, 한 지역의 경유 평균가 | (date, region_code) | region_code -> region |
| company_profile | 기업 한 곳 | business_no | - |
| company_financial | 기업 한 곳의 한 해 재무 | (business_no, year) | business_no -> company_profile |
| quarantine | 적재 계약을 어겨 표준 테이블에 못 들어간 원본 한 줄 | quarantine_id | - |

## 제약 메모

- driving: 유일 (vehicle_id, date)
- route: 유일 (origin_place_id, dest_place_id)
- product: 유일 (client_id, route_id, item, price_basis, valid_from), 빈 값끼리도 같은 값으로 취급
- 모든 외래키 칸에 인덱스, delivery(date)와 driving(date) 인덱스 포함
- 만들지 않은 테이블: weather, station (route.station_no 는 외래키 없는 숫자 칸)
- client.business_no: company_profile 이 채워질 때까지 외래키 아님
- delivery: 공급가액 출처 `amount_source`(sheet, computed_invoice), 물량 환산 근거 `weight_basis`(kg, ton_x1000, matrix_kg), 이상 표시 `flags`(jsonb), 원본 수량·금액·비고(`quantity`, `amount`, `note`) 보존
- maintenance: 원본에 날짜가 없는 줄을 받기 위해 `date` 비움 허용
