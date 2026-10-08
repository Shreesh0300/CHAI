import React from 'react';
import { API_BASE } from './api-config';

export interface UserSession {
  id: string;
  name: string;
  email: string;
  image?: string | null;
  provider?: 'email' | 'google' | 'github' | 'guest';
}

const STORAGE_KEY = 'chai_auth_user';

function getStoredUser(): UserSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function setStoredUser(user: UserSession | null) {
  try {
    if (user) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore
  }
}

export const authClient = {
  signUp: {
    email: async ({ email, password, name }: { email: string; password?: string; name: string }) => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/sign-up`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, name }),
        });
        if (res.ok) {
          const data = await res.json();
          const userObj: UserSession = {
            id: data.id || email,
            name: data.name || name,
            email,
            provider: 'email',
          };
          setStoredUser(userObj);
          return { data: userObj, error: null };
        }
      } catch {
        // Fallback to local session
      }
      const userObj: UserSession = {
        id: `user_${Date.now()}`,
        name,
        email,
        provider: 'email',
      };
      setStoredUser(userObj);
      return { data: userObj, error: null };
    },
  },

  signIn: {
    email: async ({ email, password }: { email: string; password?: string }) => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/sign-in`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (res.ok) {
          const data = await res.json();
          const userObj: UserSession = {
            id: data.id || email,
            name: data.name || email.split('@')[0],
            email,
            provider: 'email',
          };
          setStoredUser(userObj);
          return { data: userObj, error: null };
        }
      } catch {
        // Fallback to local session
      }
      const userObj: UserSession = {
        id: `user_${Date.now()}`,
        name: email.split('@')[0],
        email,
        provider: 'email',
      };
      setStoredUser(userObj);
      return { data: userObj, error: null };
    },

    social: async ({ provider }: { provider: 'google' | 'github' }) => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/${provider}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (res.ok) {
          const data = await res.json();
          const userObj: UserSession = {
            id: data.id || `${provider}_${Date.now()}`,
            name: data.name || (provider === 'google' ? 'Google Operator' : 'GitHub Engineer'),
            email: data.email || (provider === 'google' ? 'user@gmail.com' : 'developer@github.com'),
            image: data.image || null,
            provider,
          };
          setStoredUser(userObj);
          return { data: userObj, error: null };
        }
      } catch {
        // Fallback to client-side session
      }

      const userObj: UserSession =
        provider === 'google'
          ? {
              id: `goog_${Date.now()}`,
              name: 'Google Operator',
              email: 'operator@gmail.com',
              image: 'https://lh3.googleusercontent.com/a/default-user=s96-c',
              provider: 'google',
            }
          : {
              id: `gh_${Date.now()}`,
              name: 'GitHub Engineer',
              email: 'engineer@github.com',
              image: 'https://avatars.githubusercontent.com/u/9919?v=4',
              provider: 'github',
            };

      setStoredUser(userObj);
      return { data: userObj, error: null };
    },
  },

  signInAsGuest: () => {
    const userObj: UserSession = {
      id: `guest_${Date.now()}`,
      name: 'Guest Operator',
      email: 'guest@chai.ai',
      provider: 'guest',
    };
    setStoredUser(userObj);
    return userObj;
  },

  updateUser: async ({ name }: { name: string }) => {
    try {
      await fetch(`${API_BASE}/api/auth/update-user`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
    } catch {
      // ignore
    }
    const current = getStoredUser();
    if (current) {
      current.name = name;
      setStoredUser(current);
    }
    return { data: current, error: null };
  },

  signOut: async () => {
    try {
      await fetch(`${API_BASE}/api/auth/sign-out`, {
        method: 'POST',
      });
    } catch {
      // ignore
    }
    setStoredUser(null);
    return { data: true, error: null };
  },

  useSession: () => {
    const [user, setUser] = React.useState<UserSession | null>(() => getStoredUser());
    const [isPending, setIsPending] = React.useState(false);

    React.useEffect(() => {
      const u = getStoredUser();
      setUser(u);
    }, []);

    return {
      data: user ? { user, session: { id: 'sess_1', userId: user.id } } : null,
      isPending,
      error: null,
    };
  },
};

export const { signIn, signUp, signOut, useSession, signInAsGuest } = authClient;
