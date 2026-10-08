export function useRouter() {
  return {
    push: (href: string) => {
      try {
        window.history.pushState({}, '', href);
        window.dispatchEvent(new CustomEvent('chai-navigate', { detail: href }));
      } catch {
        window.location.href = href;
      }
    },
    replace: (href: string) => {
      try {
        window.history.replaceState({}, '', href);
        window.dispatchEvent(new CustomEvent('chai-navigate', { detail: href }));
      } catch {
        window.location.replace(href);
      }
    },
    back: () => window.history.back(),
    forward: () => window.history.forward(),
    refresh: () => window.location.reload(),
  };
}

export function usePathname(): string {
  return typeof window !== 'undefined' ? window.location.pathname : '/';
}

export function useSearchParams(): URLSearchParams {
  return typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : new URLSearchParams();
}

export function redirect(url: string): never {
  if (typeof window !== 'undefined') {
    try {
      window.history.pushState({}, '', url);
      window.dispatchEvent(new CustomEvent('chai-navigate', { detail: url }));
    } catch {
      window.location.href = url;
    }
  }
  throw new Error(`Redirected to ${url}`);
}
