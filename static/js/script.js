document.addEventListener("DOMContentLoaded", () => {
    // Live character counter for the activity description
    const desc = document.querySelector("#activity-description");
    const count = document.querySelector("#char-count");
    if (desc && count) {
        const update = () => { count.textContent = desc.value.length; };
        desc.addEventListener("input", update);
        update();
    }

    // Reveal / hide the "Add Custom Deadline" form
    const toggle = document.querySelector("#deadline-toggle");
    const form = document.querySelector("#deadline-form");
    if (toggle && form) {
        toggle.addEventListener("click", () => {
            form.classList.toggle("hidden");
            if (!form.classList.contains("hidden")) form.querySelector("input").focus();
        });
    }

    // AI Picks: show progress while waiting for the AI
    const aiForm = document.querySelector("[data-ai-form]");
    if (aiForm) {
        aiForm.addEventListener("submit", () => {
            const btn = aiForm.querySelector("button[type=submit]");
            btn.disabled = true;
            btn.textContent = "Finding picks…";
            aiForm.querySelector("[data-ai-status]").classList.remove("hidden");
        });
    }

    // Print / Save as PDF buttons
    document.querySelectorAll("[data-print]").forEach((btn) =>
        btn.addEventListener("click", () => window.print()));
});
