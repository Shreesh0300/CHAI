import React from 'react';

export interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
}

export function Link({ href, children, ...props }: LinkProps) {
  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (props.onClick) props.onClick(e);
    if (!e.defaultPrevented) {
      if (href.startsWith('#')) {
        e.preventDefault();
        const id = href.replace(/^#/, '');
        const element = document.getElementById(id);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth' });
        }
      } else if (href.startsWith('/')) {
        e.preventDefault();
        try {
          window.history.pushState({}, '', href);
          window.dispatchEvent(new CustomEvent('chai-navigate', { detail: href }));
        } catch {
          window.location.href = href;
        }
      }
    }
  };

  return (
    <a href={href} onClick={handleClick} {...props}>
      {children}
    </a>
  );
}

export default Link;
