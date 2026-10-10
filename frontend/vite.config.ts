import { defineConfig } from 'vite';

// Electron loads the production build from file://, so asset URLs must be
// relative (./assets/...). With Vite's default base ('/') the packaged window
// was blank: the browser looked for C:/assets/*.js.
export default defineConfig({
  base: './',
  server: { port: 5173, strictPort: true }, // main.js trusts exactly this dev origin
});
