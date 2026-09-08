# Phase 3 — Next.js 프론트엔드 구현 설계서

> 이 문서는 구현 담당자(Gemini)를 위한 상세 명세서입니다.
> Phase 2 (FastAPI) 완료 후 진행합니다. 설계 결정은 확정되었으며 임의로 변경하지 마세요.

---

## 0. 전제 조건 및 금지사항

**반드시 지킬 것:**
- 프레임워크: **Next.js 14 (App Router)**, TypeScript 필수
- UI: **Tailwind CSS + shadcn/ui** — 다른 CSS 프레임워크 혼용 금지
- 차트: **Recharts** — Plotly, Chart.js 사용 금지
- 폼 상태관리: **react-hook-form + zod** — 다른 폼 라이브러리 금지
- access_token은 **메모리(React Context)에만 저장** — localStorage, sessionStorage, 쿠키 저장 금지
- refresh_token은 httpOnly 쿠키로 자동 전달됨 (프론트에서 직접 다루지 않음)
- API 호출은 반드시 `src/lib/api.ts`의 래퍼 함수를 통해서만 수행
- `NEXT_PUBLIC_API_URL` 환경변수로 API 주소 관리 — 하드코딩 금지

---

## 1. 설치 패키지

```bash
# Next.js 프로젝트 생성 (frontend/ 디렉토리)
npx create-next-app@14 frontend --typescript --tailwind --app --src-dir --import-alias "@/*"

# 이동
cd frontend

# shadcn/ui 초기화
npx shadcn-ui@latest init
# → Style: Default, Base color: Zinc, CSS variables: Yes

# shadcn/ui 컴포넌트 설치
npx shadcn-ui@latest add button card input label select table badge separator dialog toast skeleton form

# 추가 패키지
npm install recharts date-fns react-hook-form @hookform/resolvers zod lucide-react
```

**최종 핵심 의존성:**
```json
{
  "next": "^14.2.0",
  "react": "^18.3.0",
  "react-dom": "^18.3.0",
  "recharts": "^2.12.0",
  "date-fns": "^3.6.0",
  "react-hook-form": "^7.52.0",
  "@hookform/resolvers": "^3.6.0",
  "zod": "^3.23.0",
  "lucide-react": "^0.400.0"
}
```

---

## 2. 환경변수 (`.env.local`)

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

프로덕션 docker-compose에서는 `/api` (Nginx 경로 프록시)로 설정:
```yaml
environment:
  NEXT_PUBLIC_API_URL: /api
```

---

## 3. 디렉토리 구조

```
frontend/
├── Dockerfile
├── next.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── components.json          # shadcn/ui 설정 파일
├── .env.local
└── src/
    ├── app/
    │   ├── layout.tsx         # 루트 레이아웃 (AuthProvider 포함)
    │   ├── page.tsx           # / → /dashboard 리다이렉트
    │   ├── login/
    │   │   └── page.tsx
    │   ├── dashboard/
    │   │   └── page.tsx
    │   ├── logs/
    │   │   ├── page.tsx       # 기록 목록 + 필터
    │   │   ├── new/
    │   │   │   └── page.tsx
    │   │   └── [id]/
    │   │       └── edit/
    │   │           └── page.tsx
    │   └── vehicles/
    │       └── page.tsx
    ├── components/
    │   ├── ui/                # shadcn/ui 자동 생성 (수정 금지)
    │   ├── layout/
    │   │   ├── AppShell.tsx
    │   │   └── MobileNav.tsx
    │   ├── dashboard/
    │   │   ├── KpiCard.tsx
    │   │   ├── EfficiencyChart.tsx
    │   │   ├── DistanceChart.tsx
    │   │   ├── FuelChart.tsx
    │   │   └── CorrelationChart.tsx
    │   ├── logs/
    │   │   ├── LogTable.tsx
    │   │   ├── LogFilters.tsx
    │   │   └── LogForm.tsx
    │   └── vehicles/
    │       └── VehicleCompareCharts.tsx
    ├── contexts/
    │   └── AuthContext.tsx
    ├── lib/
    │   ├── api.ts
    │   └── utils.ts           # shadcn/ui의 cn() 함수 (자동 생성)
    └── types/
        ├── log.ts
        └── stats.ts
```

---

