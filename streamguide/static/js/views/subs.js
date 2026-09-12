// Abos: aktive Abos/Quellen verwalten und sehen, welche Titel der eigenen Liste bei welchem Anbieter laufen –
// auch bei nicht aktiven Anbietern, als Entscheidungshilfe, ob sich ein neues Abo gerade lohnt.
import { api, IMG } from '../api.js';
import { h, hrow, skeletons, empty, toast, regionBadge, regionName } from '../ui.js';

export async function render(root) {
  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, 'Abos 💳'), h('div', { class: 'sub' }, 'Deine Abos und Quellen verwalten – und sehen, welches Abo sich für deine Watchlist und Serien gerade lohnen würde.')),
    h('a', { class: 'btn', href: '#/settings' }, '🌍 Länder & Einstellungen'));
  root.append(head);

  // ---------- Aktive Abos & Quellen (wie in den Einstellungen) ----------
  const provList = h('div', { class: 'prov-list' });
  const provSearch = h('input', { type: 'search', placeholder: 'Anbieter suchen und aktivieren (z. B. Disney, Paramount, WOW, Joyn) …', style: { width: '100%' } });
  let providers = [];
  const drawProviders = () => {
    provList.innerHTML = '';
    const q = provSearch.value.trim().toLowerCase();
    const list = providers.filter((p) => p.active || (q && p.name.toLowerCase().includes(q)));
    if (!list.length) provList.append(h('span', { class: 'muted small' }, q ? 'Kein Anbieter gefunden.' : 'Keine aktiven Anbieter.'));
    for (const p of list) {
      const abroad = p.region && p.region !== 'DE';
      provList.append(h('div', { class: `prov-item ${p.active ? 'on' : 'off'}`, title: abroad ? `${p.name} in ${regionName(p.region)} – nur per VPN nutzbar` : p.name, onClick: async () => {
        try { await api.toggleProvider(p.id, !p.active, p.region); p.active = !p.active; drawProviders(); toast(`${p.name} ${p.active ? 'aktiviert' : 'deaktiviert'}`, 'ok'); loadCoverage(); }
        catch (e) { toast(e.message, 'err'); }
      } }, p.logo_path ? h('img', { src: IMG(p.logo_path, 'w92'), alt: '' }) : null, p.name, abroad ? regionBadge(p.region, 'inline') : null, h('span', {}, p.active ? '✓' : '+')));
    }
  };
  provSearch.addEventListener('input', drawProviders);
  root.append(h('div', { class: 'glass panel' },
    h('h2', {}, '📡 Meine Abos & Quellen'),
    h('p', { class: 'muted small' }, 'Aktive Anbieter zählen als „meine Anbieter“ (Abo/Flatrate oder kostenlos). Zum Hinzufügen suchen und anklicken, zum Kündigen im Guide einfach abwählen.'),
    provSearch, h('div', { style: { height: '10px' } }), provList));
  try { providers = await api.providers(); drawProviders(); } catch (e) { provList.append(h('span', { class: 'muted small' }, e.message)); }

  // ---------- Abdeckung: was läuft wo ----------
  const activeBox = h('div', {}, skeletons(4));
  const candBox = h('div', {}, skeletons(4));
  root.append(
    h('section', { class: 'section' },
      h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', {}, '✅ Was bei meinen Abos läuft'),
        h('span', { class: 'muted small' }, 'Titel deiner Watchlist und verfolgten Serien je Anbieter')),
      activeBox),
    h('section', { class: 'section' },
      h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', {}, '💡 Lohnt sich ein neues Abo?'),
        h('span', { class: 'muted small' }, 'Diese Titel deiner Liste würden mit dem Anbieter verfügbar – „NUR HIER“ = bei keinem anderen Streaming-Anbieter')),
      candBox),
  );

  const groupEl = (g, reload) => {
    const abroad = g.region && g.region !== 'DE';
    const parts = [];
    if (g.movies) parts.push(`${g.movies} ${g.movies === 1 ? 'Film' : 'Filme'}`);
    if (g.tv) parts.push(`${g.tv} ${g.tv === 1 ? 'Serie' : 'Serien'}`);
    const body = h('div', { class: 'sub-body' }, hrow(g.titles, { onChange: reload, badge: (t) => t.only_here ? 'NUR HIER' : null }));
    const el = h('div', { class: 'glass panel sub-group open' });
    const toggleBtn = h('button', { class: `btn sm ${g.active ? 'ghost' : 'primary'}`, title: g.active ? 'Anbieter deaktivieren (Abo gekündigt)' : 'Anbieter aktivieren (Abo abgeschlossen)', onClick: async (e) => {
      e.stopPropagation();
      try {
        for (const id of g.ids) await api.toggleProvider(id, !g.active, g.region || 'DE');
        toast(`${g.name} ${g.active ? 'deaktiviert' : 'aktiviert'}`, 'ok');
        providers = await api.providers(); drawProviders(); reload();
      } catch (err) { toast(err.message, 'err'); }
    } }, g.active ? 'Deaktivieren' : '＋ Aktivieren');
    el.append(
      h('div', { class: 'sub-head', title: 'Titelreihe ein-/ausklappen', onClick: () => { body.hidden = !body.hidden; el.classList.toggle('open', !body.hidden); } },
        g.logo ? h('img', { src: IMG(g.logo, 'w92'), alt: '' }) : h('span', { style: { width: '44px' } }),
        h('div', { class: 'grow' },
          h('div', { class: 'n' }, g.name, abroad ? regionBadge(g.region, 'inline') : null, g.free ? h('span', { class: 'muted small', style: { marginLeft: '8px', fontWeight: 600 } }, 'kostenlos') : null),
          h('div', { class: 'c' }, parts.join(' · ') || 'keine Titel', ' von deiner Liste', g.exclusive ? h('span', { class: 'excl' }, ` · ${g.exclusive} davon nur hier`) : null)),
        h('div', { class: 'n', style: { fontSize: '1.4rem' } }, g.count),
        toggleBtn,
        h('span', { class: 'arrow' }, '▶')),
      body);
    return el;
  };

  async function loadCoverage() {
    try {
      const d = await api.subs();
      const reload = () => loadCoverage();
      activeBox.innerHTML = '';
      candBox.innerHTML = '';
      if (d.active.length) d.active.forEach((g) => activeBox.append(groupEl(g, reload)));
      else activeBox.append(empty('Kein Titel deiner Liste läuft gerade bei deinen aktiven Anbietern.', '📡'));
      if (d.candidates.length) d.candidates.forEach((g) => candBox.append(groupEl(g, reload)));
      else candBox.append(empty('Keine weiteren Anbieter mit Titeln deiner Liste bekannt.', '💡'));
    } catch (e) {
      activeBox.innerHTML = ''; candBox.innerHTML = '';
      activeBox.append(empty(e.message, '⚠️'));
    }
  }
  await loadCoverage();
  const onJob = (e) => { if (['refresh_library', 'import_imdb', 'import_list', 'tmdb_sync'].includes(e.detail?.kind)) loadCoverage(); };
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
