-- 허브(3층) 테이블. PostgreSQL 17. 다시 돌려도 같은 상태가 된다.
DROP SCHEMA IF EXISTS hub CASCADE;
CREATE SCHEMA hub;

CREATE TABLE hub.region (
    region_code text primary key,
    name text not null,
    level text,
    parent_code text references hub.region(region_code)
);
CREATE INDEX ix_region_parent_code ON hub.region (parent_code);
COMMENT ON TABLE hub.region IS '한 행은 지역 하나(법정동코드 단위)';
COMMENT ON COLUMN hub.region.region_code IS '법정동코드(기본키)';
COMMENT ON COLUMN hub.region.name IS '지역 이름';
COMMENT ON COLUMN hub.region.level IS '행정 단계(시도, 시군구 등)';
COMMENT ON COLUMN hub.region.parent_code IS '상위 지역 코드(자기 참조)';

CREATE TABLE hub.vehicle (
    vehicle_id text primary key,
    brand text,
    model text,
    model_year integer,
    color text,
    service_start date,
    service_end date,
    note text
);
COMMENT ON TABLE hub.vehicle IS '한 행은 차량 한 대';
COMMENT ON COLUMN hub.vehicle.vehicle_id IS '뜻 없는 차량 번호(V01 등)';
COMMENT ON COLUMN hub.vehicle.brand IS '브랜드';
COMMENT ON COLUMN hub.vehicle.model IS '모델명';
COMMENT ON COLUMN hub.vehicle.model_year IS '연식';
COMMENT ON COLUMN hub.vehicle.color IS '색';
COMMENT ON COLUMN hub.vehicle.service_start IS '운행 시작일';
COMMENT ON COLUMN hub.vehicle.service_end IS '운행 종료일(운행 중이면 비움)';
COMMENT ON COLUMN hub.vehicle.note IS '비고';

CREATE TABLE hub."user" (
    user_id bigserial primary key,
    name text,
    created_at_kst timestamptz not null default now()
);
COMMENT ON TABLE hub."user" IS '한 행은 앱 사용자 한 명';
COMMENT ON COLUMN hub."user".user_id IS '사용자 번호';
COMMENT ON COLUMN hub."user".name IS '표시 이름';
COMMENT ON COLUMN hub."user".created_at_kst IS '만든 시각(KST)';

CREATE TABLE hub.place (
    place_id bigserial primary key,
    name text not null,
    region_code text references hub.region(region_code),
    lat numeric,
    lon numeric
);
CREATE INDEX ix_place_region_code ON hub.place (region_code);
COMMENT ON TABLE hub.place IS '한 행은 장소 한 곳(상차지, 하차지, 거래처 위치)';
COMMENT ON COLUMN hub.place.place_id IS '장소 번호';
COMMENT ON COLUMN hub.place.name IS '정리된 장소 이름';
COMMENT ON COLUMN hub.place.region_code IS '소속 지역';
COMMENT ON COLUMN hub.place.lat IS '위도';
COMMENT ON COLUMN hub.place.lon IS '경도';

CREATE TABLE hub.place_alias (
    alias text primary key,
    place_id bigint not null references hub.place(place_id)
);
CREATE INDEX ix_place_alias_place_id ON hub.place_alias (place_id);
COMMENT ON TABLE hub.place_alias IS '한 행은 원본에 적힌 장소 이름 하나';
COMMENT ON COLUMN hub.place_alias.alias IS '원본에 적힌 그대로의 이름';
COMMENT ON COLUMN hub.place_alias.place_id IS '정리된 장소';

CREATE TABLE hub.client (
    client_id bigserial primary key,
    name text not null,
    business_no text,
    place_id bigint references hub.place(place_id)
);
CREATE INDEX ix_client_place_id ON hub.client (place_id);
COMMENT ON TABLE hub.client IS '한 행은 정리된 거래처 한 곳';
COMMENT ON COLUMN hub.client.client_id IS '거래처 번호';
COMMENT ON COLUMN hub.client.name IS '정리된 거래처 이름';
COMMENT ON COLUMN hub.client.business_no IS '사업자번호(company_profile 이 채워지면 연결, 지금은 외래키 아님)';
COMMENT ON COLUMN hub.client.place_id IS '거래처 위치';