## 4. TypeScript 타입 정의

### `src/types/log.ts`

```typescript
export interface DrivingLog {
  id: number;
  date: string;                        // "YYYY-MM-DD"
  vehicle_id: string;
  distance: number;
  cumulative_distance: number | null;
  speed: number | null;
  time: string | null;                 // "HH:MM"
  time_idle: string | null;
  time_pto: string | null;
  fuel_efficiency: number | null;
  fuel_rate_per_hour: number | null;
  consumed_fuel: number | null;
  consumed_fuel_idle: number | null;
  consumed_fuel_pto: number | null;
  refuel: number | null;
  reurea: number | null;
  source: "pipeline" | "manual";
  created_at: string;
}

export interface LogsPage {
  total: number;
  page: number;
  per_page: number;
  items: DrivingLog[];
}

export interface LogCreatePayload {
  date: string;
  vehicle_id: string;
  distance: number;
  cumulative_distance?: number;
  speed?: number;
  time?: string;
  time_idle?: string;
  time_pto?: string;
  fuel_efficiency?: number;
  fuel_rate_per_hour?: number;
  consumed_fuel?: number;
  consumed_fuel_idle?: number;
  consumed_fuel_pto?: number;
  refuel?: number;
  reurea?: number;
}

export type LogUpdatePayload = Partial<LogCreatePayload>;

// 차량 목록 (확정)
export const VEHICLE_OPTIONS = [
  { value: "MAN TGX", label: "MAN TGX" },
  { value: "Daewoo Prima", label: "대우 프리마" },
  { value: "Scania", label: "스카니아" },
] as const;

export type VehicleId = typeof VEHICLE_OPTIONS[number]["value"];

// 스카니아 전용 필드 여부 판별
export const isScania = (vehicleId: string) => vehicleId === "Scania";
```

### `src/types/stats.ts`

```typescript
export interface StatsSummary {
  total_distance: number;
  avg_fuel_efficiency: number | null;
  total_consumed_fuel: number | null;
  total_records: number;
}

export interface MonthlyStats {
  year: number;
  month: number;
  total_distance: number;
  avg_fuel_efficiency: number | null;
  total_consumed_fuel: number | null;
  record_count: number;
}

export interface StatsResponse {
  summary: StatsSummary;
  monthly: MonthlyStats[];
}
```

---

## 5. 파일별 구현 명세

### 5-1. `src/lib/api.ts`

모든 API 호출의 단일 진입점. 자동 토큰 갱신 포함.

```typescript
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// 메모리에 저장되는 access_token (모듈 스코프)
// AuthContext에서 관리하므로 여기서는 setter/getter만 제공
let _accessToken: string | null = null;

export const tokenStore = {
  get: () => _accessToken,
  set: (token: string | null) => { _accessToken = token; },
};

async function refreshAccessToken(): Promise<string | null> {
  const res = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",   // httpOnly 쿠키 자동 전송
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.access_token ?? null;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = tokenStore.get();

  const makeRequest = (accessToken: string | null) =>
    fetch(`${BASE_URL}${path}`, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(options.headers ?? {}),
      },
    });

  let res = await makeRequest(token);

  // 401 → refresh 시도 → 1회 재시도
  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      tokenStore.set(newToken);
      res = await makeRequest(newToken);
    } else {
      // refresh도 실패 → 로그인 페이지로
      tokenStore.set(null);
      window.location.href = "/login";
      throw new Error("인증이 만료되었습니다.");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "API 오류");
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json();
}

// ---- 엔드포인트별 함수 ----

export const authApi = {
  login: (username: string, password: string) =>
    apiFetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    apiFetch<void>("/auth/logout", { method: "POST" }),
};

export const logsApi = {
  list: (params: {
    page?: number;
    per_page?: number;
    vehicle_id?: string;
    date_from?: string;
    date_to?: string;
  }) => {
    const qs = new URLSearchParams(
      Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)])
    ).toString();
    return apiFetch<import("@/types/log").LogsPage>(`/logs${qs ? `?${qs}` : ""}`);
  },
  create: (payload: import("@/types/log").LogCreatePayload) =>
    apiFetch<import("@/types/log").DrivingLog>("/logs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  update: (id: number, payload: import("@/types/log").LogUpdatePayload) =>
    apiFetch<import("@/types/log").DrivingLog>(`/logs/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  delete: (id: number) =>
    apiFetch<void>(`/logs/${id}`, { method: "DELETE" }),
};

