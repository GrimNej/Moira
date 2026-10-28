import { describe, expect, it } from 'vitest';

import { linkPieces } from '../src/lib/format';

describe('linkPieces', () => {
  it('links http and https URLs and keeps the rest as text', () => {
    const p = linkPieces('see https://example.com/a?b=1, and http://x.test.');
    expect(p).toEqual([
      { text: 'see ' },
      { text: 'https://example.com/a?b=1', href: 'https://example.com/a?b=1' },
      { text: ', and ' },
      { text: 'http://x.test', href: 'http://x.test/' },
      { text: '.' },
    ]);
  });

  it('never links other schemes', () => {
    for (const t of ['javascript:alert(1)', 'data:text/html,<b>x</b>', 'file:///etc/passwd']) {
      expect(linkPieces(t).every((p) => !p.href)).toBe(true);
    }
  });

  it('plain text stays one piece', () => {
    expect(linkPieces('buy oat milk')).toEqual([{ text: 'buy oat milk' }]);
  });
});
