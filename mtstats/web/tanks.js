/* Каталог техники — таблицей, как на lesta-replays. */
(function () {
  const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI'];

  const COLUMNS = [
    { key: 'tank', label: 'Танк', left: true },
    { key: 'battles', label: 'Бои' },
    { key: 'winrate', label: 'Победы', percent: true },
    { key: 'damage_avg', label: 'Ср. урон' },
    { key: 'xp_avg', label: 'Ср. опыт' },
    { key: 'kills_avg', label: 'Фраги', one: true },
    { key: 'survival_rate', label: 'Выжил', percent: true },
    { key: 'accuracy', label: 'Точность', percent: true },
    { key: 'penetration', label: 'Пробитие', percent: true },
    { key: 'marks', label: 'Отметка', marks: true },
    { key: 'mastery', label: 'Мастерство', mastery: true },
  ];

  const state = {
    tanks: [], search: '', nation: '', level: 0, tankClass: '',
    sort: { key: 'battles', dir: -1 },
  };

  function iconUrl(vehicle) {
    return vehicle ? '/api/icon/' + encodeURIComponent(vehicle) : '';
  }

  function wrClass(value) {
    if (value == null) return '';
    return value >= 50 ? 'win' : 'loss';
  }

  function sortRows(rows) {
    const { key, dir } = state.sort;
    return rows.slice().sort((a, b) => {
      if (key === 'tank') return dir * String(a.tank).localeCompare(String(b.tank), 'ru');
      const av = a[key] == null ? -Infinity : a[key];
      const bv = b[key] == null ? -Infinity : b[key];
      return dir * (av - bv);
    });
  }

  function renderFilters(tanks) {
    const levels = [...new Set(tanks.map((t) => t.tier).filter(Boolean))].sort((a, b) => a - b);
    document.getElementById('levelFilter').innerHTML =
      '<button class="chip' + (state.level === 0 ? ' active' : '') + '" data-level="0" title="Все уровни">Все</button>' +
      levels.map((lv) => `<button class="chip${state.level === lv ? ' active' : ''}" data-level="${lv}" title="${lv} уровень">${ROMAN[lv] || lv}</button>`).join('');

    const classes = [...new Set(tanks.map((t) => t.tank_class).filter(Boolean))]
      .sort((a, b) => MT.classRu(a).localeCompare(MT.classRu(b), 'ru'));
    document.getElementById('classFilter').innerHTML =
      '<button class="chip' + (state.tankClass === '' ? ' active' : '') + '" data-class="" title="Все классы">Все</button>' +
      classes.map((c) => `<button class="chip${state.tankClass === c ? ' active' : ''}" data-class="${c}" title="${c}">${MT.classRu(c)}</button>`).join('');

    const nations = [...new Set(tanks.map((t) => t.nation).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru'));
    const select = document.getElementById('nationSelect');
    select.innerHTML = '<option value="">Все нации</option>' +
      nations.map((n) => `<option value="${MT.escapeHtml(n)}">${MT.escapeHtml(n)}</option>`).join('');
    select.value = state.nation;
  }

  function cell(tank, column) {
    const value = tank[column.key];
    if (column.key === 'tank') {
      const tier = tank.tier ? `<span class="tier-badge">${tank.tier}</span>` : '';
      const sub = [tank.tier ? `${tank.tier} уровень` : '', tank.nation].filter(Boolean).join(' · ');
      return `<td class="left tank-cell-td">
        <a class="tank-row-link" href="/tank?tank=${encodeURIComponent(tank.tank)}">
          <span class="tank-thumb"><img loading="lazy" src="${iconUrl(tank.vehicle)}" alt=""
             onerror="this.style.display='none';this.parentNode.classList.add('no-icon')"></span>
          <span class="tank-name-cell">
            <span class="tank-name-line">${tier}<b>${MT.escapeHtml(tank.tank)}</b></span>
            <small>${MT.escapeHtml(sub)}</small>
          </span>
        </a>
      </td>`;
    }
    if (column.mastery) {
      const m = Number(value || 0);
      return `<td>${m ? `<span class="mastery-badge">${m}</span>` : '<span class="dim">—</span>'}</td>`;
    }
    if (column.marks) {
      if (value == null || value === 0) return '<td><span class="dim">—</span></td>';
      return `<td class="marks-cell"><span class="star">★</span>${MT.fmt1(value)}%</td>`;
    }
    if (value == null) return '<td><span class="dim">—</span></td>';
    if (column.percent) {
      return `<td class="${column.key === 'winrate' ? wrClass(value) : ''}">${MT.fmt1(value)}%</td>`;
    }
    if (column.one) return `<td>${MT.fmt1(value)}</td>`;
    return `<td>${MT.fmt(value)}</td>`;
  }

  function render() {
    const query = state.search.trim().toLowerCase();
    const rows = state.tanks.filter((tank) => {
      if (query && !tank.tank.toLowerCase().includes(query)) return false;
      if (state.nation && tank.nation !== state.nation) return false;
      if (state.level && Number(tank.tier || 0) !== state.level) return false;
      if (state.tankClass && tank.tank_class !== state.tankClass) return false;
      return true;
    });

    const sorted = sortRows(rows);
    const html = ['<thead><tr>'];
    COLUMNS.forEach((column) => {
      const active = state.sort.key === column.key
        ? (state.sort.dir < 0 ? ' <span class="sort">↓</span>' : ' <span class="sort">↑</span>')
        : ' <span class="sort muted">⇅</span>';
      html.push(`<th data-key="${column.key}" class="${column.left ? 'left' : ''}">${column.label}${active}</th>`);
    });
    html.push('</tr></thead><tbody>');

    if (!sorted.length) {
      html.push('<tr><td class="empty-row" colspan="11">Ничего не найдено</td></tr>');
    }
    sorted.forEach((tank) => {
      html.push('<tr>' + COLUMNS.map((column) => cell(tank, column)).join('') + '</tr>');
    });
    html.push('</tbody>');

    const table = document.getElementById('tanksTable');
    table.innerHTML = html.join('');
    table.querySelectorAll('th').forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (state.sort.key === key) state.sort.dir *= -1;
        else state.sort = { key, dir: key === 'tank' ? 1 : -1 };
        render();
      });
    });
  }

  async function load(params) {
    try {
      const payload = await MT.api('/api/tanks', params);
      state.tanks = payload.tanks;
      renderFilters(state.tanks);
      render();

      const summary = payload.summary;
      document.getElementById('tanksSummary').textContent =
        `${payload.request.label}: танков ${MT.fmt(state.tanks.length)} · боёв ${MT.fmt(summary.battles)} · ` +
        `побед ${MT.fmt1(summary.winrate)}% · средний урон ${MT.fmt(summary.damage_avg)}` +
        (summary.wn8 != null ? ` · WN8 ${MT.fmt(summary.wn8)}` : '');
      document.getElementById('banner').hidden = true;
    } catch (error) {
      const banner = document.getElementById('banner');
      banner.hidden = false;
      banner.textContent = 'Не удалось загрузить данные: ' + error.message;
    }
  }

  async function loadStatus() {
    try {
      const status = await MT.api('/api/status');
      document.getElementById('playerName').textContent = status.player || 'Игрок';
      document.getElementById('dbInfo').textContent =
        `${MT.fmt(status.battles)} боёв в базе · ${MT.ruDate(status.date_min)} … ${MT.ruDate(status.date_max)}`;
      const noFarm = Number(status.no_farm || 0);
      document.getElementById('footInfo').textContent = noFarm
        ? `Из них ${MT.fmt(noFarm)} — восстановлены с сайта: нет данных о расходах на ремонт и снаряды`
        : '';
    } catch (error) { /* не критично */ }
  }

  document.addEventListener('DOMContentLoaded', () => {
    const control = MT.periodControl((params) => load(params));

    document.getElementById('levelFilter').addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      state.level = Number(button.dataset.level) || 0;
      renderFilters(state.tanks);
      render();
    });
    document.getElementById('classFilter').addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      state.tankClass = button.dataset.class || '';
      renderFilters(state.tanks);
      render();
    });
    document.getElementById('searchInput').addEventListener('input', (event) => {
      state.search = event.target.value;
      render();
    });
    document.getElementById('nationSelect').addEventListener('change', (event) => {
      state.nation = event.target.value;
      render();
    });

    loadStatus();
    load(control.query());
  });
})();
