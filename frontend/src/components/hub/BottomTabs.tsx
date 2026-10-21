"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/", label: "홈" },
  { href: "/drive/new", label: "운행 입력" },
];

export function BottomTabs() {
  const pathname = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t bg-background lg:hidden">
      <div className="mx-auto flex max-w-md">
        {TABS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "flex h-14 flex-1 items-center justify-center text-lg font-semibold",
              pathname === t.href ? "text-primary" : "text-muted-foreground"
            )}
          >
            {t.label}
          </Link>
        ))}
      </div>
    </nav>
  );
}