export const statsApi = {
  get: (params?: { vehicle_id?: string; year?: number }) => {
    const qs = params
      ? new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)])
        ).toString()
      : "";
    return apiFetch<import("@/types/stats").StatsResponse>(`/stats${qs ? `?${qs}` : ""}`);
  },
};
```

---

### 5-2. `src/contexts/AuthContext.tsx`

```typescript
"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { tokenStore, authApi } from "@/lib/api";
import { useRouter } from "next/navigation";

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  // 앱 최초 로드 시 refresh 시도 (쿠키가 있으면 자동 복구)
  useEffect(() => {
    import("@/lib/api").then(({ apiFetch, tokenStore }) =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      })
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (data?.access_token) {
            tokenStore.set(data.access_token);
            setIsAuthenticated(true);
          }
        })
        .finally(() => setIsLoading(false))
    );
  }, []);

  const login = async (username: string, password: string) => {
    const { access_token } = await authApi.login(username, password);
    tokenStore.set(access_token);
    setIsAuthenticated(true);
    router.push("/dashboard");
  };

  const logout = async () => {
    await authApi.logout();
    tokenStore.set(null);
    setIsAuthenticated(false);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
```

---

### 5-3. `src/app/layout.tsx`

```typescript
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/toaster";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "KiloStone Dashboard",
  description: "화물트럭 운행 관리 시스템",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className="dark">
      <body className={inter.className}>
        <AuthProvider>
          {children}
          <Toaster />
        </AuthProvider>
      </body>
    </html>
  );
}
```

---

### 5-4. `src/app/login/page.tsx`

```typescript
"use client";

import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
    } catch (err: any) {
      setError(err.message ?? "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-center text-2xl">KiloStone</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="username">아이디</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">비밀번호</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "로그인 중..." : "로그인"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

---

### 5-5. `src/components/layout/AppShell.tsx`

인증된 페이지 공통 레이아웃. 데스크탑: 좌측 사이드바, 모바일: 하단 탭 바.

```typescript
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { LayoutDashboard, ClipboardList, PlusCircle, Truck, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "대시보드", icon: LayoutDashboard },
  { href: "/logs", label: "기록 조회", icon: ClipboardList },
  { href: "/logs/new", label: "기록 추가", icon: PlusCircle },
  { href: "/vehicles", label: "차량 비교", icon: Truck },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <div className="min-h-screen bg-background">
      {/* 데스크탑 사이드바 */}
      <aside className="hidden md:flex flex-col fixed left-0 top-0 h-full w-56 border-r border-border bg-card p-4 gap-2">
        <div className="text-lg font-bold mb-4 px-2">KiloStone</div>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
        <div className="mt-auto">
          <Button variant="ghost" size="sm" className="w-full justify-start gap-3" onClick={logout}>
            <LogOut className="w-4 h-4" />
            로그아웃
          </Button>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="md:ml-56 pb-20 md:pb-0 min-h-screen">
        {children}
      </main>

      {/* 모바일 하단 탭 바 */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t border-border bg-card flex">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex-1 flex flex-col items-center py-3 gap-1 text-xs transition-colors",
              pathname.startsWith(href)
                ? "text-foreground"
                : "text-muted-foreground"
            )}
          >
            <Icon className="w-5 h-5" />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
```

---

### 5-6. `src/app/dashboard/page.tsx`

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import KpiCard from "@/components/dashboard/KpiCard";
import EfficiencyChart from "@/components/dashboard/EfficiencyChart";
import DistanceChart from "@/components/dashboard/DistanceChart";
import FuelChart from "@/components/dashboard/FuelChart";
import CorrelationChart from "@/components/dashboard/CorrelationChart";
import { statsApi } from "@/lib/api";
import { StatsResponse } from "@/types/stats";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const PERIOD_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "365", label: "최근 1년" },
  { value: "180", label: "최근 6개월" },
  { value: "90", label: "최근 3개월" },
  { value: "30", label: "최근 30일" },
];

