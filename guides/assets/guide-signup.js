/* Free 2027 Reading Challenge sign-up box inside the reading-challenge guides.
   Same endpoint and messages as the challenge page; `data-source` tells the lists apart. */
(function () {
    var MSG = {
        en: {
            ok: "Request received. We will try to send the PDF by email. If it does not arrive, contact hello@thebookswanderer.com.",
            none: "No new email was scheduled. If you need the PDF, contact hello@thebookswanderer.com.",
            err: "That didn't go through. Try again, or email hello@thebookswanderer.com."
        },
        es: {
            ok: "Solicitud recibida. Intentaremos enviarte el PDF por correo. Si no llega, escribe a hello@thebookswanderer.com.",
            none: "No se programó ningún correo nuevo. Si necesitas el PDF, escribe a hello@thebookswanderer.com.",
            err: "No se pudo enviar. Inténtalo de nuevo o escribe a hello@thebookswanderer.com."
        }
    };
    [].forEach.call(document.querySelectorAll("form[data-guide-signup]"), function (form) {
        var lang = form.getAttribute("data-lang") === "es" ? "es" : "en", m = MSG[lang];
        var email = form.querySelector("input[type=email]"), btn = form.querySelector("button");
        var status = form.parentNode.querySelector(".j-signup__status");
        form.addEventListener("submit", function (e) {
            e.preventDefault();
            if (!email.value || !email.checkValidity()) { email.focus(); return; }
            btn.disabled = true;
            fetch("/api/newsletter/subscribe", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify({email: email.value.trim(), lang: lang, source: form.getAttribute("data-source") || "guide"})
            })
              .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
              .then(function (d) {
                  if (d.ok !== true) throw new Error();
                  status.textContent = d.email_status === "queued" ? m.ok : m.none;
                  form.reset();
                  try {
                      if (window.tbwTrack) window.tbwTrack("challenge_request", {extra: {
                          lang: lang, already: d.already === true,
                          email_status: d.email_status === "queued" ? "queued" : "not_queued"
                      }});
                  } catch (_) { /* Analytics must not change the form result. */ }
              })
              .catch(function () { status.textContent = m.err; })
              .finally(function () { btn.disabled = false; });
        });
    });
})();
