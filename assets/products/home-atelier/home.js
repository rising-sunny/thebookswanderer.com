const toggle = document.querySelector('.mobile-menu');
const nav = document.querySelector('#nav');
function closeMenu() {
  toggle.setAttribute('aria-expanded', 'false');
  nav.classList.remove('open');
}
toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  nav.classList.toggle('open', open);
});
nav.addEventListener('click', event => {
  if (event.target.closest('a')) closeMenu();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeMenu();
});

const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const motionButton = document.querySelector('.motion-toggle');
let manuallyPaused = false;
function updateMotion() {
  const paused = manuallyPaused || motionPreference.matches;
  document.documentElement.classList.toggle('motion-paused', paused);
  motionButton.setAttribute('aria-pressed', String(paused));
  const es = document.documentElement.lang === 'es';
  motionButton.textContent = paused ? (es ? 'Activar animaciones' : 'Play animations') : (es ? 'Pausar animaciones' : 'Pause animations');
  motionButton.disabled = motionPreference.matches;
}
motionButton.hidden = false;
motionButton.addEventListener('click', () => {
  manuallyPaused = !manuallyPaused;
  updateMotion();
});
motionPreference.addEventListener('change', updateMotion);
updateMotion();

// Content stays visible when JavaScript or IntersectionObserver is unavailable.
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.08 });
  document.querySelectorAll('.section-head, .product, .shop-paths a, .nature-grid > *, .ritual-grid > *, .newsletter-grid > *').forEach((element, index) => {
    // Only animate items initially outside the viewport; no initial content flash.
    if (element.getBoundingClientRect().top < innerHeight) return;
    element.classList.add('reveal');
    element.style.setProperty('--reveal-delay', `${(index % 3) * 75}ms`);
    observer.observe(element);
  });
}

// Keep the existing subscription API and confirmation messages on the new home.
const form = document.querySelector('#newsletterForm');
const status = document.querySelector('#formStatus');
const isSpanish = document.documentElement.lang === 'es';
function message(en, es) { return isSpanish ? es : en; }
form.addEventListener('submit', async event => {
  event.preventDefault();
  const email = form.querySelector('input[type=email]');
  const button = form.querySelector('button[type=submit]');
  if (button.disabled) return;
  if (!email.checkValidity()) {
    status.textContent = message('Please check your email — it looks incomplete.', 'Revisa tu correo: parece incompleto.');
    email.focus();
    return;
  }
  button.disabled = true;
  status.textContent = message('Adding you…', 'Añadiéndote…');
  try {
    const response = await fetch('/api/newsletter/subscribe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.value.trim(), lang: isSpanish ? 'es' : 'en' }),
    });
    if (!response.ok) throw new Error('subscribe failed');
    const data = await response.json();
    status.textContent = data.already
      ? message('You were already on the list — the challenge is on its way to your inbox.', 'Ya estabas en la lista: el reto va camino de tu correo.')
      : message('Done! Check your inbox for the 2027 Reading Challenge.', '¡Listo! Revisa tu correo para recibir el Reto de Lectura 2027.');
    form.reset();
  } catch (_) {
    status.textContent = message("That didn't go through. Try again, or email hello@thebookswanderer.com.", 'No se pudo completar. Inténtalo de nuevo o escribe a hello@thebookswanderer.com.');
  } finally {
    button.disabled = false;
  }
});
