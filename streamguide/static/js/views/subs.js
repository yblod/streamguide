// Abos: 1. Diese Abos und Quellen habe ich (verwalten) – 2. Was würden weitere Abos bringen? Je nicht aktivem
// Anbieter die Titel der eigenen Liste, die man damit zusätzlich sehen könnte (ohne Gesehenes und ohne das, was
// bei den eigenen Anbietern schon läuft); „NUR HIER“ = kein anderer Streaming-Anbieter hat den Titel.
import { api, IMG } from '../api.js';
import { h, hrow, skeletons, empty, toast, regionBadge, regionName } from '../ui.js';

export async function render(root) {
  let st = null;
  try { st = await api.status(); } catch { /* ohne Status weiter */ }
  const ro = !(st?.profile?.is_main ?? true);  // Nebenprofile sehen die Abos, ändern sie aber nicht
  root.append(h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, 'Abos 💳'), h('div', { class: 'sub' }, 'Welche Abos und Quellen du hast – und was dir weitere Abos für deine Watchlist und Serien bringen würden.')),
    h('a', { class: 'btn', href: '#/settings' }, '🌍 Länder (VPN)')));

  const mineBox = h('div', { class: 'sub-mine' }, skeletons(3));
  const addInput = h('input', { type: 'search', placeholder: 'Abo oder Quelle hinzufügen … (z. B. Disney, Paramount, WOW, Joyn, ZDF)', style: { width: '100%' } });
  const addBox = h('div', { class: 'sub-add' });
  const candBox = h('div', {}, skeletons(4));
  let data = null;

  const freeToggle = h('label', { class: 'toggle small', style: { marginTop: '14px' } },
    h('input', { type: 'checkbox', checked: !!st?.settings?.count_all_free, onChange: async (e) => {
      try { await api.settings({ count_all_free: e.target.checked }); toast('Gespeichert', 'ok'); load(); } catch (err) { toast(err.message, 'err'); }
    } }),
    h('span', { class: 'sw' }), 'Kostenlose Angebote aller Anbieter (z. B. Joyn, Pluto TV) als verfügbar zählen');

  root.append(
    h('section', { class: 'section' },
      h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', {}, '1 · Diese Abos & Quellen habe ich'),
        h('span', { class: 'muted small' }, 'Titel gelten als „bei meinen Anbietern“, wenn sie hier laufen')),
      mineBox,
      ro ? h('p', { class: 'muted small' }, 'Abos ändern kann nur das Hauptprofil.') : h('div', { class: 'glass panel', style: { marginTop: '4px' } }, addInput, addBox, freeToggle)),
    h('section', { class: 'section' },
      h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', {}, '2 · Was würden weitere Abos bringen?'),
        h('span', { class: 'muted small' }, 'Nur Titel deiner Liste, die du noch nicht sehen kannst · „NUR HIER“ = bei keinem anderen Anbieter')),
      candBox),
  );

  // Anbieter (Familie) aktivieren/deaktivieren: alle Varianten gemeinsam
  const setActive = async (g, active) => {
    for (const id of g.ids) await api.toggleProvider(id, active, g.region || 'DE');
    toast(`${g.name} ${active ? 'aktiviert' : 'deaktiviert'}`, 'ok');
    await load();
  };

  const nameEl = (g) => h('div', { class: 'n' }, g.name, g.region ? regionBadge(g.region, 'inline') : null,
    g.free ? h('span', { class: 'muted small', style: { marginLeft: '8px', fontWeight: 600 } }, 'kostenlos') : null);
  const logoEl = (g) => g.logo ? h('img', { src: IMG(g.logo, 'w92'), alt: '' }) : h('span', { style: { width: '44px' } });

  const mineRow = (g) => h('div', { class: 'glass panel sub-group static' },
    h('div', { class: 'sub-head' }, logoEl(g), h('div', { class: 'grow' }, nameEl(g)),
      ro ? null : h('button', { class: 'btn sm ghost', title: 'Abo gekündigt / Quelle nicht mehr nutzen', onClick: () => setActive(g, false).catch((e) => toast(e.message, 'err')) }, 'Deaktivieren')));

  const drawAdd = () => {
    addBox.innerHTML = '';
    const q = addInput.value.trim().toLowerCase();
    if (!q || !data) return;
    const hits = data.providers.filter((g) => !g.active && g.name.toLowerCase().includes(q)).slice(0, 24);
    if (!hits.length) { addBox.append(h('span', { class: 'muted small' }, 'Kein Anbieter gefunden.')); return; }
    for (const g of hits) {
      addBox.append(h('div', { class: 'prov-item off', title: g.region ? `${g.name} in ${regionName(g.region)} – nur per VPN nutzbar` : g.name,
        onClick: () => setActive(g, true).then(() => { addInput.value = ''; drawAdd(); }).catch((e) => toast(e.message, 'err')) },
        g.logo ? h('img', { src: IMG(g.logo, 'w92'), alt: '' }) : null, g.name, g.region ? regionBadge(g.region, 'inline') : null, h('span', {}, '+')));
    }
  };
  addInput.addEventListener('input', drawAdd);

  const candRow = (g, reload) => {
    const parts = [];
    if (g.movies) parts.push(`${g.movies} ${g.movies === 1 ? 'Film' : 'Filme'}`);
    if (g.tv) parts.push(`${g.tv} ${g.tv === 1 ? 'Serie' : 'Serien'}`);
    const body = h('div', { class: 'sub-body' }, hrow(g.titles, { onChange: reload, badge: (t) => t.only_here ? 'NUR HIER' : null }));
    const el = h('div', { class: 'glass panel sub-group open' });
    el.append(
      h('div', { class: 'sub-head', title: 'Titelreihe ein-/ausklappen', onClick: () => { body.hidden = !body.hidden; el.classList.toggle('open', !body.hidden); } },
        logoEl(g),
        h('div', { class: 'grow' }, nameEl(g),
          h('div', { class: 'c' }, parts.join(' · '), ' zusätzlich sehbar', g.exclusive ? h('span', { class: 'excl' }, ` · ${g.exclusive} davon nur hier`) : null)),
        h('div', { class: 'n', style: { fontSize: '1.4rem' } }, g.count),
        ro ? null : h('button', { class: 'btn sm primary', title: 'Abo abgeschlossen – ab jetzt als „meine Anbieter“ zählen', onClick: (e) => { e.stopPropagation(); setActive(g, true).catch((err) => toast(err.message, 'err')); } }, '＋ Aktivieren'),
        h('span', { class: 'arrow' }, '▶')),
      body);
    return el;
  };

  async function load() {
    try {
      data = await api.subs();
      const reload = () => load();
      mineBox.innerHTML = '';
      candBox.innerHTML = '';
      if (data.mine.length) data.mine.forEach((g) => mineBox.append(mineRow(g)));
      else mineBox.append(empty('Noch kein Abo oder keine Quelle aktiv – unten hinzufügen.', '📡'));
      if (data.candidates.length) data.candidates.forEach((g) => candBox.append(candRow(g, reload)));
      else candBox.append(empty('Alles auf deiner Liste kannst du schon sehen – oder es ist nirgends im Stream.', '💡'));
      drawAdd();
    } catch (e) {
      mineBox.innerHTML = ''; candBox.innerHTML = '';
      mineBox.append(empty(e.status === 428 ? 'Bitte zuerst den TMDB-Schlüssel in den Einstellungen hinterlegen.' : e.message, '⚠️'));
    }
  }
  await load();
  const onJob = (e) => { if (['refresh_library', 'import_imdb', 'import_list', 'tmdb_sync'].includes(e.detail?.kind)) load(); };
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
