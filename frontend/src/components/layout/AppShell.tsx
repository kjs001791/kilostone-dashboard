"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { LayoutDashboard, ClipboardList, PlusCircle, Truck, LogOut, Users } from "lucide-react";
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
  const { logout, role } = useAuth();

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
        <div className="mt-auto space-y-1">
          {role === "admin" && (
            <Link
              href="/admin/users"
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                pathname.startsWith("/admin")
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              )}
            >
              <Users className="w-4 h-4" />
              계정 관리
            </Link>
          )}
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
      <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t border-border bg-card flex z-50">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex-1 flex flex-col items-center py-3 gap-1 text-[10px] transition-colors",
              pathname.startsWith(href)
                ? "text-primary"
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