CREATE TABLE hub.client_alias (
    alias text primary key,
    client_id bigint not null references hub.client(client_id)
);
CREATE INDEX ix_client_alias_client_id ON hub.client_alias (client_id);
COMMENT ON TABLE hub.client_alias IS '한 행은 원본에 적힌 거래처 이름 하나';
COMMENT ON COLUMN hub.client_alias.alias IS '원본에 적힌 그대로의 이름';
COMMENT ON COLUMN hub.client_alias.client_id IS '정리된 거래처';

CREATE TABLE hub.route (
    route_id bigserial primary key,
    origin_place_id bigint not null references hub.place(place_id),
    dest_place_id bigint not null references hub.place(place_id),
    std_round_trip_km numeric,
    station_no integer,
    unique (origin_place_id, dest_place_id)
);
CREATE INDEX ix_route_origin_place_id ON hub.route (origin_place_id);
CREATE INDEX ix_route_dest_place_id ON hub.route (dest_place_id);
COMMENT ON TABLE hub.route IS '한 행은 상차지와 하차지 쌍 하나';
COMMENT ON COLUMN hub.route.route_id IS '구간 번호';
COMMENT ON COLUMN hub.route.origin_place_id IS '상차지';
COMMENT ON COLUMN hub.route.dest_place_id IS '하차지';
COMMENT ON COLUMN hub.route.std_round_trip_km IS '표준 왕복 거리(km)';
COMMENT ON COLUMN hub.route.station_no IS '구간 위 날씨 관측소 번호(관측소 테이블은 아직 없음)';

CREATE TABLE hub.event (
    event_id bigserial primary key,
    event_type text not null,
    name text not null,
    start_date date not null,
    end_date date,
    region_code text references hub.region(region_code)
);
CREATE INDEX ix_event_region_code ON hub.event (region_code);
COMMENT ON TABLE hub.event IS '한 행은 운행에 영향을 주는 사건 하나(행사, 휴일, 공사 등)';
COMMENT ON COLUMN hub.event.event_id IS '사건 번호';
COMMENT ON COLUMN hub.event.event_type IS '사건 종류';
COMMENT ON COLUMN hub.event.name IS '사건 이름';
COMMENT ON COLUMN hub.event.start_date IS '시작일';
COMMENT ON COLUMN hub.event.end_date IS '종료일';
COMMENT ON COLUMN hub.event.region_code IS '영향 범위 지역';

CREATE TABLE hub.product (
    product_id bigserial primary key,
    client_id bigint not null references hub.client(client_id),
    route_id bigint references hub.route(route_id),
    item text,
    price_basis text not null check (price_basis in ('company','invoice')),
    unit text not null default 'ton' check (unit in ('ton')),
    unit_price numeric,
    valid_from date not null,
    valid_to date,
    sheet_supply_amount numeric,
    sheet_vat numeric,
    sheet_total_amount numeric,
    source_file_no integer,
    source_sheet_no integer,
    source_row_no integer
);
CREATE INDEX ix_product_client_id ON hub.product (client_id);
CREATE INDEX ix_product_route_id ON hub.product (route_id);
COMMENT ON TABLE hub.product IS '한 행은 거래처 한 곳의 한 기간, 한 단가 기준의 톤당 단가 하나';
COMMENT ON COLUMN hub.product.product_id IS '단가 번호';
COMMENT ON COLUMN hub.product.client_id IS '거래처';
COMMENT ON COLUMN hub.product.route_id IS '구간(모르면 비움)';
COMMENT ON COLUMN hub.product.item IS '품목(모르면 비움)';
COMMENT ON COLUMN hub.product.price_basis IS '단가 기준(company=회사인정, invoice=발행단가)';
COMMENT ON COLUMN hub.product.unit IS '단가 단위';
COMMENT ON COLUMN hub.product.unit_price IS '단가';
COMMENT ON COLUMN hub.product.valid_from IS '적용 시작일';
COMMENT ON COLUMN hub.product.valid_to IS '적용 종료일';
COMMENT ON COLUMN hub.product.sheet_supply_amount IS '시트에 적힌 그달 공급가액(대사용)';
COMMENT ON COLUMN hub.product.sheet_vat IS '시트에 적힌 그달 부가세(대사용)';
COMMENT ON COLUMN hub.product.sheet_total_amount IS '시트에 적힌 그달 합계 금액(대사용)';
COMMENT ON COLUMN hub.product.source_file_no IS '원본 엑셀 파일 순번';
COMMENT ON COLUMN hub.product.source_sheet_no IS '원본 시트 순번';
COMMENT ON COLUMN hub.product.source_row_no IS '원본 시트 안 행 번호';