const VEHICLE_OPTIONS = [
  { value: "all", label: "전체 차량" },
  { value: "MAN TGX", label: "MAN TGX" },
  { value: "Daewoo Prima", label: "대우 프리마" },
  { value: "Scania", label: "스카니아" },
];

export default function DashboardPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [fetching, setFetching] = useState(true);
  const [vehicleFilter, setVehicleFilter] = useState("all");
  const [periodDays, setPeriodDays] = useState("all");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading]);

  useEffect(() => {
    if (!isAuthenticated) return;
    setFetching(true);
    statsApi
      .get(vehicleFilter !== "all" ? { vehicle_id: vehicleFilter } : undefined)
      .then(setStats)
      .finally(() => setFetching(false));
  }, [isAuthenticated, vehicleFilter]);

  // 기간 필터는 클라이언트에서 monthly 배열을 slice
  const filteredMonthly = (() => {
    if (!stats || periodDays === "all") return stats?.monthly ?? [];
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - Number(periodDays));
    return stats.monthly.filter(
      (m) => new Date(m.year, m.month - 1) >= cutoff
    );
  })();

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 space-y-6">
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
          <h1 className="text-xl font-semibold">대시보드</h1>
          <div className="flex gap-2">
            <Select value={vehicleFilter} onValueChange={setVehicleFilter}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {VEHICLE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={periodDays} onValueChange={setPeriodDays}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PERIOD_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* KPI 카드 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {fetching ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))
          ) : (
            <>
              <KpiCard
                title="평균 연비"
                value={stats?.summary.avg_fuel_efficiency?.toFixed(2) ?? "-"}
                unit="km/L"
              />
              <KpiCard
                title="총 주행거리"
                value={stats?.summary.total_distance.toLocaleString("ko") ?? "-"}
                unit="km"
              />
              <KpiCard
                title="총 연료소모"
                value={stats?.summary.total_consumed_fuel?.toLocaleString("ko") ?? "-"}
                unit="L"
              />
              <KpiCard
                title="총 기록 수"
                value={stats?.summary.total_records.toLocaleString("ko") ?? "-"}
                unit="건"
              />
            </>
          )}
        </div>

        {/* 차트 2×2 그리드 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <EfficiencyChart data={filteredMonthly} loading={fetching} />
          <DistanceChart data={filteredMonthly} loading={fetching} />
          <FuelChart data={filteredMonthly} loading={fetching} />
          <CorrelationChart vehicleId={vehicleFilter !== "all" ? vehicleFilter : undefined} loading={fetching} />
        </div>
      </div>
    </AppShell>
  );
}
```

---

### 5-7. `src/components/dashboard/KpiCard.tsx`

```typescript
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  title: string;
  value: string;
  unit: string;
  delta?: number;       // 선택적: 이전 기간 대비 변화량 (양수=상승, 음수=하락)
}

export default function KpiCard({ title, value, unit, delta }: Props) {
  return (
    <Card>
      <CardHeader className="pb-1 pt-4 px-4">
        <CardTitle className="text-xs font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="text-2xl font-bold">
          {value}
          <span className="text-sm font-normal text-muted-foreground ml-1">{unit}</span>
        </div>
        {delta !== undefined && (
          <p className={`text-xs mt-1 ${delta >= 0 ? "text-green-500" : "text-red-400"}`}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

---

### 5-8. 차트 컴포넌트 공통 패턴

모든 차트 컴포넌트는 아래 패턴을 따름. `MonthlyStats[]`를 props로 받아 Recharts로 렌더링.

#### `src/components/dashboard/EfficiencyChart.tsx`
```typescript
"use client";

import { MonthlyStats } from "@/types/stats";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";
import { ko } from "date-fns/locale";

interface Props { data: MonthlyStats[]; loading: boolean; }

export default function EfficiencyChart({ data, loading }: Props) {
  const chartData = data
    .filter((d) => d.avg_fuel_efficiency !== null)
    .map((d) => ({
      label: format(new Date(d.year, d.month - 1), "yy.MM", { locale: ko }),
      value: d.avg_fuel_efficiency,
    }));

  const avg = chartData.length
    ? chartData.reduce((s, d) => s + (d.value ?? 0), 0) / chartData.length
    : 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">연비 추이</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-52 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3C4043" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} unit=" km/L" />
              <Tooltip formatter={(v: number) => [`${v.toFixed(2)} km/L`, "연비"]} />
              <ReferenceLine y={avg} stroke="#F28B82" strokeDasharray="4 4" label={{ value: `평균 ${avg.toFixed(2)}`, fill: "#F28B82", fontSize: 11 }} />
              <Line type="monotone" dataKey="value" stroke="#81C995" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
```

#### `src/components/dashboard/DistanceChart.tsx`
- BarChart, dataKey: `total_distance`, fill: `#8AB4F8`
- 3개월 이동평균선 (데이터가 3개 이상일 때) 추가: Line으로 overlay
- 구현: `chartData[i].trend = avg(i-1, i, i+1)`

#### `src/components/dashboard/FuelChart.tsx`
- ComposedChart: `refuel`은 Bar, `total_consumed_fuel`은 Area (stroke: `#F28B82`, fill: `rgba(242,139,130,0.2)`)
- 주의: `/stats` 응답에는 `refuel` 합계가 없음 → `GET /logs?per_page=100`으로 월별 직접 집계하거나,
  **Phase 4에서 `/stats` 응답에 `total_refuel` 추가 요청 예정** → Phase 3에서는 FuelChart를 Skeleton placeholder로만 구현하고 "데이터 준비 중" 표시해도 무방

#### `src/components/dashboard/CorrelationChart.tsx`
- `GET /logs?per_page=500&vehicle_id=...` 로 raw 데이터를 가져와 ScatterChart 렌더링
- x축: `speed`, y축: `fuel_efficiency`, 점 하나 = 하루 기록
- speed가 null인 레코드 제외

---

### 5-9. `src/components/logs/LogForm.tsx`

신규 추가(new)와 수정(edit) 양쪽에서 재사용.

```typescript
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VEHICLE_OPTIONS, isScania, LogCreatePayload } from "@/types/log";

// 서버 측 data_validator.py와 동일한 임계값
const schema = z.object({
  date: z.string().min(1, "날짜를 입력하세요"),
  vehicle_id: z.string().min(1, "차량을 선택하세요"),
  distance: z.number({ invalid_type_error: "숫자를 입력하세요" }).min(10).max(1500),
  cumulative_distance: z.number().optional(),
  speed: z.number().min(5).max(120).optional(),
  time: z.string().regex(/^\d{1,3}:\d{2}$/, "HH:MM 형식").optional().or(z.literal("")),
  time_idle: z.string().regex(/^\d{1,3}:\d{2}$/).optional().or(z.literal("")),
  time_pto: z.string().regex(/^\d{1,3}:\d{2}$/).optional().or(z.literal("")),
  fuel_efficiency: z.number().min(1.0).max(5.0).optional(),
  fuel_rate_per_hour: z.number().optional(),
  consumed_fuel: z.number().min(5).max(500).optional(),
  consumed_fuel_idle: z.number().optional(),
  consumed_fuel_pto: z.number().optional(),
  refuel: z.number().optional(),
  reurea: z.number().optional(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  defaultValues?: Partial<FormValues>;
  onSubmit: (payload: LogCreatePayload) => Promise<void>;
  submitLabel?: string;
}

export default function LogForm({ defaultValues, onSubmit, submitLabel = "저장" }: Props) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { date: new Date().toISOString().slice(0, 10), ...defaultValues },
  });

  const vehicleId = form.watch("vehicle_id") ?? "";
  const showScaniaFields = isScania(vehicleId);

  const handleSubmit = async (values: FormValues) => {
    // 빈 문자열 → undefined 변환
    const payload: LogCreatePayload = Object.fromEntries(
      Object.entries(values).filter(([, v]) => v !== "" && v !== undefined)
    ) as LogCreatePayload;
    await onSubmit(payload);
  };

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
      {/* 공통 필드 — 모든 차량 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="날짜" error={form.formState.errors.date?.message}>
          <Input type="date" {...form.register("date")} />
        </Field>

        <Field label="차량" error={form.formState.errors.vehicle_id?.message}>
          <Select
            value={form.watch("vehicle_id")}
            onValueChange={(v) => form.setValue("vehicle_id", v)}
          >
            <SelectTrigger><SelectValue placeholder="차량 선택" /></SelectTrigger>
            <SelectContent>
              {VEHICLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="주행거리 (km)" error={form.formState.errors.distance?.message}>
          <Input type="number" step="0.1" {...form.register("distance", { valueAsNumber: true })} />
        </Field>

        <Field label="연비 (km/L)" error={form.formState.errors.fuel_efficiency?.message}>
          <Input type="number" step="0.01" {...form.register("fuel_efficiency", { valueAsNumber: true })} />
        </Field>

        <Field label="연료소모량 (L)" error={form.formState.errors.consumed_fuel?.message}>
          <Input type="number" step="0.01" {...form.register("consumed_fuel", { valueAsNumber: true })} />
        </Field>

        <Field label="주유량 (L)">
          <Input type="number" step="0.1" {...form.register("refuel", { valueAsNumber: true })} />
        </Field>

        <Field label="요소수 (L)">
          <Input type="number" step="0.1" {...form.register("reurea", { valueAsNumber: true })} />
        </Field>

        <Field label="누적거리 (km)">
          <Input type="number" step="0.1" {...form.register("cumulative_distance", { valueAsNumber: true })} />
        </Field>

        <Field label="평균속도 (km/h)" error={form.formState.errors.speed?.message}>
          <Input type="number" step="0.1" {...form.register("speed", { valueAsNumber: true })} />
        </Field>

        <Field label="운행시간 (HH:MM)" error={form.formState.errors.time?.message}>
          <Input placeholder="06:30" {...form.register("time")} />
        </Field>
      </div>

      {/* 스카니아 전용 필드 — vehicle_id === "Scania" 일 때만 표시 */}
      {showScaniaFields && (
        <div className="border border-border rounded-lg p-4 space-y-4">
          <p className="text-xs text-muted-foreground font-medium">스카니아 전용 항목</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="공회전 연료 (L)">
              <Input type="number" step="0.01" {...form.register("consumed_fuel_idle", { valueAsNumber: true })} />
            </Field>
            <Field label="PTO 연료 (L)">
              <Input type="number" step="0.01" {...form.register("consumed_fuel_pto", { valueAsNumber: true })} />
            </Field>
            <Field label="시간당 연료 (L/h)">
              <Input type="number" step="0.01" {...form.register("fuel_rate_per_hour", { valueAsNumber: true })} />
            </Field>
            <Field label="공회전 시간 (HH:MM)" error={form.formState.errors.time_idle?.message}>
              <Input placeholder="00:45" {...form.register("time_idle")} />
            </Field>
            <Field label="PTO 시간 (HH:MM)" error={form.formState.errors.time_pto?.message}>
              <Input placeholder="00:00" {...form.register("time_pto")} />
            </Field>
          </div>
        </div>
      )}

      <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? "저장 중..." : submitLabel}
      </Button>
    </form>
  );
}

