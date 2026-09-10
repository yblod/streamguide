// Suche nach Filmen und Serien (TMDB) mit Verfügbarkeit.
import { api } from '../api.js';
import { h, grid, skeletons, empty } from '../ui.js';

export async function render(root, params) {
  const input = h('input', { type: 'search', placeholder: 'Film oder Serie suchen …', value: params.q || '', autofocus: true });
  const results = h('div', {});
  const more = h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '18px' } });
  let items = [], page = 1, totalPages = 1, seq = 0;

  const run = async (append = false) => {
    const q = input.value.trim();
    if (!q) { results.innerHTML = ''; more.innerHTML = ''; return; }
    const my = ++seq;
    if (!append) { page = 1; items = []; results.innerHTML = ''; results.append(skeletons(8)); history.replaceState(null, '', `#/search?q=${encodeURIComponent(q)}`); }
    more.innerHTML = '';
    more.append(h('span', { class: 'spinner' }));
    try {
      const r = await api.search(q, page);
      if (my !== seq) return;
      items = append ? [...items, ...r.results] : r.results;
      totalPages = r.total_pages;
      draw();
    } catch (e) {
      if (my !== seq) return;
      results.innerHTML = ''; more.innerHTML = '';
      results.append(empty(e.status === 428 ? 'Bitte zuerst den TMDB-Schlüssel in den Einstellungen hinterlegen.' : e.message, '⚠️'));
    }
  };
  const draw = () => {
    results.innerHTML = '';
    results.append(grid(items, { onChange: (t) => { if (t) items = items.map((x) => x.media_type === t.media_type && x.tmdb_id === t.tmdb_id ? t : x); draw(); }, emptyText: 'Nichts gefunden.' }));
    more.innerHTML = '';
    if (page < totalPages) more.append(h('button', { class: 'btn primary', onClick: () => { page += 1; run(true); } }, 'Mehr laden'));
  };

  let timer;
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => run(), 400); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { clearTimeout(timer); run(); } });

  root.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Suche 🔍'), h('div', { class: 'sub' }, 'Titel finden und sehen, wo sie in Deutschland laufen.'))),
    h('div', { class: 'glass panel' }, h('div', { class: 'searchbar' }, input, h('button', { class: 'btn primary', onClick: () => run() }, 'Suchen'))),
    h('div', { style: { height: '18px' } }),
    results, more,
  );
  if (input.value) run();
  setTimeout(() => input.focus(), 50);
  return {};
}
