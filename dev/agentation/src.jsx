import React from "react";
import { createRoot } from "react-dom/client";
import { Agentation } from "agentation";

const KEY = "__morphicAgentation";
if (window[KEY]) {
  window[KEY].remove();
} else {
  const host = document.createElement("div");
  host.id = "morphic-dev-agentation";
  document.body.appendChild(host);
  const root = createRoot(host);
  const state = {
    version: "3.1.2",
    lastOutput: "",
    remove() {
      root.unmount();
      host.remove();
      delete window[KEY];
    },
  };
  window[KEY] = state;
  root.render(<Agentation
    appName="Local browser feedback"
    enableKeyboardShortcuts={false}
    onCopy={(output) => { state.lastOutput = output; }}
  />);
}