// 내부 유틸
function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-sm">{label}</Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
```

---

### 5-10. `src/app/logs/page.tsx` (기록 목록)

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import LogTable from "@/components/logs/LogTable";
import LogFilters from "@/components/logs/LogFilters";
import { logsApi } from "@/lib/api";
import { LogsPage } from "@/types/log";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { PlusCircle } from "lucide-react";

export default function LogsPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<LogsPage | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<{
    vehicle_id?: string;
    date_from?: string;
    date_to?: string;
  }>({});
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading]);

  useEffect(() => {
    if (!isAuthenticated) return;
    setFetching(true);
    logsApi.list({ page, per_page: 20, ...filters })
      .then(setData)
      .finally(() => setFetching(false));
  }, [isAuthenticated, page, filters]);

  return (
    <AppShell>
      <div className="p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">기록 조회</h1>
          <Button asChild size="sm">
            <Link href="/logs/new"><PlusCircle className="w-4 h-4 mr-1" />추가</Link>
          </Button>
        </div>

        <LogFilters value={filters} onChange={(f) => { setFilters(f); setPage(1); }} />

        <LogTable
          data={data}
          loading={fetching}
          page={page}
          onPageChange={setPage}
          onDelete={async (id) => {
            await logsApi.delete(id);
            logsApi.list({ page, per_page: 20, ...filters }).then(setData);
          }}
        />
      </div>
    </AppShell>
  );
}
```

