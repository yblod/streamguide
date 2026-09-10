// Entdecken: umfassender Filter (Jahr, Genre, IMDb, Land, FSK, Verfügbarkeit).
import { api } from '../api.js';
import { h, grid, card, skeletons, toast, empty } from '../ui.js';

const COUNTRIES = [['DE', 'Deutschland'], ['US', 'USA'], ['GB', 'Großbritannien'], ['FR', 'Frankreich'], ['ES', 'Spanien'], ['IT', 'Italien'],
  ['KR', 'Südkorea'], ['JP', 'Japan'], ['DK', 'Dänemark'], ['SE', 'Schweden'], ['NO', 'Norwegen'], ['AT', 'Österreich'], ['CH', 'Schweiz'],
  ['CA', 'Kanada'], ['AU', 'Australien'], ['IN', 'Indien'], ['BR', 'Brasilien'], ['MX', 'Mexiko'], ['NL', 'Niederlande'], ['BE', 'Belgien'], ['PL', 'Polen'], ['TR', 'Türkei']];

const AUDIO = [['de', 'Deutsch'], ['en', 'Englisch'], ['fr', 'Französisch']];

const DEFAULT = { media_type: '', year_from: '', year_to: '', genres: [], exclude_genres: [], countries: [], exclude_countries: [], fsk: [], adult: false, languages: [], imdb_min: '', availability: 'mine', sort: 'popularity', hide_seen: true, hide_listed: false, min_votes: 50, runtime_min: '' };

function loadState() {
  try { const st = { ...DEFAULT, ...JSON.parse(localStorage.getItem('discover') || '{}') }; if (!Array.isArray(st.fsk)) st.fsk = []; delete st.exclude_languages; if (!Array.isArray(st.languages)) st.languages = []; if (!Array.isArray(st.exclude_genres)) st.exclude_genres = []; if (!Array.isArray(st.exclude_countries)) st.exclude_countries = []; delete st.fsk_max; delete st.runtime_max; return st; } catch { return { ...DEFAULT }; }
}

