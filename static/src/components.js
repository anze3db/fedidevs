if (
	localStorage.getItem("theme") === "dark" ||
	(!("theme" in localStorage) &&
		window.matchMedia("(prefers-color-scheme: dark)").matches)
) {
	document.documentElement.classList.add("dark");
} else {
	document.documentElement.classList.remove("dark");
}

class ThemeToggle extends HTMLElement {
	constructor() {
		super();
		this.button = this.querySelector("button");
		this.button.addEventListener("click", this.toggleTheme.bind(this));
		if (
			localStorage.theme === "dark" ||
			(!("theme" in localStorage) &&
				window.matchMedia("(prefers-color-scheme: dark)").matches)
		) {
			document.documentElement.classList.add("dark");
		} else {
			document.documentElement.classList.remove("dark");
		}
	}
	toggleTheme() {
		document.documentElement.classList.toggle("dark");
		localStorage.setItem(
			"theme",
			document.documentElement.classList.contains("dark") ? "dark" : "light",
		);
	}
}
window.addEventListener("DOMContentLoaded", () => {
	customElements.define("theme-toggle", ThemeToggle);
	setupCsrfBootstrap();
});

// Anonymous pages are served without a csrftoken cookie so Cloudflare can
// cache them. Fetch a fresh cookie+token from /csrf/ before any same-origin
// POST so login, language switch, subscribe, and remote-follow still work.
function setupCsrfBootstrap() {
	const csrfUrl = document.body && document.body.dataset.csrfUrl;
	if (!csrfUrl) {
		return;
	}

	let tokenPromise = null;

	function ensureCsrfToken() {
		if (!tokenPromise) {
			tokenPromise = fetch(csrfUrl, { credentials: "same-origin" })
				.then((response) => {
					if (!response.ok) {
						throw new Error("Failed to fetch CSRF token");
					}
					return response.json();
				})
				.then((data) => {
					window.__csrfToken = data.csrfToken;
					return data.csrfToken;
				})
				.catch((error) => {
					tokenPromise = null;
					throw error;
				});
		}
		return tokenPromise;
	}

	function setFormToken(form, token) {
		let input = form.querySelector("input[name=csrfmiddlewaretoken]");
		if (!input) {
			input = document.createElement("input");
			input.type = "hidden";
			input.name = "csrfmiddlewaretoken";
			form.appendChild(input);
		}
		input.value = token;
	}

	function isSameOriginForm(form) {
		try {
			return new URL(form.action, window.location.href).origin === window.location.origin;
		} catch {
			return true;
		}
	}

	function isFormRelated(element) {
		return Boolean(
			element.closest("form") ||
				element.closest("[data-modal-toggle='authentication-modal']") ||
				element.closest("[data-dropdown-toggle='lang_dropdown']"),
		);
	}

	document.addEventListener("pointerdown", (event) => {
		if (isFormRelated(event.target)) {
			ensureCsrfToken().catch(() => {});
		}
	});
	document.addEventListener("focusin", (event) => {
		if (isFormRelated(event.target)) {
			ensureCsrfToken().catch(() => {});
		}
	});

	document.addEventListener("submit", async (event) => {
		const form = event.target;
		if (!(form instanceof HTMLFormElement)) {
			return;
		}
		if (form.method.toLowerCase() !== "post") {
			return;
		}
		if (!isSameOriginForm(form)) {
			return;
		}
		if (form.dataset.csrfReady === "1") {
			return;
		}

		event.preventDefault();
		const submitter = event.submitter;
		try {
			const token = await ensureCsrfToken();
			setFormToken(form, token);
		} catch {
			// Fall through and submit with whatever token is already in the form.
		}
		form.dataset.csrfReady = "1";
		form.requestSubmit(submitter);
	});

	document.body.addEventListener("htmx:configRequest", (event) => {
		if (!window.__csrfToken) {
			return;
		}
		const verb = (event.detail.verb || "").toLowerCase();
		if (verb === "get" || verb === "head" || verb === "") {
			return;
		}
		event.detail.headers["X-CSRFToken"] = window.__csrfToken;
	});
}

// Make elements with a data-href attribute (e.g. table rows) clickable,
// while leaving real links/buttons and text selection alone.
document.addEventListener("click", (event) => {
	const row = event.target.closest("[data-href]");
	if (!row) return;
	if (event.target.closest("a, button")) return;
	if (window.getSelection().toString()) return;
	window.location = row.dataset.href;
});

window.addEventListener("scroll", () => {
	if (window.scrollY > 0) {
		document.getElementById('top-bar').classList.add('shadow-lg');
	} else {
		document.getElementById('top-bar').classList.remove('shadow-lg');
	}
});