---

### 5-11. `src/components/logs/LogTable.tsx`

```typescript
"use client";

import { DrivingLog, LogsPage } from "@/types/log";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";

interface Props {
  data: LogsPage | null;
  loading: boolean;
  page: number;
  onPageChange: (p: number) => void;
  onDelete: (id: number) => Promise<void>;
}

export default function LogTable({ data, loading, page, onPageChange, onDelete }: Props) {
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const handleDelete = async (log: DrivingLog) => {
    if (!confirm(`${log.date} ${log.vehicle_id} 기록을 삭제하시겠습니까?`)) return;
    setDeletingId(log.id);
    try {
      await onDelete(log.id);
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!data || data.items.length === 0) return <p className="text-muted-foreground text-sm text-center py-12">기록이 없습니다.</p>;

  const totalPages = Math.ceil(data.total / data.per_page);

  return (
    <div className="space-y-3">
      {/* 모바일: 카드 목록, 데스크탑: 테이블 */}
      <div className="hidden md:block rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>날짜</TableHead>
              <TableHead>차량</TableHead>
              <TableHead className="text-right">주행(km)</TableHead>
              <TableHead className="text-right">연비(km/L)</TableHead>
              <TableHead className="text-right">소모(L)</TableHead>
              <TableHead>출처</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((log) => (
              <TableRow key={log.id}>
                <TableCell>{log.date}</TableCell>
                <TableCell>{log.vehicle_id}</TableCell>
                <TableCell className="text-right">{log.distance?.toLocaleString("ko")}</TableCell>
                <TableCell className="text-right">{log.fuel_efficiency?.toFixed(2) ?? "-"}</TableCell>
                <TableCell className="text-right">{log.consumed_fuel?.toFixed(1) ?? "-"}</TableCell>
                <TableCell>
                  <Badge variant={log.source === "manual" ? "default" : "secondary"}>
                    {log.source === "manual" ? "수동" : "파이프라인"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" asChild>
                      <Link href={`/logs/${log.id}/edit`}><Pencil className="w-3.5 h-3.5" /></Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={deletingId === log.id}
                      onClick={() => handleDelete(log)}
                    >
                      <Trash2 className="w-3.5 h-3.5 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* 모바일 카드 */}
      <div className="md:hidden space-y-2">
        {data.items.map((log) => (
          <div key={log.id} className="border border-border rounded-lg p-3 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-medium text-sm">{log.date}</span>
              <Badge variant={log.source === "manual" ? "default" : "secondary"} className="text-xs">
                {log.source === "manual" ? "수동" : "파이프라인"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">{log.vehicle_id}</p>
            <div className="flex gap-4 text-sm">
              <span>{log.distance?.toLocaleString("ko")} km</span>
              <span>{log.fuel_efficiency?.toFixed(2) ?? "-"} km/L</span>
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <Button variant="ghost" size="sm" asChild>
                <Link href={`/logs/${log.id}/edit`}><Pencil className="w-3.5 h-3.5 mr-1" />수정</Link>
              </Button>
              <Button variant="ghost" size="sm" onClick={() => handleDelete(log)} disabled={deletingId === log.id}>
                <Trash2 className="w-3.5 h-3.5 mr-1 text-destructive" />삭제
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* 페이지네이션 */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>전체 {data.total.toLocaleString("ko")}건</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => onPageChange(page - 1)}>이전</Button>
          <span className="flex items-center">{page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>다음</Button>
        </div>
      </div>
    </div>
  );
}
```