CREATE TABLE hub.driving (
    driving_id bigserial primary key,
    vehicle_id text not null references hub.vehicle(vehicle_id),
    date date not null,
    user_id bigint references hub."user"(user_id),
    distance numeric,
    cumulative_distance numeric,
    consumed_fuel numeric,
    fuel_efficiency numeric,
    speed numeric,
    time_h numeric,
    refuel numeric,
    reurea numeric,
    fuel_rate_per_hour numeric,
    consumed_fuel_idle numeric,
    consumed_fuel_pto numeric,
    time_idle_h numeric,
    time_pto_h numeric,
    source_file_no integer,
    source_sheet_no integer,
    source_row_no integer,
    entered_via text not null check (entered_via in ('excel','app')),
    flags jsonb,
    created_at_kst timestamptz not null default now(),
    unique (vehicle_id, date)
);
CREATE INDEX ix_driving_vehicle_id ON hub.driving (vehicle_id);
CREATE INDEX ix_driving_user_id ON hub.driving (user_id);
CREATE INDEX ix_driving_date ON hub.driving (date);
COMMENT ON TABLE hub.driving IS '한 행은 차량 한 대의 하루 계기판 기록';
COMMENT ON COLUMN hub.driving.driving_id IS '운행 기록 번호';
COMMENT ON COLUMN hub.driving.vehicle_id IS '차량';
COMMENT ON COLUMN hub.driving.date IS '운행일';
COMMENT ON COLUMN hub.driving.user_id IS '입력한 사용자(엑셀 적재분은 비움)';
COMMENT ON COLUMN hub.driving.distance IS '하루 주행거리(km)';
COMMENT ON COLUMN hub.driving.cumulative_distance IS '누적 주행거리(km)';
COMMENT ON COLUMN hub.driving.consumed_fuel IS '연료 소모량(L)';
COMMENT ON COLUMN hub.driving.fuel_efficiency IS '연비(km/L)';
COMMENT ON COLUMN hub.driving.speed IS '평균 속도(km/h)';
COMMENT ON COLUMN hub.driving.time_h IS '운행 시간(시간)';
COMMENT ON COLUMN hub.driving.refuel IS '주유량(L)';
COMMENT ON COLUMN hub.driving.reurea IS '요소수 주입량(L)';
COMMENT ON COLUMN hub.driving.fuel_rate_per_hour IS '시간당 연료 소모량(L/h)';
COMMENT ON COLUMN hub.driving.consumed_fuel_idle IS '공회전 연료 소모량(L)';
COMMENT ON COLUMN hub.driving.consumed_fuel_pto IS 'PTO 연료 소모량(L)';
COMMENT ON COLUMN hub.driving.time_idle_h IS '공회전 시간(시간)';
COMMENT ON COLUMN hub.driving.time_pto_h IS 'PTO 시간(시간)';
COMMENT ON COLUMN hub.driving.source_file_no IS '원본 엑셀 파일 순번';
COMMENT ON COLUMN hub.driving.source_sheet_no IS '원본 시트 순번';
COMMENT ON COLUMN hub.driving.source_row_no IS '원본 시트 안 행 번호';
COMMENT ON COLUMN hub.driving.entered_via IS '입력 경로(excel=엑셀 적재, app=앱 입력)';
COMMENT ON COLUMN hub.driving.flags IS '이상값 표시(칸별 사유)';
COMMENT ON COLUMN hub.driving.created_at_kst IS '적재 시각(KST)';

