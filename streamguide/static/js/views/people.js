// Schauspieler: eigene Suche, meine Favoriten, im Trend, Neuerscheinungen von Favoriten.
import { api, IMG } from '../api.js';
import { h, openPerson, hrow, section, empty, toast, loadFavSet, markFavorite } from '../ui.js';

export async function render(root) {
  const input = h('input', { type: 'search', placeholder: 'Schauspieler oder Schauspielerin suchen …' });
  const searchBox = h('div', {});
  const favBox = h('div', {}, h('span', { class: 'spinner' }));
  const newBox = h('div', {}, h('span', { class: 'spinner' }));
  const trendBox = h('div', {}, h('span', { class: 'spinner' }));
  const blockedWrap = h('div', { class: 'hidden', style: { marginTop: '22px' } });
  let blockedOpen = false;
  const loadBlocked = async () => {
    try {
      const r = await api.peopleBlocked();
      blockedWrap.innerHTML = '';
      if (!r.results.length) { blockedWrap.classList.add('hidden'); return; }
      blockedWrap.classList.remove('hidden');
      const body = h('div', { class: `people-grid blocked-grid ${blockedOpen ? '' : 'hidden'}`, style: { marginTop: '12px' } },
        ...r.results.map((p) => {
          const card = h('div', { class: 'person-card blocked', onClick: () => openPerson(p.id, loadBlocked) },
            h('div', { class: 'photo' }, p.profile_path ? h('img', { src: IMG(p.profile_path, 'w342'), loading: 'lazy', alt: '' }) : h('div', { class: 'noposter' }, '👤'),
              h('button', { class: 'q unblock', title: 'Sperre aufheben', onClick: async (e) => {
                e.stopPropagation();
                try { await api.setBlocked(p.id, false); toast(`${p.name} wieder freigegeben`, 'ok'); loadBlocked(); } catch (err) { toast(err.message, 'err'); }
              } }, '🚫')),
            h('div', { class: 'n' }, p.name),
            h('div', { class: 'k' }, 'Klick auf 🚫 gibt frei'));
          return card;
        }));
      const head = h('div', { class: 'glass collapsed-row', onClick: () => { blockedOpen = !blockedOpen; body.classList.toggle('hidden', !blockedOpen); head.lastChild.textContent = blockedOpen ? '▴' : '▾'; } },
        h('span', { class: 'muted' }, `🚫 Nicht mein Fall (${r.results.length})`), h('span', { class: 'grow' }), h('span', { class: 'muted small' }, blockedOpen ? '▴' : '▾'));
      blockedWrap.append(head, body);
    } catch { blockedWrap.classList.add('hidden'); }
  };
  const favCount = h('span', { class: 'muted small' });
  let seq = 0;
  let favItems = [];
  const ff = { gender: 'all', sort: 'name_asc' };
  const favSeg = (opts, key) => {
    const el = h('div', { class: 'seg' });
    const draw = () => { el.innerHTML = ''; opts.forEach(([v, l]) => el.append(h('button', { class: ff[key] === v ? 'active' : '', onClick: () => { ff[key] = v; draw(); showFavs(); } }, l))); };
    draw();
    return el;
  };
  const favControls = h('div', { class: 'row' },
    favSeg([['all', 'Alle'], ['1', 'Frauen'], ['2', 'Männer']], 'gender'),
    favSeg([['name_asc', 'A–Z'], ['name_desc', 'Z–A'], ['age_asc', 'Alter ↑'], ['age_desc', 'Alter ↓']], 'sort'),
    favCount);
  const showFavs = () => {
    let l = favItems;
    if (ff.gender !== 'all') l = l.filter((p) => String(p.gender) === ff.gender);
    const byName = (a, b) => a.name.localeCompare(b.name, 'de');
    const byAge = (a, b) => (a.age ?? 999) - (b.age ?? 999);
    l = [...l].sort(ff.sort === 'name_asc' ? byName : ff.sort === 'name_desc' ? (a, b) => byName(b, a)
      : ff.sort === 'age_asc' ? byAge : (a, b) => ((b.age ?? -1) - (a.age ?? -1)));
    favBox.innerHTML = '';
    favCount.textContent = ff.gender === 'all' ? `${favItems.length}` : `${l.length} von ${favItems.length}`;
    favBox.append(l.length ? grid(l, loadFavs, true) : empty(favItems.length ? 'Keine Treffer in dieser Auswahl.' : 'Noch keine Favoriten. Suche oben nach Personen oder importiere deine IMDb-Liste in den Einstellungen.', '🎭'));
  };

  const personCard = (p, onChange, showAge = false) => {
    const card = h('div', { class: `person-card ${p.favorite ? 'fav' : ''}`, onClick: () => openPerson(p.id, onChange) },
      h('div', { class: 'photo' }, p.profile_path ? h('img', { src: IMG(p.profile_path, 'w342'), loading: 'lazy', alt: '' }) : h('div', { class: 'noposter' }, '👤'),
        h('button', { class: 'q star', title: p.favorite ? 'Aus Favoriten entfernen' : 'Zu meinen Schauspielern', onClick: async (e) => {
          e.stopPropagation();
          try { const r = await api.setFavorite(p.id, !p.favorite); p.favorite = r.favorite; markFavorite(p.id, r.favorite); card.classList.toggle('fav', r.favorite); toast(r.favorite ? `${p.name} hinzugefügt` : `${p.name} entfernt`, 'ok'); loadFavs(); }
          catch (err) { toast(err.message, 'err'); }
        } }, '★')),
      h('div', { class: 'n' }, p.name),
      showAge && p.age != null ? h('div', { class: 'k' }, `${p.deathday ? '† ' : ''}${p.age} Jahre`) :
        (p.known_for?.length ? h('div', { class: 'k' }, p.known_for.slice(0, 2).join(' · ')) : (p.known_for_department && p.known_for_department !== 'Acting' ? h('div', { class: 'k' }, p.known_for_department) : null)));
    return card;
  };
  const grid = (list, onChange, showAge = false) => h('div', { class: 'people-grid' }, ...list.map((p) => personCard(p, onChange, showAge)));

  const loadFavs = async () => {
    try {
      const r = await api.peopleFavorites();
      await loadFavSet(true);
      favItems = r.results;
      showFavs();
    } catch (e) { favBox.innerHTML = ''; favBox.append(empty(e.message, '⚠️')); }
  };
  const loadNew = async () => {
    try {
      const r = await api.peopleNew();
      newBox.innerHTML = '';
      newBox.append(r.results.length ? hrow(r.results, { onChange: loadNew, showPeople: true }) : empty('Keine aktuellen Hauptrollen deiner Favoriten in den letzten Monaten.', '🎬'));
    } catch (e) { newBox.innerHTML = ''; newBox.append(empty(e.message, '⚠️')); }
  };
  const loadTrending = async () => {
    try {
      const r = await api.peopleTrending();
      trendBox.innerHTML = '';
      trendBox.append(r.results.length ? grid(r.results, loadTrending) : empty('Keine Daten.', '📈'));
    } catch (e) { trendBox.innerHTML = ''; trendBox.append(empty(e.status === 428 ? 'Bitte zuerst den TMDB-Schlüssel hinterlegen.' : e.message, '⚠️')); }
  };
  const runSearch = async () => {
    const q = input.value.trim();
    const my = ++seq;
    if (!q) { searchBox.innerHTML = ''; return; }
    searchBox.innerHTML = '';
    searchBox.append(h('span', { class: 'spinner' }));
    try {
      const r = await api.peopleSearch(q);
      if (my !== seq) return;
      searchBox.innerHTML = '';
      searchBox.append(section(`🔍 Suchergebnis „${q}“`, r.results.length ? grid(r.results, runSearch) : empty('Niemand gefunden.', '🔍'),
        h('button', { class: 'btn sm ghost', onClick: () => { input.value = ''; searchBox.innerHTML = ''; } }, 'Zurücksetzen')));
    } catch (e) { if (my === seq) { searchBox.innerHTML = ''; searchBox.append(empty(e.message, '⚠️')); } }
  };
  let timer;
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 400); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { clearTimeout(timer); runSearch(); } });

  root.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Schauspieler 🎭'), h('div', { class: 'sub' }, 'Deine Favoriten, aktuelle Rollen und wer gerade im Trend ist.'))),
    h('div', { class: 'glass panel' }, h('div', { class: 'searchbar' }, input, h('button', { class: 'btn primary', onClick: runSearch }, 'Suchen'))),
    h('div', { style: { height: '18px' } }),
    searchBox,
    section('🎬 Neu von deinen Schauspielern', newBox),
    section('★ Meine Schauspieler', favBox, favControls),
    section('📈 Im Trend', trendBox),
    blockedWrap,
  );
  loadFavs(); loadNew(); loadTrending(); loadBlocked();
  setTimeout(() => input.focus(), 50);
  const onJob = (e) => { if (['import_people', 'refresh_library'].includes(e.detail?.kind)) { loadFavs(); loadNew(); } };
  const favReload = loadFavs;
  window.addEventListener('focus', () => loadBlocked());
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
