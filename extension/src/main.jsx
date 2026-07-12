import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

// 1. Create a shadow host element to isolate styles perfectly from YouTube
const shadowHost = document.createElement('div');
shadowHost.id = 'brand-guardian-root';
document.body.appendChild(shadowHost);

// 2. Attach a shadow root boundary
const shadowRoot = shadowHost.attachShadow({ mode: 'open' });
const reactContainer = document.createElement('div');
shadowRoot.appendChild(reactContainer);

// 3. Pull the compiled CSS directly into the shadow root wrapper
const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = chrome.runtime.getURL('content.css');
shadowRoot.appendChild(link);

// 4. Mount React safely inside the isolated container
ReactDOM.createRoot(reactContainer).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);