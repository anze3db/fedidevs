const colors = require("tailwindcss/colors");

/** @type {import('tailwindcss').Config} */
module.exports = {
	darkMode: "class",
	content: ["./accounts/templates/**/*.html"],
	theme: {
		extend: {
			colors: {
				primary: colors.slate,
			},
			fontFamily: {
				sans: ["Inter", "Helvetica Neue", "Helvetica", "Arial", "sans-serif"],
			},
		},
	},
	plugins: [
		require("@tailwindcss/typography"),
		require("@tailwindcss/forms"),
		require("@tailwindcss/aspect-ratio"),
		require("@tailwindcss/container-queries"),
	],
};