CREATE TABLE hub.driving_correction (
    correction_id bigserial primary key,
    driving_id bigint not null references hub.driving(driving_id),
    column_name text not null,
    original_value text,
    corrected_value text,
    rule text,
    reason text,
    corrected_by text not null check (corrected_by <> ''),
    corrected_at_kst timestamptz not null default now()
);
CREATE INDEX ix_driving_correction_driving_id ON hub.driving_correction (driving_id);
COMMENT ON TABLE hub.driving_correction IS '한 행은 운행 기록의 한 칸을 한 번 고친 일';
COMMENT ON COLUMN hub.driving_correction.correction_id IS '수정 번호';
COMMENT ON COLUMN hub.driving_correction.driving_id IS '고친 운행 기록';
COMMENT ON COLUMN hub.driving_correction.column_name IS '고친 칸 이름';
COMMENT ON COLUMN hub.driving_correction.original_value IS '원본값(지우지 않고 보존)';
COMMENT ON COLUMN hub.driving_correction.corrected_value IS '수정값';
COMMENT ON COLUMN hub.driving_correction.rule IS '적용한 규칙';
COMMENT ON COLUMN hub.driving_correction.reason IS '수정 사유';
COMMENT ON COLUMN hub.driving_correction.corrected_by IS '수정 주체(pipeline, app 또는 사용자 이름)';
COMMENT ON COLUMN hub.driving_correction.corrected_at_kst IS '수정 시각(KST)';

CREATE TABLE hub.delivery (
    delivery_id bigserial primary key,
    date date not null,
    vehicle_id text references hub.vehicle(vehicle_id),
    client_id bigint references hub.client(client_id),
    route_id bigint references hub.route(route_id),
    origin_place_id bigint references hub.place(place_id),
    dest_place_id bigint references hub.place(place_id),
    item text,
    weight_kg numeric,
    trips numeric,
    unit_price numeric,
    supply_amount numeric,
    vat numeric,
    total_amount numeric,
    grain text not null check (grain in ('row','client_day')),
    source_kind text not null check (source_kind in ('table','matrix')),
    source_file_no integer,
    source_sheet_no integer,
    source_row_no integer,
    source_col integer,
    quantity numeric,
    amount numeric,
    note text,
    amount_source text check (amount_source in ('sheet','computed_invoice','computed_company')),
    weight_basis text check (weight_basis in ('kg','ton_x1000','matrix_kg')),
    flags jsonb
);
CREATE INDEX ix_delivery_date ON hub.delivery (date);
CREATE INDEX ix_delivery_vehicle_id ON hub.delivery (vehicle_id);
CREATE INDEX ix_delivery_client_id ON hub.delivery (client_id);
CREATE INDEX ix_delivery_route_id ON hub.delivery (route_id);
CREATE INDEX ix_delivery_origin_place_id ON hub.delivery (origin_place_id);
CREATE INDEX ix_delivery_dest_place_id ON hub.delivery (dest_place_id);
COMMENT ON TABLE hub.delivery IS '한 행은 원본 한 줄 또는 가로형 시트의 거래처×날짜 칸 하나';
COMMENT ON COLUMN hub.delivery.delivery_id IS '운송 번호';
COMMENT ON COLUMN hub.delivery.date IS '운송일';
COMMENT ON COLUMN hub.delivery.vehicle_id IS '차량(모르면 비움)';
COMMENT ON COLUMN hub.delivery.client_id IS '거래처';
COMMENT ON COLUMN hub.delivery.route_id IS '구간';
COMMENT ON COLUMN hub.delivery.origin_place_id IS '상차지';
COMMENT ON COLUMN hub.delivery.dest_place_id IS '하차지';
COMMENT ON COLUMN hub.delivery.item IS '품목';
COMMENT ON COLUMN hub.delivery.weight_kg IS '물량(kg)';
COMMENT ON COLUMN hub.delivery.trips IS '운행 횟수';
COMMENT ON COLUMN hub.delivery.unit_price IS '단가';
COMMENT ON COLUMN hub.delivery.supply_amount IS '공급가액';
COMMENT ON COLUMN hub.delivery.vat IS '부가세';
COMMENT ON COLUMN hub.delivery.total_amount IS '합계 금액';
COMMENT ON COLUMN hub.delivery.grain IS '행 단위(row=원본 한 줄, client_day=가로형 거래처×날짜 칸)';
COMMENT ON COLUMN hub.delivery.source_kind IS '원본 양식(table=세로 표, matrix=가로형 시트)';
COMMENT ON COLUMN hub.delivery.source_file_no IS '원본 엑셀 파일 순번';
COMMENT ON COLUMN hub.delivery.source_sheet_no IS '원본 시트 순번';
COMMENT ON COLUMN hub.delivery.source_row_no IS '원본 시트 안 행 번호';
COMMENT ON COLUMN hub.delivery.source_col IS '원본 시트 안 열 번호(가로형 칸일 때)';
COMMENT ON COLUMN hub.delivery.quantity IS '원본에 적힌 수량';
COMMENT ON COLUMN hub.delivery.amount IS '원본에 적힌 금액 칸(공급가액과 별개)';
COMMENT ON COLUMN hub.delivery.note IS '원본 비고';
COMMENT ON COLUMN hub.delivery.amount_source IS '공급가액의 출처(sheet=시트에 적힌 값, computed_invoice=물량×발행단가로 계산, computed_company=발행단가가 없는 달에 물량×회사인정단가로 계산, 비움=공급가액 없음)';
COMMENT ON COLUMN hub.delivery.weight_basis IS '물량 환산 근거(kg=원본이 킬로그램, ton_x1000=톤×1000, matrix_kg=가로형 킬로그램, 비움=물량 없음)';
COMMENT ON COLUMN hub.delivery.flags IS '이상 표시(예: weight_unit_ambiguous=톤인지 킬로그램인지 구분 불가)';

