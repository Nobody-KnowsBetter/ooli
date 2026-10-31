// Sends the buttons to GitHub login, or straight to the dashboard if the visitor is already in.
(async () => {
  const messages = {
    denied: 'GitHub login was cancelled.',
    expired: 'That login link expired. Please try again.',
    rejected: 'GitHub rejected the login. Please try again.',
    unavailable: 'Could not reach GitHub. Please try again.',
  };

  const error = messages[new URLSearchParams(location.search).get('login_error')];
  if (error) {
    const box = document.createElement('p');
    box.className = 'dg-error';
    box.setAttribute('role', 'alert');
    box.textContent = error;
    document.body.append(box);
  }

  try {
    const res = await fetch('/api/auth/status', { cache: 'no-store' });
    if (!res.ok) return;
    const status = await res.json();

    if (status.logged_in || !status.login_enabled) {
      document.querySelectorAll('[data-dg-login]').forEach((link) => {
        link.href = '/dashboard';
        const label = link.querySelector('[data-dg-label]');
        if (label) label.textContent = 'Open dashboard';
      });
      document.querySelectorAll('.dg-private').forEach((el) => {
        if (status.login_enabled) {
          el.remove();
        } else {
          el.textContent = 'GitHub sign-in isn’t set up on this server yet. The dashboard shows how.';
        }
      });

      if (status.logged_in) {
        const signOut = document.createElement('a');
        signOut.href = '#';
        signOut.className = 'dg-link dg-signout';
        signOut.textContent = 'Sign out';
        signOut.addEventListener('click', async (event) => {
          event.preventDefault();
          await fetch('/api/auth/logout', { method: 'POST' });
          location.assign('/');
        });
        document.querySelector('.dg-nav')?.insertBefore(signOut, document.querySelector('.dg-login'));
      }
    } else if (!status.private_repos_allowed) {
      document.querySelectorAll('.dg-private').forEach((el) => el.remove());
    }
  } catch {
    // Backend is offline: the login link will show that when clicked.
  }
})();

// Fades sections in as they scroll into view.
(() => {
  const hidden = [...document.querySelectorAll('#main [style*="opacity:0"]')].filter((el) =>
    el.getAttribute('style').includes('translate')
  );
  const reveal = (el) => {
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    el.style.opacity = '1';
    el.style.transform = 'none';
  };

  if (!('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    hidden.forEach(reveal);
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        reveal(entry.target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.05 });
  hidden.forEach((el) => observer.observe(el));
})();

// The hero stays pinned while scrolling, and swaps the headline for the statement halfway through.
(() => {
  const hero = document.querySelector('section[data-framer-name="Hero"]');
  const stage = hero && hero.querySelector('[data-framer-name="Hero Stage"]');
  const statement = stage && stage.querySelector('[data-framer-name="Statement Panel"]');
  if (!statement) return;

  const headline = [...stage.children].filter((el) => el !== statement && !el.contains(statement));
  [statement, ...headline].forEach((el) => {
    el.style.transition = 'opacity 0.4s ease';
  });

  const update = () => {
    const travel = hero.offsetHeight - stage.offsetHeight;
    const showStatement = travel > 0 && -hero.getBoundingClientRect().top / travel > 0.4;
    statement.style.opacity = showStatement ? '1' : '0';
    statement.style.pointerEvents = showStatement ? 'auto' : 'none';
    headline.forEach((el) => {
      el.style.opacity = showStatement ? '0' : '1';
      el.style.pointerEvents = showStatement ? 'none' : 'auto';
    });
  };

  addEventListener('scroll', update, { passive: true });
  addEventListener('resize', update);
  update();
})();
