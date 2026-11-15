/* Общие помощники и графики. */
(function () {
  const numberFmt = new Intl.NumberFormat('ru-RU');
  const oneFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

  const fmt = (value) => numberFmt.format(Math.round(value || 0));
  const fmt1 = (value) => oneFmt.format(value || 0);
  const pct = (value) => fmt1(value) + '%';

  const COLOR = {
    blue: '#0071e3',
    teal: '#5ac8fa',
    purple: '#af52de',
    green: '#34c759',
    orange: '#ff9500',
    red: '#ff3b30',
    gray: '#8e8e93',
  };

  function compact(value) {
    const abs = Math.abs(value || 0);
    if (abs >= 1e9) return fmt1(value / 1e9) + ' млрд';
    if (abs >= 1e6) return fmt1(value / 1e6) + ' млн';
    if (abs >= 1e4) return fmt1(value / 1e3) + ' тыс';
    return fmt(value);
  }

  function ruDate(iso) {
    if (!iso) return '—';
    const parts = String(iso).split('-');
    return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : iso;
  }

  function plural(count, forms) {
    const abs = Math.abs(count) % 100;
    const last = abs % 10;
    if (abs > 10 && abs < 20) return forms[2];
    if (last > 1 && last < 5) return forms[1];
    if (last === 1) return forms[0];
    return forms[2];
  }

  const RATING_TIP = 'Эффективность (0–100) = 45% урон относительно своего запаса прочности (урон ÷ HP, '
    + 'норма 1,6) + 20% фраги (3 за бой — максимум) + 15% засвет и помощь (1500 — максимум) + '
    + '10% танкование (1500 — максимум) + 10% победа.';

  const CLASS_RU = { heavyTank: 'ТТ', mediumTank: 'СТ', lightTank: 'ЛТ', 'AT-SPG': 'ПТ-САУ', SPG: 'САУ' };
  const classRu = (code) => CLASS_RU[code] || '';

  function num(value, formatter) {
    if (value === null || value === undefined) return '—';
    return formatter ? formatter(value) : fmt(value);
  }

  function escapeHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function api(path, params) {
    const query = new URLSearchParams(params || {});
    const response = await fetch(path + (query.toString() ? '?' + query : ''), { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || 'Ошибка сервера');
    return payload;
  }

  function axisFormat(maxAbs) {
    if (maxAbs >= 1e6) return (value) => fmt1(value / 1e6) + ' млн';
    if (maxAbs >= 1e4) return (value) => fmt1(value / 1e3) + ' тыс';
    return (value) => fmt(value);
  }

  const maxAbs = (values) => values.reduce(
    (acc, value) => (typeof value === 'number' && isFinite(value) ? Math.max(acc, Math.abs(value)) : acc),
    0,
  );

  function periodControl(onChange) {
    const tabs = document.getElementById('tabs');
    const fromInput = document.getElementById('dateFrom');
    const toInput = document.getElementById('dateTo');
    const applyBtn = document.getElementById('applyBtn');
    const url = new URLSearchParams(location.search);

    const state = {
      period: url.get('period') || 'all',
      from: url.get('from') || '',
      to: url.get('to') || '',
    };

    function sync() {
      if (tabs) {
        tabs.querySelectorAll('button').forEach((button) => {
          button.classList.toggle('active', button.dataset.period === state.period);
        });
      }
      const params = new URLSearchParams(location.search);
      params.set('period', state.period);
      if (state.period === 'custom') {
        if (state.from) params.set('from', state.from);
        if (state.to) params.set('to', state.to);
      } else {
        params.delete('from');
        params.delete('to');
      }
      try {
        history.replaceState(null, '', location.pathname + '?' + params.toString());
      } catch (error) { /* не критично */ }
    }

    function query() {
      const params = { period: state.period };
      if (state.period === 'custom') {
        if (state.from) params.from = state.from;
        if (state.to) params.to = state.to;
      }
      return params;
    }

    if (tabs) {
      tabs.querySelectorAll('button').forEach((button) => {
        button.addEventListener('click', () => {
          state.period = button.dataset.period;
          state.from = '';
          state.to = '';
          sync();
          onChange(query(), state);
        });
      });
    }
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        const from = fromInput.value;
        const to = toInput.value;
        if (!from && !to) return;
        state.period = 'custom';
        state.from = from || to;
        state.to = to || from;
        sync();
        onChange(query(), state);
      });
    }
    if (state.from && fromInput) fromInput.value = state.from;
    if (state.to && toInput) toInput.value = state.to;
    sync();
    return { state, query, sync };
  }

  function kpiCard(label, value, meta) {
    return `<div class="kpi">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      <div class="meta">${meta || ''}</div>
    </div>`;
  }

  function battleTable(rows, limit) {
    const html = ['<thead><tr>',
      '<th class="left">Дата</th><th class="left">Карта</th><th class="left">Танк</th>',
      '<th>Результат</th><th>Урон</th><th>Засвет</th><th>Помощь</th><th>Танк.</th>',
      '<th>Фарм</th><th>Опыт</th><th>Рейтинг</th>', '</tr></thead><tbody>'];
    const list = (rows || []).slice(0, limit || 400);
    if (!list.length) html.push('<tr><td class="empty-row" colspan="11">Нет боёв</td></tr>');
    list.forEach((row) => {
      const cls = row.result === 'Победа' ? 'win' : (row.result === 'Поражение' ? 'loss' : 'draw');
      html.push(`<tr>
        <td class="left">${escapeHtml(row.played_at.slice(5, 16).replace(' ', ' · '))}</td>
        <td class="left">${escapeHtml(row.map)}</td>
        <td class="left">${escapeHtml(row.tank)}</td>
        <td class="${cls}">${escapeHtml(row.result)}</td>
        <td>${fmt(row.damage)}</td>
        <td>${num(row.spot)}</td>
        <td>${num(row.assist)}</td>
        <td>${num(row.blocked)}</td>
        <td class="${row.net === null ? '' : (row.net >= 0 ? 'pos' : 'neg')}">${num(row.net, compact)}</td>
        <td>${fmt(row.xp)}</td>
        <td>${fmt(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    return html.join('');
  }

  function mapTable(rows) {
    const html = ['<thead><tr><th class="left">Карта</th><th>Бои</th><th>% побед</th>',
      '<th>Ср. урон</th><th>Рейтинг</th></tr></thead><tbody>'];
    if (!(rows || []).length) html.push('<tr><td class="empty-row" colspan="5">Нет боёв</td></tr>');
    (rows || []).forEach((row) => {
      html.push(`<tr>
        <td class="left"><a class="map-link" href="/map?map=${encodeURIComponent(row.map)}">${escapeHtml(row.map)}</a></td>
        <td>${fmt(row.battles)}</td>
        <td class="${row.winrate >= 50 ? 'win' : 'loss'}">${fmt1(row.winrate)}%</td>
        <td>${fmt(row.damage_avg)}</td>
        <td>${fmt1(row.rating)}</td>
      </tr>`);
    });
    html.push('</tbody>');
    return html.join('');
  }

  /* ---------------- агрегация по дням и неделям ---------------- */

  const pad = (value) => String(value).padStart(2, '0');

  function mondayOf(isoDate) {
    const date = new Date(isoDate + 'T00:00:00');
    const monday = new Date(date);
    monday.setDate(date.getDate() - ((date.getDay() + 6) % 7));
    return `${monday.getFullYear()}-${pad(monday.getMonth() + 1)}-${pad(monday.getDate())}`;
  }

  /** Группирует бои по дням или неделям; суммы — фарм и фраги, остальное — средние. */
  function groupSeries(series, mode) {
    if (mode === 'battle') return series.map((battle) => ({ ...battle }));

    const groups = new Map();
    series.forEach((battle) => {
      const key = mode === 'week' ? mondayOf(battle.date) : battle.date;
      let group = groups.get(key);
      if (!group) {
        group = {
          date: key, label: `${key.slice(8, 10)}.${key.slice(5, 7)}`,
          battles: 0, wins: 0, damage: 0, xp: 0, rating: 0, kills: 0, assist: 0,
          spotSum: 0, spotN: 0, blockedSum: 0, blockedN: 0, netSum: 0, netN: 0,
        };
        groups.set(key, group);
      }
      group.battles += 1;
      group.wins += battle.win;
      group.damage += battle.damage || 0;
      group.xp += battle.xp || 0;
      group.rating += battle.rating || 0;
      group.kills += battle.kills || 0;
      group.assist += battle.assist || 0;
      if (battle.spot != null) { group.spotSum += battle.spot; group.spotN += 1; }
      if (battle.blocked != null) { group.blockedSum += battle.blocked; group.blockedN += 1; }
      if (battle.net != null) { group.netSum += battle.net; group.netN += 1; }
    });

    const round = (value) => Math.round(value * 10) / 10;
    const result = [];
    [...groups.values()].sort((a, b) => a.date.localeCompare(b.date)).forEach((group) => {
      result.push({
        date: group.date,
        time: '',
        label: group.label,
        battles: group.battles,
        wins: group.wins,
        winnings: round(group.wins * 100 / group.battles),
        damage: round(group.damage / group.battles),
        xp: round(group.xp / group.battles),
        rating: round(group.rating / group.battles),
        kills: group.kills,
        killsAvg: round(group.kills / group.battles),
        assist: round(group.assist / group.battles),
        spot: group.spotN ? round(group.spotSum / group.spotN) : null,
        blocked: group.blockedN ? Math.round(group.blockedSum / group.blockedN) : null,
        net: group.netN ? Math.round(group.netSum) : null,
        win: group.wins,
      });
    });
    return result;
  }

  /** Какой шаг выбрать для текущего периода. */
  function pickGranularity(request, series) {
    const period = (request && request.period) || 'all';
    if (period === 'today') return 'battle';
    if (period === 'year' || period === 'all') return 'week';
    if (period === 'custom' && request && request.from && request.to) {
      const days = (new Date(request.to) - new Date(request.from)) / 86400000;
      return days > 45 ? 'week' : 'day';
    }
    return 'day';
  }

  const HINTS = {
    battle: {
      chartDamage: 'за каждый бой', chartSpot: 'за каждый бой', chartBlocked: 'за каждый бой',
      chartCredits: 'чистые кредиты за бой', chartXp: 'за каждый бой',
      chartWinrate: 'накопительно, по боям', chartRating: 'за каждый бой', chartKills: 'за каждый бой',
    },
    day: {
      chartDamage: 'в среднем за день', chartSpot: 'в среднем за день', chartBlocked: 'в среднем за день',
      chartCredits: 'кредиты за день', chartXp: 'в среднем за день',
      chartWinrate: '% побед за день', chartRating: 'в среднем за день', chartKills: 'фраги за день',
    },
    week: {
      chartDamage: 'в среднем за неделю', chartSpot: 'в среднем за неделю', chartBlocked: 'в среднем за неделю',
      chartCredits: 'кредиты за неделю', chartXp: 'в среднем за неделю',
      chartWinrate: '% побед за неделю', chartRating: 'в среднем за неделю', chartKills: 'фраги за неделю',
    },
  };

  function applyChartHints(granularity) {
    const texts = HINTS[granularity] || HINTS.battle;
    Object.entries(texts).forEach(([id, text]) => {
      const node = document.getElementById(id);
      const hint = node && node.closest('.card') ? node.closest('.card').querySelector('.hint') : null;
      if (hint) hint.textContent = text;
    });
  }

  /**
   * Графики. Точка = бой (сегодня), день (неделя/месяц) или неделя (год/всё время).
   * Фарм и фраги суммируются за период, остальное усредняется.
   */
  function battleCharts(series, summary, ids, opts) {
    const granularity = (opts && opts.granularity) || 'battle';
    const points = groupSeries(series, granularity);
    const labels = points.map((point) => point.label);
    const pick = (field) => points.map((point) => point[field]);
    const perPeriod = granularity !== 'battle';

    const title = (index) => {
      if (!perPeriod) return `${points[index].date} ${points[index].time}`;
      return granularity === 'week' ? `неделя ${points[index].label}` : `${points[index].label}`;
    };
    const extra = (index) => {
      const point = points[index];
      if (perPeriod) {
        return `<div class="tt-row"><span>Боёв</span><b>${point.battles}</b></div>` +
          `<div class="tt-row"><span>Побед</span><b>${point.wins}</b></div>`;
      }
      return `<div class="tt-row"><span>${escapeHtml(point.tank)}</span><b>${escapeHtml(point.map)}</b></div>` +
        `<div class="tt-row"><span>Результат</span><b class="${point.win ? 'win' : 'loss'}">${escapeHtml(point.result)}</b></div>`;
    };
    const ref = (value, color) => ({ value, label: 'среднее', color });
    const line = (element, values, color, name, format, refLine, fill) => {
      if (!element) return;
      MTChart.draw(element, {
        labels,
        series: [{ name, type: 'line', color, values, fill: fill !== false, width: 1.9, dotRadius: 2 }],
        yFormat: format || axisFormat(maxAbs(values)),
        refLine,
        tooltipTitle: title,
        tooltipExtra: extra,
      });
    };

    line(ids.damage, pick('damage'), COLOR.blue, 'Урон',
      axisFormat(maxAbs(pick('damage'))), ref(summary.damage_avg, COLOR.blue));

    if (ids.spot) {
      MTChart.draw(ids.spot, {
        labels,
        series: [
          { name: 'Засвет', type: 'line', color: COLOR.teal, values: pick('spot'), width: 1.7 },
          { name: 'Помощь', type: 'line', color: COLOR.purple, values: pick('assist'), width: 1.7 },
        ],
        yFormat: (value) => fmt1(value),
        tooltipTitle: title,
        tooltipExtra: extra,
      });
    }

    line(ids.blocked, pick('blocked'), COLOR.gray, 'Танкование',
      axisFormat(maxAbs(pick('blocked'))), ref(summary.blocked_avg, COLOR.gray));

    if (ids.credits) {
      MTChart.draw(ids.credits, {
        labels,
        series: [{
          name: 'Фарм', type: 'line', color: COLOR.green, negativeColor: COLOR.red,
          values: pick('net'), width: 1.7,
        }],
        yFormat: axisFormat(maxAbs(pick('net'))),
        tooltipTitle: title,
        tooltipExtra: extra,
      });
    }

    line(ids.xp, pick('xp'), COLOR.orange, 'Опыт',
      axisFormat(maxAbs(pick('xp'))), ref(summary.xp_avg, COLOR.orange));

    if (ids.winrate) {
      const values = perPeriod ? pick('winnings') : pick('cum_win');
      MTChart.draw(ids.winrate, {
        labels,
        series: [{ name: '% побед', type: 'line', color: COLOR.green, values, width: 2 }],
        yFormat: (value) => fmt1(value) + '%',
        refLine: { value: 50, label: '50%', color: '#c7c7cc' },
        zeroBased: false,
        minY: 0,
        maxY: 100,
        tooltipTitle: title,
        tooltipExtra: extra,
      });
    }

    line(ids.rating, pick('rating'), COLOR.purple, 'Эффективность',
      (value) => fmt1(value), ref(summary.rating_avg, COLOR.purple));

    line(ids.kills, pick('kills'), COLOR.red, 'Фраги', (value) => fmt1(value), null, false);
  }

  window.MT = {
    fmt, fmt1, pct, compact, num, classRu, ruDate, plural, escapeHtml, api, COLOR, RATING_TIP,
    axisFormat, maxAbs, periodControl, kpiCard, battleTable, mapTable,
    battleCharts, groupSeries, pickGranularity, applyChartHints,
  };
})();