CREATE TABLE hub.maintenance (
    maintenance_id bigserial primary key,
    date date,
    vehicle_id text references hub.vehicle(vehicle_id),
    item text,
    shop text,
    quantity numeric,
    unit_price numeric,
    cost numeric,
    odometer_km numeric,
    note text,
    source_file_no integer,
    source_sheet_no integer,
    source_row_no integer
);
CREATE INDEX ix_maintenance_date ON hub.maintenance (date);
CREATE INDEX ix_maintenance_vehicle_id ON hub.maintenance (vehicle_id);
COMMENT ON TABLE hub.maintenance IS '한 행은 정비 내역 한 줄';
COMMENT ON COLUMN hub.maintenance.maintenance_id IS '정비 번호';
COMMENT ON COLUMN hub.maintenance.date IS '정비일(원본에 날짜가 없으면 비움)';
COMMENT ON COLUMN hub.maintenance.vehicle_id IS '차량(모르면 비움)';
COMMENT ON COLUMN hub.maintenance.item IS '정비 항목';
COMMENT ON COLUMN hub.maintenance.shop IS '정비소';
COMMENT ON COLUMN hub.maintenance.quantity IS '수량';
COMMENT ON COLUMN hub.maintenance.unit_price IS '단가';
COMMENT ON COLUMN hub.maintenance.cost IS '비용';
COMMENT ON COLUMN hub.maintenance.odometer_km IS '정비 때 계기판 거리(km)';
COMMENT ON COLUMN hub.maintenance.note IS '비고';
COMMENT ON COLUMN hub.maintenance.source_file_no IS '원본 엑셀 파일 순번';
COMMENT ON COLUMN hub.maintenance.source_sheet_no IS '원본 시트 순번';
COMMENT ON COLUMN hub.maintenance.source_row_no IS '원본 시트 안 행 번호';

CREATE TABLE hub.fueling (
    fueling_id bigserial primary key,
    fueled_at_kst timestamptz not null,
    vehicle_id text not null references hub.vehicle(vehicle_id),
    liters numeric,
    unit_price numeric,
    amount numeric,
    is_urea boolean not null default false
);
CREATE INDEX ix_fueling_vehicle_id ON hub.fueling (vehicle_id);
CREATE INDEX ix_fueling_fueled_at_kst ON hub.fueling (fueled_at_kst);
COMMENT ON TABLE hub.fueling IS '한 행은 주유 한 번';
COMMENT ON COLUMN hub.fueling.fueling_id IS '주유 번호';
COMMENT ON COLUMN hub.fueling.fueled_at_kst IS '주유 시각(KST)';
COMMENT ON COLUMN hub.fueling.vehicle_id IS '차량';
COMMENT ON COLUMN hub.fueling.liters IS '주유량(L)';
COMMENT ON COLUMN hub.fueling.unit_price IS '리터당 단가';
COMMENT ON COLUMN hub.fueling.amount IS '금액';
COMMENT ON COLUMN hub.fueling.is_urea IS '요소수 여부';

