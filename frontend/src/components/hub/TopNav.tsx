"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/", label: "홈" },
  { href: "/drive/new", label: "운행 입력" },
];

export function TopNav() {
  const pathname = usePathname();
  return (
    <nav className="sticky top-0 z-40 hidden border-b bg-background lg:block">
      <div className="mx-auto flex max-w-6xl gap-2 px-4">
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "flex h-14 items-center border-b-2 px-4 text-lg font-semibold",
              pathname === t.href ? "border-primary text-primary" : "border-transparent text-muted-foreground"
            )}
          >
            {t.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
