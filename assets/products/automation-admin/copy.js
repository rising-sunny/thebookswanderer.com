document.addEventListener('click', async event => {
  const button=event.target.closest('[data-copy]');
  if (!button) return;
  const field=document.getElementById(button.dataset.copy);
  field.focus();field.select();
  try { await navigator.clipboard.writeText(field.value);button.textContent='Texto copiado'; }
  catch (_) { button.textContent='Seleccionado: copia el texto'; }
});
