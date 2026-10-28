import './styles/tokens.css';
import './styles/app.css';

import jostLatin from '@fontsource-variable/jost/files/jost-latin-wght-normal.woff2?url';
import { render } from 'preact';

import { App } from './app';
import { loadTelegram } from './lib/telegram';
import { boot } from './state/session';

// Jost, latin subset only (Appendix H): one small file, self-hosted, swapped in when ready.
const jost = new FontFace('Jost Variable', `url(${jostLatin}) format('woff2')`, {
  weight: '400 500',
  display: 'swap',
});
document.fonts.add(jost);
void jost.load().catch(() => undefined);

render(<App />, document.getElementById('app')!);
void loadTelegram().then(boot);

if ('serviceWorker' in navigator && location.protocol === 'https:') {
  addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined);
  });
}