---

### 5-12. `src/app/logs/new/page.tsx`

```typescript
"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useEffect } from "react";
import AppShell from "@/components/layout/AppShell";
import LogForm from "@/components/logs/LogForm";
import { logsApi } from "@/lib/api";
import { LogCreatePayload } from "@/types/log";
import { useToast } from "@/components/ui/use-toast";

export default function NewLogPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const { toast } = useToast();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading]);

  const handleSubmit = async (payload: LogCreatePayload) => {
    await logsApi.create(payload);
    toast({ description: "기록이 저장되었습니다." });
    router.push("/logs");
  };

  return (
    <AppShell>
      <div className="p-4 md:p-6 max-w-2xl">
        <h1 className="text-xl font-semibold mb-6">운행기록 추가</h1>
        <LogForm onSubmit={handleSubmit} submitLabel="저장" />
      </div>
    </AppShell>
  );
}
```

### `src/app/logs/[id]/edit/page.tsx`

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import LogForm from "@/components/logs/LogForm";
import { logsApi } from "@/lib/api";
import { DrivingLog, LogCreatePayload } from "@/types/log";
import { useToast } from "@/components/ui/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function EditLogPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const { toast } = useToast();
  const [log, setLog] = useState<DrivingLog | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading]);

  useEffect(() => {
    if (!isAuthenticated || !params.id) return;
    // GET /logs?page=1&per_page=1 대신, 목록에서 단건 조회는 Phase 2 설계에서 id 검색 미지원
    // → GET /logs?page=1&per_page=1 식 조회 대신 목록 API에서 해당 id 조회
    // 실용적 해결: /logs 목록을 per_page=1로 date_from=date_to로 조회하기 어려우므로,
    // Phase 2 FastAPI에 GET /logs/{id} 단건 엔드포인트를 추가 요청 (아래 "Phase 2 보완" 참고)
    import("@/lib/api").then(({ apiFetch }) =>
      apiFetch<DrivingLog>(`/logs/${params.id}`).then(setLog)
    );
  }, [isAuthenticated, params.id]);

  const handleSubmit = async (payload: LogCreatePayload) => {
    await logsApi.update(Number(params.id), payload);
    toast({ description: "수정되었습니다." });
    router.push("/logs");
  };

  return (
    <AppShell>
      <div className="p-4 md:p-6 max-w-2xl">
        <h1 className="text-xl font-semibold mb-6">운행기록 수정</h1>
        {log ? (
          <LogForm
            defaultValues={{ ...log, date: log.date }}
            onSubmit={handleSubmit}
            submitLabel="수정 저장"
          />
        ) : (
          <Skeleton className="h-96 w-full" />
        )}
      </div>
    </AppShell>
  );
}
```

---

## 6. Phase 2 보완 (Phase 3 구현 전 반드시 추가)

Phase 3 edit 페이지에서 단건 조회가 필요합니다. Phase 2 `api/routers/logs.py`에 아래 엔드포인트를 추가해야 합니다:

```python
@router.get("/{log_id}", response_model=DrivingLogResponse)
def get_log(
    log_id: int,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"),
            {"id": log_id}
        ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"id={log_id} 기록을 찾을 수 없습니다.")
    return dict(row)
