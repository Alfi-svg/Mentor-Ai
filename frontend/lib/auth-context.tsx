"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  apiClient,
  getStoredToken,
  setOnUnauthorizedCallback,
  setStoredToken,
} from "./api-client";
import { User } from "./types";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  sessionExpired: boolean;
  login: (email: string, pass: string) => Promise<void>;
  signup: (email: string, pass: string) => Promise<void>;
  logout: () => void;
  clearSessionExpired: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [sessionExpired, setSessionExpired] = useState<boolean>(false);
  const router = useRouter();

  const handleUnauthorized = useCallback(() => {
    setUser(null);
    setToken(null);
    setStoredToken(null);
    setSessionExpired(true);
    router.push("/login");
  }, [router]);

  useEffect(() => {
    setOnUnauthorizedCallback(handleUnauthorized);
  }, [handleUnauthorized]);

  // Load session on startup
  const refreshUser = useCallback(async () => {
    const existingToken = getStoredToken();
    if (!existingToken) {
      setUser(null);
      setToken(null);
      setIsLoading(false);
      return;
    }

    try {
      setToken(existingToken);
      const profile = await apiClient.getMe();
      setUser(profile);
    } catch {
      // Token invalid or expired
      setUser(null);
      setToken(null);
      setStoredToken(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const res = await apiClient.login(email, pass);
      const userObj: User = res.user || {
        id: (res as any).user_id || "",
        email: (res as any).email || email,
      };
      setUser(userObj);
      setToken(res.access_token);
      setSessionExpired(false);
      // Opportunistically fetch full profile with preferences in background
      apiClient.getMe().then((p) => {
        if (p) setUser(p);
      }).catch(() => {});
      router.push("/dashboard");
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (email: string, pass: string) => {
    setIsLoading(true);
    try {
      const res = await apiClient.signup(email, pass);
      const userObj: User = res.user || {
        id: (res as any).user_id || "",
        email: (res as any).email || email,
      };
      setUser(userObj);
      setToken(res.access_token);
      setSessionExpired(false);
      // Opportunistically fetch full profile with preferences in background
      apiClient.getMe().then((p) => {
        if (p) setUser(p);
      }).catch(() => {});
      router.push("/dashboard");
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    apiClient.logout();
    setUser(null);
    setToken(null);
    router.push("/login");
  };

  const clearSessionExpired = () => {
    setSessionExpired(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user,
        sessionExpired,
        login,
        signup,
        logout,
        clearSessionExpired,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
