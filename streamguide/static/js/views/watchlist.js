// Watchlist mit Verfügbarkeits-Filter.
import { api } from '../api.js';
import { h, grid, skeletons, empty, toast } from '../ui.js';

export async function render(root, params) {
  const f = { only: params.only || 'all', type: '', sort: 'added' };
  const results = h('div', {});
  const count = h('span', { class: 'muted small' });
  let items = [];

  const seg = (opts, key) => {
    const el = h('div', { class: 'seg' });
    const draw = () => { el.innerHTML = ''; opts.forEach(([v, l]) => el.append(h('button', { class: f[key] === v ? 'active' : '', onClick: () => { f[key] = v; draw(); key === 'sort' || key === 'type' ? load() : show(); } }, l))); };
    draw();
    return el;
  };

  const show = () => {
    let list = items;
    if (f.only === 'available') list = list.filter((t) => t.availability?.mine);
    else if (f.only === 'free') list = list.filter((t) => t.availability?.mode === 'free');
    else if (f.only === 'other') list = list.filter((t) => ['other_sub', 'rent'].includes(t.availability?.mode));
    else if (f.only === 'none') list = list.filter((t) => !t.availability || t.availability.mode === 'none');
    results.innerHTML = '';
    results.append(grid(list, { onChange: () => load(), emptyText: items.length ? 'Keine Titel in dieser Kategorie.' : 'Die Watchlist ist leer – Titel per Suche hinzufügen oder in den Einstellungen importieren.', emptyIcon: '🔖' }));
    count.textContent = `${list.length} von ${items.length}`;
  };
  const load = async () => {
    results.innerHTML = ''; results.append(skeletons(8));
    try {
      const r = await api.library('watchlist', f.type || null, f.sort);
      items = r.results;
      show();
    } catch (e) { results.innerHTML = ''; results.append(empty(e.message, '⚠️')); }
  };

  root.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', {}, 'Watchlist 🔖'), h('div', { class: 'sub' }, 'Filme, die du sehen willst – und wo sie gerade laufen. Serien findest du unter „Serien“.')),
      h('button', { class: 'btn', onClick: async () => { try { await api.post('/library/refresh'); toast('Aktualisierung gestartet'); } catch (e) { toast(e.message, 'err'); } } }, '↻ Verfügbarkeit aktualisieren')),
    h('div', { class: 'glass panel row spread' },
      h('div', { class: 'row' },
        seg([['all', 'Alle'], ['available', 'Bei meinen Anbietern'], ['free', 'Kostenlos'], ['other', 'Anderes Abo / Leihen'], ['none', 'Nicht verfügbar']], 'only')),
      h('div', { class: 'row' }, seg([['added', 'Neueste'], ['title', 'A–Z'], ['year', 'Jahr']], 'sort'), count)),
    h('div', { style: { height: '18px' } }),
    results,
  );
  await load();
  const onJob = (e) => { if (['refresh_library', 'import_imdb', 'import_list', 'tmdb_sync'].includes(e.detail?.kind)) load(); };
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
