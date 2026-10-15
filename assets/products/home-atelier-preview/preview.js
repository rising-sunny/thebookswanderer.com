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
  motionButton.textContent = paused ? motionButton.dataset.play : motionButton.dataset.pause;
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