CREATE TABLE hub.fuel_price (
    date date not null,
    region_code text not null references hub.region(region_code),
    avg_diesel_price numeric,
    primary key (date, region_code)
);
CREATE INDEX ix_fuel_price_region_code ON hub.fuel_price (region_code);
COMMENT ON TABLE hub.fuel_price IS '한 행은 하루, 한 지역의 경유 평균가';
COMMENT ON COLUMN hub.fuel_price.date IS '날짜';
COMMENT ON COLUMN hub.fuel_price.region_code IS '지역';
COMMENT ON COLUMN hub.fuel_price.avg_diesel_price IS '경유 평균가(원/L)';

CREATE TABLE hub.company_profile (
    business_no text primary key,
    corp_reg_no text,
    ceo text,
    address text,
    industry text,
    listed boolean,
    employees integer,
    founded date
);
COMMENT ON TABLE hub.company_profile IS '한 행은 기업 한 곳';
COMMENT ON COLUMN hub.company_profile.business_no IS '사업자번호';
COMMENT ON COLUMN hub.company_profile.corp_reg_no IS '법인등록번호';
COMMENT ON COLUMN hub.company_profile.ceo IS '대표자';
COMMENT ON COLUMN hub.company_profile.address IS '주소';
COMMENT ON COLUMN hub.company_profile.industry IS '업종';
COMMENT ON COLUMN hub.company_profile.listed IS '상장 여부';
COMMENT ON COLUMN hub.company_profile.employees IS '직원 수';
COMMENT ON COLUMN hub.company_profile.founded IS '설립일';

CREATE TABLE hub.company_financial (
    business_no text not null references hub.company_profile(business_no),
    year integer not null,
    revenue numeric,
    operating_profit numeric,
    debt_ratio numeric,
    primary key (business_no, year)
);
COMMENT ON TABLE hub.company_financial IS '한 행은 기업 한 곳의 한 해 재무';
COMMENT ON COLUMN hub.company_financial.business_no IS '사업자번호';
COMMENT ON COLUMN hub.company_financial.year IS '연도';
COMMENT ON COLUMN hub.company_financial.revenue IS '매출액';
COMMENT ON COLUMN hub.company_financial.operating_profit IS '영업이익';
COMMENT ON COLUMN hub.company_financial.debt_ratio IS '부채비율(%)';

CREATE TABLE hub.quarantine (
    quarantine_id bigserial primary key,
    target_table text not null,
    reason text not null,
    source_file_no integer,
    source_sheet_no integer,
    source_row_no integer,
    payload jsonb,
    created_at_kst timestamptz not null default now()
);
CREATE INDEX ix_quarantine_target_table ON hub.quarantine (target_table);
COMMENT ON TABLE hub.quarantine IS '한 행은 적재 계약을 어겨 표준 테이블에 못 들어간 원본 한 줄';
COMMENT ON COLUMN hub.quarantine.quarantine_id IS '격리 번호';
COMMENT ON COLUMN hub.quarantine.target_table IS '들어가려던 표준 테이블 이름';
COMMENT ON COLUMN hub.quarantine.reason IS '격리 사유';
COMMENT ON COLUMN hub.quarantine.source_file_no IS '원본 엑셀 파일 순번';
COMMENT ON COLUMN hub.quarantine.source_sheet_no IS '원본 시트 순번';
COMMENT ON COLUMN hub.quarantine.source_row_no IS '원본 시트 안 행 번호';
COMMENT ON COLUMN hub.quarantine.payload IS '원본 행 내용';
COMMENT ON COLUMN hub.quarantine.created_at_kst IS '격리 시각(KST)';

CREATE UNIQUE INDEX ux_product_period ON hub.product (client_id, route_id, item, price_basis, valid_from) NULLS NOT DISTINCT;