export async function render(root) {
  const f = loadState();
  let genresByType = { movie: [], tv: [] };
  try { genresByType = await api.genres(); } catch { /* ohne Genres weiter */ }

  const results = h('div', {});
  const more = h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '18px' } });
  let nextPage = null, items = [], loading = false;

  const save = () => localStorage.setItem('discover', JSON.stringify(f));

  const genreChips = h('div', { class: 'chips' });
  const renderGenres = () => {
    genreChips.innerHTML = '';
    const map = new Map();
    const types = f.media_type ? [f.media_type] : ['movie', 'tv'];
    for (const mt of types) for (const g of genresByType[mt] || []) map.set(g.id, g.name);
    // Doppelte Namen (Film/Serie teilen sich viele IDs) zusammenführen
    const byName = new Map();
    for (const [id, name] of map) { const key = name.replace(/ & Adventure| & Fantasy/, ''); byName.set(name, [...(byName.get(name) || []), id]); }
    for (const [name, ids] of [...byName].sort((a, b) => a[0].localeCompare(b[0], 'de'))) {
      const on = ids.some((i) => f.genres.includes(i));
      const off = !on && ids.some((i) => f.exclude_genres.includes(i));
      genreChips.append(h('button', { class: `chip ${on ? 'active' : ''} ${off ? 'neg' : ''}`, title: on ? 'Nochmal klicken: ausschließen' : off ? 'Nochmal klicken: Filter aus' : 'Klicken: nur dieses Genre', onClick: () => {
        if (on) { f.genres = f.genres.filter((i) => !ids.includes(i)); f.exclude_genres = [...new Set([...f.exclude_genres, ...ids])]; }
        else if (off) { f.exclude_genres = f.exclude_genres.filter((i) => !ids.includes(i)); }
        else { f.genres = [...new Set([...f.genres, ...ids])]; }
        renderGenres(); run();
      } }, off ? `✕ ${name}` : name));
    }
    genreChips.append(h('button', { class: `chip ${f.adult ? 'active' : ''}`, onClick: () => { f.adult = !f.adult; renderGenres(); run(); } }, 'Adult'));
  };

  const seg = (opts, key, onChange) => {
    const el = h('div', { class: 'seg' });
    const draw = () => { el.innerHTML = ''; opts.forEach(([v, label]) => el.append(h('button', { class: f[key] === v ? 'active' : '', onClick: () => { f[key] = v; draw(); (onChange || run)(); } }, label))); };
    draw();
    return el;
  };
  const num = (key, ph, extra = {}) => h('input', { type: 'number', placeholder: ph, value: f[key], ...extra, onChange: (e) => { f[key] = e.target.value; run(); } });
  const sel = (key, opts) => {
    const s = h('select', { onChange: (e) => { f[key] = e.target.value; run(); } }, ...opts.map(([v, l]) => h('option', { value: v, selected: String(f[key]) === String(v) }, l)));
    return s;
  };
  const fskChips = h('div', { class: 'chips' });
  const renderFsk = () => {
    fskChips.innerHTML = '';
    for (const v of [0, 6, 12, 16, 18]) {
      const on = f.fsk.includes(v);
      fskChips.append(h('button', { class: `chip ${on ? 'active' : ''}`, onClick: () => { f.fsk = on ? f.fsk.filter((x) => x !== v) : [...f.fsk, v]; renderFsk(); run(); } }, `FSK ${v}`));
    }
  };
  renderFsk();
  const audioChips = h('div', { class: 'chips' });
  const renderAudio = () => {
    audioChips.innerHTML = '';
    for (const [c, n] of AUDIO) {
      const on = f.languages.includes(c);
      audioChips.append(h('button', { class: `chip ${on ? 'active' : ''}`, onClick: () => { f.languages = on ? f.languages.filter((x) => x !== c) : [...f.languages, c]; renderAudio(); run(); } }, n));
    }
  };
  renderAudio();
  const countryChips = h('div', { class: 'chips' });
  const renderCountries = () => {
    countryChips.innerHTML = '';
    for (const [c, n] of COUNTRIES) {
      const on = f.countries.includes(c);
      const off = !on && f.exclude_countries.includes(c);
      countryChips.append(h('button', { class: `chip ${on ? 'active' : ''} ${off ? 'neg' : ''}`, title: on ? 'Nochmal klicken: ausschließen' : off ? 'Nochmal klicken: Filter aus' : 'Klicken: nur dieses Land', onClick: () => {
        if (on) { f.countries = f.countries.filter((x) => x !== c); f.exclude_countries = [...new Set([...f.exclude_countries, c])]; }
        else if (off) { f.exclude_countries = f.exclude_countries.filter((x) => x !== c); }
        else { f.countries = [...f.countries, c]; }
        renderCountries(); run();
      } }, off ? `✕ ${n}` : n));
    }
    if (f.countries.length || f.exclude_countries.length) countryChips.append(h('button', { class: 'chip', style: { color: 'var(--danger)' }, onClick: () => { f.countries = []; f.exclude_countries = []; renderCountries(); run(); } }, 'Länder zurücksetzen'));
  };
  renderCountries();

  const panel = h('div', { class: 'glass panel' },
    h('div', { class: 'row spread', style: { marginBottom: '14px' } },
      h('div', { class: 'row' },
        seg([['', 'Alles'], ['movie', 'Filme'], ['tv', 'Serien']], 'media_type', () => { renderGenres(); run(); }),
        seg([['mine', 'Meine Abos'], ['free', 'Kostenlos'], ['stream', 'Alle Streams'], ['rent', 'Leihen/Kaufen'], ['any', 'Alles']], 'availability')),
      h('div', { class: 'row' },
        h('label', { class: 'toggle small' }, h('input', { type: 'checkbox', checked: f.hide_seen, onChange: (e) => { f.hide_seen = e.target.checked; run(); } }), h('span', { class: 'sw' }), 'Gesehene ausblenden'),
        h('label', { class: 'toggle small', title: 'Filme auf der Watchlist und verfolgte Serien ausblenden' }, h('input', { type: 'checkbox', checked: f.hide_listed, onChange: (e) => { f.hide_listed = e.target.checked; run(); } }), h('span', { class: 'sw' }), 'Gemerkte ausblenden'),
        h('button', { class: 'btn sm ghost', onClick: () => { Object.assign(f, DEFAULT, { genres: [], exclude_genres: [], countries: [], exclude_countries: [], fsk: [], adult: false, languages: [] }); save(); render(root); } }, 'Zurücksetzen'))),
    h('div', { class: 'filters' },
      h('label', { class: 'field' }, 'Erscheinungsjahr', h('div', { class: 'range' }, num('year_from', 'von', { min: 1900, max: 2030 }), '–', num('year_to', 'bis', { min: 1900, max: 2030 }))),
      h('label', { class: 'field' }, 'IMDb mindestens', sel('imdb_min', [['', 'egal'], ['5', '5.0+'], ['6', '6.0+'], ['6.5', '6.5+'], ['7', '7.0+'], ['7.5', '7.5+'], ['8', '8.0+'], ['8.5', '8.5+']])),
      h('label', { class: 'field' }, 'Sortierung', sel('sort', [['popularity', 'Beliebtheit'], ['imdb', 'IMDb-Bewertung'], ['tmdb', 'TMDB-Bewertung'], ['votes', 'Meiste Stimmen'], ['newest', 'Neueste zuerst'], ['oldest', 'Älteste zuerst']])),
      h('label', { class: 'field' }, 'Mind. Laufzeit (Min, blendet Kurzfilme aus)', num('runtime_min', 'z. B. 60', { min: 0, step: 10 })),
      h('label', { class: 'field' }, 'Mind. Stimmen (TMDB)', sel('min_votes', [['10', '10'], ['50', '50'], ['200', '200'], ['1000', '1000']])),
      h('div', { class: 'field wide' }, h('span', { class: 'muted small', style: { fontWeight: 600 } }, 'FSK (keine = alle, mehrere kombinierbar)'), fskChips),
      h('div', { class: 'field wide' }, h('span', { class: 'muted small', style: { fontWeight: 600 } }, 'Produktionsland (1× Klick: nur dieses Land, 2×: ausschließen, 3×: aus)'), countryChips),
      h('div', { class: 'field wide' }, h('span', { class: 'muted small', style: { fontWeight: 600 } }, 'Wiedergabesprache der Angebote (laut JustWatch; Titel ohne Sprachdaten bleiben sichtbar)'), audioChips),
      h('div', { class: 'field wide' }, h('span', { class: 'muted small', style: { fontWeight: 600 } }, 'Genres (1× Klick: nur dieses Genre, 2×: ausschließen, 3×: aus)'), genreChips),
    ),
    h('div', { class: 'legend', style: { marginTop: '12px' } }, h('span', { class: 'l-sub' }, 'Im Abo'), h('span', { class: 'l-free' }, 'Kostenlos'), h('span', { class: 'l-other' }, 'Anderes Abo'), h('span', { class: 'l-rent' }, 'Leihen/Kaufen'), h('span', { class: 'grow' }), h('span', { id: 'disc-count' })),
  );
  renderGenres();

  root.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Entdecken 🧭'), h('div', { class: 'sub' }, 'Filtere das Angebot deiner Anbieter nach Jahr, Genre, IMDb-Bewertung, Land und FSK.'))), panel, results, more);

  const payload = (page) => ({
    media_type: f.media_type || null, year_from: f.year_from ? +f.year_from : null, year_to: f.year_to ? +f.year_to : null,
    genres: f.genres, exclude_genres: f.exclude_genres || [], countries: f.countries, exclude_countries: f.exclude_countries || [], imdb_min: f.imdb_min ? +f.imdb_min : null, fsk: f.fsk || [], adult: !!f.adult, languages: f.languages || [],
    availability: f.availability, sort: f.sort, hide_seen: f.hide_seen, hide_listed: !!f.hide_listed, min_votes: +f.min_votes || 50, runtime_min: f.runtime_min ? +f.runtime_min : null, page,
  });

  let seq = 0;
  async function run(append = false) {
    save();
    const my = ++seq;
    if (!append) { items = []; results.innerHTML = ''; results.append(skeletons(12)); nextPage = null; }
    more.innerHTML = '';
    more.append(h('span', { class: 'spinner' }));
    loading = true;
    try {
      const r = await api.discover(payload(append ? nextPage : 1));
      if (my !== seq) return;
      items = append ? [...items, ...r.results] : r.results;
      nextPage = r.next_page;
      draw();
    } catch (e) {
      if (my !== seq) return;
      results.innerHTML = '';
      results.append(empty(e.status === 428 ? 'Bitte zuerst den TMDB-Schlüssel in den Einstellungen hinterlegen.' : e.message, '⚠️'));
      more.innerHTML = '';
    } finally { loading = false; }
  }
  function draw() {
    results.innerHTML = '';
    const seen = new Set();
    const uniq = items.filter((t) => { const k = t.media_type + t.tmdb_id; if (seen.has(k)) return false; seen.add(k); return true; });
    results.append(grid(uniq, { onChange: (t) => {
      if (t) items = items.map((x) => x.media_type === t.media_type && x.tmdb_id === t.tmdb_id ? t : x);
      if (f.hide_seen) items = items.filter((x) => !['watched', 'disliked', 'dropped'].includes(x.user?.status));
      if (f.hide_listed) items = items.filter((x) => !['watchlist', 'watching'].includes(x.user?.status));
      draw();
    }, emptyText: 'Keine Treffer – Filter lockern oder Verfügbarkeit auf „Alles“ stellen.' }));
    document.getElementById('disc-count').textContent = `${uniq.length} Treffer${nextPage ? '+' : ''}`;
    more.innerHTML = '';
    if (nextPage) more.append(h('button', { class: 'btn primary', onClick: () => run(true) }, 'Mehr laden'));
  }
  run();
  return {};
}
