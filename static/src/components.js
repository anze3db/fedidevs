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

customElements.define("theme-toggle", ThemeToggle);
