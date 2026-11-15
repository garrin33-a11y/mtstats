/* Мини-библиотека SVG-графиков без внешних зависимостей. */
(function () {
  const NS = 'http://www.w3.org/2000/svg';

  function node(name, attrs) {
    const element = document.createElementNS(NS, name);
    if (attrs) {
      for (const key in attrs) {
        if (attrs[key] !== undefined && attrs[key] !== null) {
          element.setAttribute(key, attrs[key]);
        }
      }
    }
    return element;
  }

  function niceStep(range, count) {
    if (range <= 0) return 1;
    const raw = range / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    let step;
    if (norm <= 1) step = 1;
    else if (norm <= 2) step = 2;
    else if (norm <= 2.5) step = 2.5;
    else if (norm <= 5) step = 5;
    else step = 10;
    return step * mag;
  }

  function ticksFor(min, max, count) {
    if (max === min) max = min + 1;
    const step = niceStep(max - min, count);
    const start = Math.floor(min / step) * step;
    const end = Math.ceil(max / step) * step;
    const ticks = [];
    for (let value = start; value <= end + step * 0.001; value += step) {
      ticks.push(Math.round(value * 1000) / 1000);
    }
    return ticks;
  }

  function render(container, cfg) {
    container._cfg = cfg;
    const width = Math.max(240, container.clientWidth || 520);
    const height = cfg.height || 210;
    const padLeft = cfg.padLeft || 52;
    const padRight = 12;
    const padTop = 10;
    const padBottom = 24;

    container.innerHTML = '';
    const labels = cfg.labels || [];
    const series = (cfg.series || []).filter((s) => s && s.values && s.values.length);

    if (!labels.length || !series.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = cfg.emptyText || 'Нет данных за выбранный период';
      container.appendChild(empty);
      return;
    }

    let max = -Infinity;
    let min = Infinity;
    series.forEach((s) => {
      s.values.forEach((v) => {
        if (typeof v === 'number' && isFinite(v)) {
          if (v > max) max = v;
          if (v < min) min = v;
        }
      });
    });
    if (cfg.refLine && typeof cfg.refLine.value === 'number') {
      max = Math.max(max, cfg.refLine.value);
      min = Math.min(min, cfg.refLine.value);
    }
    if (!isFinite(max)) { max = 1; min = 0; }
    if (cfg.zeroBased !== false) {
      // столбики всегда должны опираться на ноль
      min = Math.min(0, min);
      if (series.some((s) => (s.type || 'bar') === 'bar')) max = Math.max(0, max);
    }
    if (typeof cfg.minY === 'number') min = cfg.minY;
    if (typeof cfg.maxY === 'number') max = cfg.maxY;
    if (max - min < 1e-9) {
      // одно и то же значение во всех точках — нужен осмысленный диапазон
      const pad = Math.max(Math.abs(max) * 0.3, 1);
      if (typeof cfg.minY !== 'number') min -= pad;
      if (typeof cfg.maxY !== 'number') max += pad;
    }
    if (typeof cfg.maxY !== 'number') max += (max - min) * 0.08;

    const ticks = ticksFor(min, max, 4);
    const yMin = Math.min(min, ticks[0]);
    const yMax = Math.max(max, ticks[ticks.length - 1]);

    const svg = node('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img' });
    const innerW = width - padLeft - padRight;
    const innerH = height - padTop - padBottom;
    const band = innerW / labels.length;
    const xCenter = (index) => padLeft + band * (index + 0.5);
    const yScale = (value) => padTop + innerH - ((value - yMin) / (yMax - yMin)) * innerH;

    // сетка и подписи оси Y
    ticks.forEach((tick) => {
      if (tick < yMin - 1e-9 || tick > yMax + 1e-9) return;
      const y = yScale(tick);
      svg.appendChild(node('line', {
        x1: padLeft, x2: width - padRight, y1: y, y2: y, class: 'grid-line',
      }));
      const text = node('text', {
        x: padLeft - 8, y: y + 3.5, class: 'axis-text', 'text-anchor': 'end',
      });
      text.textContent = cfg.yFormat ? cfg.yFormat(tick) : String(Math.round(tick));
      svg.appendChild(text);
    });

    // линия отсчёта
    if (cfg.refLine && typeof cfg.refLine.value === 'number') {
      const y = yScale(cfg.refLine.value);
      svg.appendChild(node('line', {
        x1: padLeft, x2: width - padRight, y1: y, y2: y,
        class: 'ref-line', stroke: cfg.refLine.color || '#8b98a8',
      }));
      if (cfg.refLine.label) {
        const text = node('text', {
          x: width - padRight, y: y - 5, class: 'ref-text',
          'text-anchor': 'end', fill: cfg.refLine.color || '#8b98a8',
        });
        text.textContent = cfg.refLine.label;
        svg.appendChild(text);
      }
    }

    const barSeries = series.filter((s) => (s.type || 'bar') === 'bar');
    const barCount = Math.max(1, barSeries.length);
    const barWidth = Math.max(2, (band * 0.62) / barCount);

    barSeries.forEach((s, seriesIndex) => {
      const offset = (seriesIndex - (barCount - 1) / 2) * barWidth;
      // ноль может оказаться вне диапазона (например, все значения отрицательные)
      const baseline = yScale(Math.min(Math.max(0, yMin), yMax));
      s.values.forEach((value, index) => {
        if (typeof value !== 'number' || !isFinite(value)) return;
        const zeroY = baseline;
        const y = yScale(value);
        const barHeight = Math.abs(zeroY - y);
        if (barHeight < 0.5) return;
        const rect = node('rect', {
          x: xCenter(index) + offset - barWidth / 2,
          y: Math.min(y, zeroY),
          width: barWidth,
          height: barHeight,
          rx: Math.min(3, barWidth / 3),
          fill: value < 0 ? (s.negativeColor || '#e0605c') : s.color,
          opacity: 0.92,
        });
        rect.dataset.index = index;
        svg.appendChild(rect);
      });
    });

    series.filter((s) => s.type === 'line').forEach((s) => {
      const points = [];
      s.values.forEach((value, index) => {
        if (typeof value !== 'number' || !isFinite(value)) return;
        points.push([xCenter(index), yScale(value)]);
      });
      if (!points.length) return;
      if (s.fill) {
        const area = points
          .map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
          .join(' ');
        const baseY = yScale(Math.min(Math.max(0, yMin), yMax));
        svg.appendChild(node('path', {
          d: `${area} L${points[points.length - 1][0].toFixed(1)},${baseY.toFixed(1)} L${points[0][0].toFixed(1)},${baseY.toFixed(1)} Z`,
          fill: s.color,
          opacity: 0.12,
        }));
      }
      svg.appendChild(node('polyline', {
        points: points.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' '),
        fill: 'none',
        stroke: s.color,
        'stroke-width': s.width || 2.4,
        'stroke-linejoin': 'round',
        'stroke-linecap': 'round',
        'stroke-dasharray': s.dashed ? '5 4' : undefined,
      }));
      // точки рисуем, когда их не слишком много (иначе линия превращается в кашу)
      if (points.length <= 60) {
        points.forEach((p) => {
          svg.appendChild(node('circle', {
            cx: p[0], cy: p[1], r: s.dotRadius || 3, fill: s.color,
          }));
        });
      }
    });

    // подписи оси X
    const labelStep = Math.max(1, Math.ceil(labels.length / Math.max(2, Math.floor(innerW / 62))));
    labels.forEach((label, index) => {
      const show = index % labelStep === 0 || index === labels.length - 1;
      if (!show) return;
      const text = node('text', {
        x: xCenter(index), y: height - 6, class: 'axis-text', 'text-anchor': 'middle',
      });
      text.textContent = label;
      svg.appendChild(text);
    });

    // подсказка
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    const guide = node('line', {
      y1: padTop, y2: height - padBottom, stroke: '#f0a233', 'stroke-width': 1,
      'stroke-dasharray': '3 3', opacity: 0,
    });
    svg.appendChild(guide);

    const overlay = node('rect', {
      x: padLeft, y: padTop, width: innerW, height: innerH, fill: 'transparent',
    });
    svg.appendChild(overlay);
    container.appendChild(svg);
    container.appendChild(tooltip);

    overlay.addEventListener('mousemove', (event) => {
      const rect = svg.getBoundingClientRect();
      const scale = width / rect.width;
      const x = (event.clientX - rect.left) * scale;
      const index = Math.max(0, Math.min(labels.length - 1, Math.floor((x - padLeft) / band)));
      if (index < 0) return;
      guide.setAttribute('x1', xCenter(index));
      guide.setAttribute('x2', xCenter(index));
      guide.setAttribute('opacity', 0.55);

      const titleText = cfg.tooltipTitle ? cfg.tooltipTitle(index) : labels[index];
      let html = `<div class="tt-title">${titleText}</div>`;
      series.forEach((s) => {
        const value = s.values[index];
        if (typeof value !== 'number' || !isFinite(value)) return;
        const shown = s.format ? s.format(value) : (cfg.yFormat ? cfg.yFormat(value) : value);
        html += `<div class="tt-row"><span><i style="display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;background:${s.color}"></i>${s.name}</span><b>${shown}</b></div>`;
      });
      if (cfg.tooltipExtra) {
        const extra = cfg.tooltipExtra(index);
        if (extra) html += extra;
      }
      tooltip.innerHTML = html;
      tooltip.style.opacity = 1;
      const left = Math.min(Math.max(4, xCenter(index) - 70), width - 150);
      tooltip.style.left = left + 'px';
      tooltip.style.top = Math.max(4, yScale(series[0].values[index] || 0) - 90) + 'px';
    });

    overlay.addEventListener('mouseleave', () => {
      tooltip.style.opacity = 0;
      guide.setAttribute('opacity', 0);
    });
  }

  function ensureObserver() {
    if (ensureObserver.done) return;
    ensureObserver.done = true;
    const observer = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        const target = entry.target;
        const cfg = target._cfg;
        if (!cfg) return;
        const width = Math.round(entry.contentRect.width);
        if (!target._lastWidth || Math.abs(target._lastWidth - width) > 12) {
          target._lastWidth = width;
          render(target, cfg);
        }
      });
    });
    ensureObserver.observer = observer;
  }

  function draw(container, cfg) {
    if (!container) return;
    ensureObserver();
    if (!container._observed) {
      ensureObserver.observer.observe(container);
      container._observed = true;
    }
    render(container, cfg);
  }

  window.MTChart = { draw: draw, render: render };
})();
