// auth.js - Clerk integration, gated on a publishable key.
//
// If CLERK_PUBLISHABLE_KEY is set in the backend .env, this loads Clerk's
// browser SDK and wires sign-in / user button. If not, the app runs in open
// demo mode and the auth buttons simply lead into the app.

(async function () {
  const slot = document.getElementById("user-slot");
  const signinBtn = document.getElementById("signin-btn");
  const demoBtn = document.getElementById("demo-btn");
  const isAppPage = location.pathname.startsWith("/app");

  let cfg = { clerk_enabled: false, clerk_publishable_key: "" };
  try { cfg = await (await fetch("/api/config")).json(); } catch (_) {}

  // --- demo mode (no key) ---------------------------------------------------
  if (!cfg.clerk_enabled) {
    if (signinBtn) {
      signinBtn.addEventListener("click", (e) => {
        if (isAppPage) {
          e.preventDefault();
          alert("Logins are off in demo mode.\nAdd CLERK_PUBLISHABLE_KEY to .env to enable Clerk sign-in.");
        }
      });
    }
    return;
  }

  // --- Clerk enabled --------------------------------------------------------
  try {
    await loadClerk(cfg.clerk_publishable_key);
    await window.Clerk.load();
    const Clerk = window.Clerk;

    function paint() {
      if (Clerk.user) {
        if (slot) { slot.classList.remove("cl-hidden"); slot.innerHTML = ""; Clerk.mountUserButton(slot); }
        signinBtn && signinBtn.classList.add("cl-hidden");
        demoBtn && (demoBtn.textContent = "Open app", demoBtn.setAttribute("href", "/app"));
      } else {
        slot && slot.classList.add("cl-hidden");
        signinBtn && signinBtn.classList.remove("cl-hidden");
        if (signinBtn) signinBtn.addEventListener("click", (e) => { e.preventDefault(); Clerk.openSignIn(); }, { once: false });
        if (demoBtn) demoBtn.addEventListener("click", (e) => { e.preventDefault(); Clerk.openSignUp(); });
      }
    }
    paint();
    Clerk.addListener(paint);

    // Soft gate the app: prompt sign-in, but don't hard-lock the demo.
    if (isAppPage && !Clerk.user) Clerk.openSignIn();
  } catch (err) {
    console.warn("Clerk failed to load; continuing in open mode.", err);
  }

  function loadClerk(pk) {
    return new Promise((resolve, reject) => {
      if (window.Clerk) return resolve();
      const s = document.createElement("script");
      s.async = true;
      s.crossOrigin = "anonymous";
      s.setAttribute("data-clerk-publishable-key", pk);
      s.src = "https://cdn.jsdelivr.net/npm/@clerk/clerk-js@5/dist/clerk.browser.js";
      s.addEventListener("load", resolve);
      s.addEventListener("error", reject);
      document.head.appendChild(s);
    });
  }
})();
