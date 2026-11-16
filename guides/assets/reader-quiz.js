/* "What kind of reader are you?" quiz. Pure client-side: it tallies the chosen options, shows the matching result
   block, and points the shared sign-up box at that type (data-source = "quiz-<type>"), so the welcome series can
   send the right free gift. Results are shareable through the URL hash (#cozy, #annotator, ...). */
(function () {
    var root = document.getElementById("readerQuiz");
    if (!root) return;
    var lang = root.getAttribute("data-lang") === "es" ? "es" : "en";
    var TYPES = ["cozy", "annotator", "wanderer", "challenger", "classic"];
    var form = root.querySelector(".rq-form");
    var questions = [].slice.call(form.querySelectorAll(".rq-q"));
    var bar = root.querySelector(".rq-progress__bar");
    var count = root.querySelector(".rq-progress__text");
    var submit = form.querySelector(".rq-submit");
    var intro = root.querySelector(".rq-intro");
    var results = [].slice.call(root.querySelectorAll(".rq-result"));
    var box = document.getElementById("quizSignup");
    var retake = root.querySelectorAll(".rq-retake");

    function answered() {
        return questions.filter(function (q) { return q.querySelector("input:checked"); }).length;
    }
    function update() {
        var n = answered();
        bar.style.width = (n / questions.length * 100) + "%";
        count.textContent = n + " / " + questions.length;
        submit.disabled = n < questions.length;
        questions.forEach(function (q) {
            [].forEach.call(q.querySelectorAll(".rq-opt"), function (o) {
                o.classList.toggle("is-on", o.querySelector("input").checked);
            });
        });
    }
    function winner() {
        var score = {}, first = {};
        TYPES.forEach(function (t) { score[t] = 0; });
        questions.forEach(function (q, i) {
            var c = q.querySelector("input:checked");
            if (!c) return;
            score[c.value] += 1;
            if (first[c.value] === undefined) first[c.value] = i;
        });
        var best = null;
        TYPES.forEach(function (t) {
            if (!score[t]) return;
            if (best === null || score[t] > score[best] || (score[t] === score[best] && first[t] < first[best])) best = t;
        });
        return best;
    }
    function show(type, fromQuiz) {
        var block = root.querySelector('.rq-result[data-type="' + type + '"]');
        if (!block) return;
        results.forEach(function (r) { r.hidden = r !== block; });
        form.hidden = true;
        if (intro) intro.hidden = true;
        if (box) {
            box.hidden = false;
            box.querySelector("form").setAttribute("data-source", block.getAttribute("data-source"));
            box.querySelector(".rq-gift-title").textContent = block.getAttribute("data-gift-title");
            box.querySelector(".rq-gift-text").textContent = block.getAttribute("data-gift-text");
        }
        try { history.replaceState(null, "", "#" + type); } catch (_) { /* The result still shows. */ }
        var h = block.querySelector("h2");
        if (h) { h.setAttribute("tabindex", "-1"); h.focus({preventScroll: true}); }
        root.scrollIntoView({behavior: "smooth", block: "start"});
        if (fromQuiz) {
            try {
                if (window.tbwTrack) window.tbwTrack("quiz_complete", {extra: {type: type, lang: lang}});
            } catch (_) { /* Analytics must not change the result. */ }
        }
    }
    function reset() {
        form.reset();
        form.hidden = false;
        if (intro) intro.hidden = false;
        results.forEach(function (r) { r.hidden = true; });
        if (box) box.hidden = true;
        try { history.replaceState(null, "", location.pathname + location.search); } catch (_) { /* Optional. */ }
        update();
        root.scrollIntoView({behavior: "smooth", block: "start"});
    }

    form.addEventListener("change", update);
    form.addEventListener("submit", function (e) {
        e.preventDefault();
        var t = winner();
        if (answered() === questions.length && t) show(t, true);
    });
    [].forEach.call(retake, function (b) { b.addEventListener("click", reset); });
    update();
    var hash = (location.hash || "").replace("#", "");
    if (TYPES.indexOf(hash) !== -1) show(hash, false);
})();
