import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, ApiError, setUnauthorizedHandler, type Me } from "../lib/api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (input: SignupInput) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

export interface SignupInput {
  email: string;
  password: string;
  workspace_name: string;
  name?: string;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get<Me>("/api/auth/me");
      setMe(data);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setMe(null);
      } else {
        setMe(null);
      }
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  // Clear auth state on any mid-session 401 so ProtectedRoute redirects to login.
  useEffect(() => {
    setUnauthorizedHandler(() => setMe(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<Me>("/api/auth/login", { email, password });
    setMe(data);
  }, []);

  const signup = useCallback(async (input: SignupInput) => {
    const data = await api.post<Me>("/api/auth/signup", input);
    setMe(data);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post<void>("/api/auth/logout");
    } finally {
      setMe(null);
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ me, loading, login, signup, logout, refresh }),
    [me, loading, login, signup, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
