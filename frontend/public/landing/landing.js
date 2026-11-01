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

// ── Hero Stage: Mascot Fan, Tooltips & Flight into Sentence Slots ──
(() => {
  const heroTrack = document.getElementById('hero-track');
  const heroStage = document.getElementById('hero-stage');
  const heroIntro = document.getElementById('hero-intro');
  const statement = document.querySelector('[data-framer-name="Statement Panel"]');

  if (!heroTrack || !heroStage || !heroIntro || !statement) return;

  const mascots = [
    { fanId: 'chip-fan-1', slotId: 'chip-slot-1', role: 'Diff agent', name: 'Cut', angle: -12 },
    { fanId: 'chip-fan-2', slotId: 'chip-slot-2', role: 'Settings agent', name: 'Hue', angle: 11 },
    { fanId: 'chip-fan-3', slotId: 'chip-slot-3', role: 'Doc agent', name: 'Nova', angle: -8 },
    { fanId: 'chip-fan-4', slotId: 'chip-slot-4', role: 'Drift agent', name: 'Echo', angle: 7 },
    { fanId: 'chip-fan-5', slotId: 'chip-slot-5', role: 'Autofix agent', name: 'Flow', angle: 15 }
  ];

  let metrics = [];
  let currentScrollProgress = 0;

  // Pre-calculate exact resting offsets once (zero layout thrashing during scroll)
  function measureTargets() {
    // Temporarily clear transforms to measure true natural DOM layout centers
    mascots.forEach((m) => {
      const card = document.getElementById(m.fanId);
      if (card) card.style.transform = 'none';
    });
    statement.style.transform = 'none';

    const stageRect = heroStage.getBoundingClientRect();

    metrics = mascots.map((m) => {
      const fanCard = document.getElementById(m.fanId);
      const slotEl = document.getElementById(m.slotId);
      if (!fanCard || !slotEl) return null;

      const fanRect = fanCard.getBoundingClientRect();
      const slotRect = slotEl.getBoundingClientRect();

      const fanCenterX = fanRect.left + fanRect.width / 2 - stageRect.left;
      const fanCenterY = fanRect.top + fanRect.height / 2 - stageRect.top;
      const slotCenterX = slotRect.left + slotRect.width / 2 - stageRect.left;
      const slotCenterY = slotRect.top + slotRect.height / 2 - stageRect.top;

      return {
        fanCard,
        deltaX: slotCenterX - fanCenterX,
        deltaY: slotCenterY - fanCenterY,
        targetScale: slotRect.width / (fanRect.width || 1),
        angle: m.angle,
      };
    });

    render();
  }

  // Inject hover tooltip badges on each mascot
  mascots.forEach((m) => {
    const card = document.getElementById(m.fanId);
    if (!card) return;

    const tip = document.createElement('div');
    tip.className = 'dg-mascot-tooltip';
    tip.innerHTML = `
      <span class="dg-mascot-tooltip-role">${m.role}</span>
      <span class="dg-mascot-tooltip-name">${m.name}</span>
    `;
    card.style.position = 'relative';
    card.appendChild(tip);

    card.addEventListener('mouseenter', () => {
      if (currentScrollProgress < 0.08) {
        card.classList.add('dg-mascot-hovered');
        render();
      }
    });
    card.addEventListener('mouseleave', () => {
      card.classList.remove('dg-mascot-hovered');
      render();
    });
  });

  const easeInOutCubic = (t) => {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  };

  const render = () => {
    const travel = heroTrack.offsetHeight - heroStage.offsetHeight;
    if (travel <= 0) return;

    const rawP = -heroTrack.getBoundingClientRect().top / travel;
    currentScrollProgress = Math.min(1, Math.max(0, rawP));
    const p = currentScrollProgress;

    // Phase 1: Headline Intro cross-fades out (p: 0 -> 0.28)
    const introOpacity = Math.max(0, 1 - p / 0.26);
    heroIntro.style.opacity = introOpacity.toFixed(3);
    heroIntro.style.pointerEvents = introOpacity > 0.1 ? 'auto' : 'none';

    // Phase 2: Statement sentence fades in (p: 0.16 -> 0.42)
    const sentenceProgress = Math.min(1, Math.max(0, (p - 0.16) / 0.26));
    statement.style.opacity = sentenceProgress.toFixed(3);
    statement.style.pointerEvents = sentenceProgress > 0.8 ? 'auto' : 'none';

    // Phase 3: Mascot Flight directly into slots (p: 0.12 -> 0.80)
    const flightT = Math.min(1, Math.max(0, (p - 0.12) / 0.68));
    const easedT = easeInOutCubic(flightT);

    for (let i = 0; i < metrics.length; i++) {
      const m = metrics[i];
      if (!m || !m.fanCard) continue;

      if (easedT <= 0.001) {
        if (m.fanCard.classList.contains('dg-mascot-hovered')) {
          m.fanCard.style.setProperty(
            'transform',
            `scale(1.08) rotate(${(m.angle * 0.4).toFixed(1)}deg) translateY(-14px)`,
            'important'
          );
        } else {
          // Dynamic scroll sway & spring float between 0% and 5%
          const initialParallax = p * -45;
          const tiltDynamic = m.angle + (p * 14 * (m.angle > 0 ? 1 : -1));
          m.fanCard.style.setProperty(
            'transform',
            `translate3d(0, ${initialParallax.toFixed(1)}px, 0) rotate(${tiltDynamic.toFixed(1)}deg)`,
            'important'
          );
        }
        m.fanCard.style.setProperty('z-index', '2', 'important');
      } else {
        m.fanCard.classList.remove('dg-mascot-hovered');

        const curX = easedT * m.deltaX;
        const curY = easedT * m.deltaY;
        const curScale = 1 + easedT * (m.targetScale - 1);
        const curRot = (1 - easedT) * m.angle;

        m.fanCard.style.setProperty(
          'transform',
          `translate3d(${curX.toFixed(2)}px, ${curY.toFixed(2)}px, 0) scale(${curScale.toFixed(4)}) rotate(${curRot.toFixed(2)}deg)`,
          'important'
        );
        m.fanCard.style.setProperty('z-index', easedT > 0.05 ? '80' : '2', 'important');
      }
    }
  };

  let rafScheduled = false;
  const onScroll = () => {
    if (!rafScheduled) {
      rafScheduled = true;
      requestAnimationFrame(() => {
        render();
        rafScheduled = false;
      });
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', measureTargets);
  window.addEventListener('load', measureTargets);
  document.addEventListener('DOMContentLoaded', measureTargets);

  // Initial measurement
  measureTargets();
})();


// ── Scroll Percentage Counter (0% -> 100%) ──
(() => {
  const updateScrollPct = () => {
    const total = document.documentElement.scrollHeight - window.innerHeight;
    const progress = total > 0 ? (window.scrollY / total) * 100 : 0;
    const pct = Math.min(100, Math.max(0, Math.round(progress)));
    document.querySelectorAll('.dg-pct, .framer-1m1ag2l p, [data-framer-name="Scroll Progress"] p').forEach((el) => {
      el.textContent = `${pct}%`;
    });
  };
  window.addEventListener('scroll', updateScrollPct, { passive: true });
  window.addEventListener('resize', updateScrollPct);
  window.addEventListener('DOMContentLoaded', updateScrollPct);
  updateScrollPct();
})();

// ── 21% - 24%: Create Modes (3-way Expanding Cards) ──
(() => {
  const initCreateModes = () => {
    const cardRemix = document.querySelector('[data-framer-name="Card · Remix"]');
    const cardDescribe = document.querySelector('[data-framer-name="Card · Describe"]');
    const cardCode = document.querySelector('[data-framer-name="Card · Code"]');
    const cards = [cardRemix, cardDescribe, cardCode].filter(Boolean);

    if (cards.length < 2) return;

    const setActive = (activeCard) => {
      cards.forEach((c) => {
        if (c === activeCard) {
          c.classList.add('dg-card-active');
          c.classList.remove('dg-card-collapsed');
        } else {
          c.classList.remove('dg-card-active');
          c.classList.add('dg-card-collapsed');
        }
      });
    };

    // Default to Remix open
    setActive(cardRemix || cards[0]);

    cards.forEach((c) => {
      c.addEventListener('click', () => setActive(c));
      c.addEventListener('mouseenter', () => setActive(c));
    });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCreateModes);
  } else {
    initCreateModes();
  }
})();

// ── 24% - 28%: Connected Phone Mockup Parallax ──
(() => {
  const connectedSec = document.getElementById('connected') || document.querySelector('[data-framer-name="Connected"]');
  if (!connectedSec) return;

  const visual = connectedSec.querySelector('.framer-2m9b1t');
  if (!visual) return;

  const onScroll = () => {
    const rect = connectedSec.getBoundingClientRect();
    const vh = window.innerHeight;
    if (rect.top < vh && rect.bottom > 0) {
      // Parallax lift
      const p = Math.max(0, Math.min(1, (vh - rect.top) / (vh + rect.height)));
      const translateY = (1 - p) * 36;
      visual.style.transform = `translate3d(0, ${translateY.toFixed(1)}px, 0)`;
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();