```

---

## 7. `frontend/Dockerfile`

Next.js standalone 빌드 사용 (이미지 크기 최소화).

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

`next.config.ts`에 반드시 포함:
```typescript
const nextConfig = {
  output: "standalone",
};
export default nextConfig;
```

---

## 8. `docker-compose.yml` 변경사항

기존 서비스 아래에 추가:

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: kilostone-frontend:latest
    container_name: kilostone-frontend
    restart: unless-stopped
    expose:
      - "3000"
    environment:
      NEXT_PUBLIC_API_URL: /api
    networks:
      - proxy-network
```

---

## 9. Nginx 추가 설정

Phase 2에서 추가한 `/api/` 블록 아래에 추가:

```nginx
location / {
    proxy_pass         http://kilostone-frontend:3000;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

**순서 주의**: Nginx는 위에서부터 매칭하므로 `/api/` 블록이 `/` 블록보다 **위**에 있어야 합니다.

---

## 10. 구현 순서 권고

1. `src/types/` 2개 파일 생성
2. `src/lib/api.ts` 생성
3. `src/contexts/AuthContext.tsx` 생성
4. `src/app/layout.tsx` 생성
5. `src/app/login/page.tsx` 생성
6. `src/components/layout/AppShell.tsx` 생성
7. 대시보드 페이지 + KpiCard + EfficiencyChart + DistanceChart 생성
8. LogForm 생성
9. /logs/new 페이지 생성
10. /logs 목록 페이지 + LogTable + LogFilters 생성
11. /logs/[id]/edit 페이지 생성
12. /vehicles 페이지 + VehicleCompareCharts 생성
13. FuelChart, CorrelationChart 생성
14. Phase 2에 GET /logs/{id} 단건 엔드포인트 추가
15. Dockerfile 생성 + docker-compose.yml 추가
16. `npm run build` 성공 확인
17. `docker compose up -d --build frontend` 실행 확인
