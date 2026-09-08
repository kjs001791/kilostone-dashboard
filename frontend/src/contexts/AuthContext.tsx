"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { tokenStore, authApi } from "@/lib/api";
import { useRouter } from "next/navigation";

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
  role: "admin" | "driver" | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [role, setRole] = useState<"admin" | "driver" | null>(null);
  const router = useRouter();

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.access_token) {
          tokenStore.set(data.access_token);
          setIsAuthenticated(true);
          setRole(data.role ?? "driver");
        }
      })
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const data = await authApi.login(username, password);
    tokenStore.set(data.access_token);
    setIsAuthenticated(true);
    setRole((data.role as "admin" | "driver") ?? "driver");
    router.push("/dashboard");
  };

  const logout = async () => {
    try { await authApi.logout(); } catch (e) {}
    tokenStore.set(null);
    setIsAuthenticated(false);
    setRole(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading, role, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};
