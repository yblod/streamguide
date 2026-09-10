// Gesehen / bewertet / kein Interesse.
import { api } from '../api.js';
import { h, grid, skeletons, empty } from '../ui.js';

export async function render(root) {
  const f = { status: 'watched', type: '', sort: 'rated', q: '', minRating: '' };
  const results = h('div', {});
  const count = h('span', { class: 'muted small' });
  let items = [];

  const seg = (opts, key, reload = true) => {
    const el = h('div', { class: 'seg' });
    const draw = () => { el.innerHTML = ''; opts.forEach(([v, l]) => el.append(h('button', { class: f[key] === v ? 'active' : '', onClick: () => { f[key] = v; draw(); reload ? load() : show(); } }, l))); };
    draw();
    return el;
  };
  const q = h('input', { type: 'search', placeholder: 'Filtern …', onInput: (e) => { f.q = e.target.value.toLowerCase(); show(); } });
  const minR = h('select', { onChange: (e) => { f.minRating = e.target.value; show(); } },
    ...[['', 'Alle Bewertungen'], ['9', '9–10'], ['8', '8+'], ['7', '7+'], ['6', '6+'], ['1', 'bis 5']].map(([v, l]) => h('option', { value: v }, l)));

  const show = () => {
    let l = items;
    if (f.q) l = l.filter((t) => (t.title || '').toLowerCase().includes(f.q) || (t.original_title || '').toLowerCase().includes(f.q));
    if (f.minRating === '1') l = l.filter((t) => t.user.rating != null && t.user.rating <= 5);
    else if (f.minRating) l = l.filter((t) => t.user.rating != null && t.user.rating >= +f.minRating);
    results.innerHTML = '';
    results.append(grid(l, { noQuick: true, onChange: () => load(), emptyText: items.length ? 'Keine Treffer.' : 'Noch nichts hier. Importiere deine IMDb-Bewertungen in den Einstellungen.', emptyIcon: '✅' }));
    count.textContent = `${l.length} Titel`;
  };
  const load = async () => {
    results.innerHTML = ''; results.append(skeletons(8));
    try {
      const r = await api.library(f.status, f.type || null, f.sort);
      items = r.results;
      show();
    } catch (e) { results.innerHTML = ''; results.append(empty(e.message, '⚠️')); }
  };

  root.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Gesehen ✅'), h('div', { class: 'sub' }, 'Deine Historie und Bewertungen (aus IMDb, TMDB oder manuell).'))),
    h('div', { class: 'glass panel' },
      h('div', { class: 'row spread' },
        h('div', { class: 'row' },
          seg([['watched', 'Gesehen'], ['disliked', 'Kein Interesse'], ['dropped', 'Abgebrochen']], 'status'),
          seg([['', 'Alles'], ['movie', 'Filme'], ['tv', 'Serien']], 'type')),
        h('div', { class: 'row' }, seg([['rated', 'Zuletzt bewertet'], ['rating', 'Beste zuerst'], ['title', 'A–Z'], ['year', 'Jahr']], 'sort'), minR, q, count))),
    h('div', { style: { height: '18px' } }),
    results,
  );
  await load();
  const onJob = (e) => { if (['import_imdb', 'tmdb_sync', 'import_list'].includes(e.detail?.kind)) load(); };
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
