import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { isTvBrowser } from "./lib/device";

// TV browsers scroll the page, not boxes inside it; app.css adapts layouts under .tv.
document.documentElement.classList.toggle("tv", isTvBrowser(navigator.userAgent));

const target = document.getElementById("app");
if (!target) throw new Error("Missing #app element");

const app = mount(App, { target });

export default app;
