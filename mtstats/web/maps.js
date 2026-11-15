/* Статистика по картам. */
(function () {
  const COLUMNS = [
    { key: 'map', label: 'Карта', left: true },
    { key: 'battles', label: 'Бои' },
    { key: 'winrate', label: 'Победы', percent: true, colored: true },
    { key: 'damage_avg', label: 'Ср. урон' },
    { key: 'xp_avg', label: 'Ср. опыт' },
    { key: 'kills_avg', label: 'Фраги', one: true },
    { key: 'survival_rate', label: 'Выжил', percent: true },
    { key: 'spot_avg', label: 'Ср. засвет', one: true },
    { key: 'assist_avg', label: 'Ср. помощь' },
    { key: 'blocked_avg', label: 'Ср. танк.' },
    { key: 'net', label: 'Фарм', money: true },
    { key: 'rating', label: 'Рейтинг <span class="info" data-tip="' + MT.escapeHtml(MT.RATING_TIP) + '">i</span>', one: true },
    { key: 'tanks', label: 'Танков' },
  ];

  const state = {
    maps: [], search: '',
    sort: { key: 'battles', dir: -1 },
  };

  function sortRows(rows) {
    const { key, dir } = state.sort;
    return rows.slice().sort((a, b) => {
      if (key === 'map') return dir * String(a.map).localeCompare(String(b.map), 'ru');
      const av = a[key] == null ? -Infinity : a[key];
      const bv = b[key] == null ? -Infinity : b[key];
      return dir * (av - bv);
    });
  }

  function cell(row, column) {
    const value = row[column.key];
    if (column.key === 'map') {
      const icon = row.map_id
        ? `/api/mapicon/${encodeURIComponent(row.map_id)}.png?kind=thumb&name=${encodeURIComponent(row.map)}`
        : '';
      return `<td class="left">
        <a class="tank-row-link" href="/map?map=${encodeURIComponent(row.map)}">
          <span class="map-thumb"><img loading="lazy" src="${icon}" alt=""
            onerror="this.parentNode.classList.add('no-icon')"></span>
          <span class="tank-name-cell"><b>${MT.escapeHtml(row.map)}</b></span>
        </a>
      </td>`;
    }
    if (value == null) return '<td><span class="dim">—</span></td>';
    if (column.money) {
      return `<td class="${value >= 0 ? 'pos' : 'neg'}">${MT.compact(value)}</td>`;
    }
    if (column.percent) {
      const cls = column.colored ? (value >= 50 ? 'win' : 'loss') : '';
      return `<td class="${cls}">${MT.fmt1(value)}%</td>`;
    }
    if (column.one) return `<td>${MT.fmt1(value)}</td>`;
    return `<td>${MT.fmt(value)}</td>`;
  }

  function render() {
    const query = state.search.trim().toLowerCase();
    const rows = state.maps.filter((row) => !query || row.map.toLowerCase().includes(query));
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
      html.push('<tr><td class="empty-row" colspan="13">Ничего не найдено</td></tr>');
    }
    sorted.forEach((row) => {
      html.push('<tr>' + COLUMNS.map((column) => cell(row, column)).join('') + '</tr>');
    });
    html.push('</tbody>');

    const table = document.getElementById('mapsTable');
    table.innerHTML = html.join('');
    table.querySelectorAll('th').forEach((th) => {
      th.addEventListener('click', () => {
        const key = th.dataset.key;
        if (state.sort.key === key) state.sort.dir *= -1;
        else state.sort = { key, dir: key === 'map' ? 1 : -1 };
        render();
      });
    });
  }

  async function load(params) {
    try {
      const payload = await MT.api('/api/maps', params);
      state.maps = payload.maps;
      render();

      const summary = payload.summary;
      document.getElementById('mapsSummary').textContent =
        `${payload.request.label}: карт ${MT.fmt(state.maps.length)} · боёв ${MT.fmt(summary.battles)} · ` +
        `побед ${MT.fmt1(summary.winrate)}% · средний урон ${MT.fmt(summary.damage_avg)}`;
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
    document.getElementById('searchInput').addEventListener('input', (event) => {
      state.search = event.target.value;
      render();
    });
    loadStatus();
    load(control.query());
  });
})();
