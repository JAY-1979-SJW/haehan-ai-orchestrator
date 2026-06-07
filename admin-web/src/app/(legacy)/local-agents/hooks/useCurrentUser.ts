import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/api";
import type { CurrentUser } from "@/types/auth";

export interface UseCurrentUserResult {
  currentUser: CurrentUser | null;
  userLoading: boolean;
  userError: boolean;
}

export function useCurrentUser(): UseCurrentUserResult {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);
  const [userError, setUserError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setUserLoading(true);
    setUserError(false);
    getCurrentUser()
      .then((u) => { if (!cancelled) { setCurrentUser(u); setUserLoading(false); } })
      .catch(() => { if (!cancelled) { setUserError(true); setUserLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  return { currentUser, userLoading, userError };
}
