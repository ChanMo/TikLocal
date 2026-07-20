(() => {
  const boot = window.__TIKLOCAL_TIMELINE_BOOT__ || {};
  delete window.__TIKLOCAL_TIMELINE_BOOT__;

  const stream = document.getElementById('timeline-stream');
  const loading = document.getElementById('library-loading');
  const statusText = document.getElementById('library-status-text');
  const sentinel = document.getElementById('library-sentinel');
  const currentLabel = document.getElementById('timeline-current-label');
  const currentDateButton = document.getElementById('timeline-current-date');
  const stickyBar = document.getElementById('timeline-sticky-bar');
  const yearPopover = document.getElementById('timeline-year-popover');
  const yearList = document.getElementById('timeline-year-list');

  let months = Array.isArray(boot.months) ? [...boot.months] : [];
  let years = Array.isArray(boot.years) ? [...boot.years] : [];
  let hasMore = boot.has_more === true;
  let nextBefore = String(boot.next_before || '');
  let loadingMore = false;
  let lastRenderedYear = '';
  const renderedMonthKeys = new Set();
  const restoreKey = 'tiklocal:timeline-position';
  const imageQueue = [];
  let activeImageRequests = 0;
  const maxImageRequests = 4;

  function monthParts(key) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(key || ''));
    return match ? { year: match[1], month: Number(match[2]) } : null;
  }

  function formatCount(value) {
    const count = Number(value || 0);
    return count > 9999 ? `${(count / 10000).toFixed(count > 99999 ? 0 : 1)} 万项` : `${count} 项`;
  }

  function monthUrl(monthKey, focusName = '') {
    const params = new URLSearchParams({ view: 'month', month: monthKey });
    if (focusName) params.set('focus', focusName);
    return `/library?${params.toString()}`;
  }

  function visibleCoverLimit() {
    return window.matchMedia('(min-width: 700px)').matches ? 15 : 9;
  }

  function rememberPosition(monthKey) {
    try {
      sessionStorage.setItem(restoreKey, JSON.stringify({
        month: monthKey,
        y: Math.max(0, window.scrollY),
        savedAt: Date.now(),
      }));
    } catch (error) {
      // Storage can be unavailable in strict private browsing contexts.
    }
  }

  function createYearMarker(year) {
    const marker = document.createElement('div');
    marker.className = 'timeline-year-marker';
    marker.id = `year-${year}`;
    marker.dataset.year = year;

    const title = document.createElement('h2');
    title.textContent = year;
    const meta = document.createElement('span');
    const summary = years.find((item) => String(item.year) === year);
    meta.textContent = summary
      ? `${summary.month_count} 个月 · ${formatCount(summary.count)}`
      : 'PRIVATE ARCHIVE';
    marker.append(title, meta);
    stream.appendChild(marker);
  }

  function createTile(item, index, visibleCount, month) {
    const tile = document.createElement('button');
    tile.type = 'button';
    tile.className = `timeline-tile${index === 0 && visibleCount >= 5 ? ' is-hero' : ''}`;
    tile.setAttribute('aria-label', `打开 ${month.key} 的媒体`);

    const image = document.createElement('img');
    image.dataset.src = String(item.thumb_url || '');
    image.alt = '';
    image.loading = index < 5 ? 'eager' : 'lazy';
    image.decoding = 'async';
    if (index === 0) image.fetchPriority = 'high';
    image.addEventListener('load', () => image.classList.add('is-loaded'), { once: true });
    tile.appendChild(image);
    imageObserver.observe(image);

    if (item.type === 'video') {
      const mark = document.createElement('span');
      mark.className = 'timeline-video-mark';
      mark.setAttribute('aria-hidden', 'true');
      mark.innerHTML = '<svg viewBox="0 0 24 24"><polygon points="7 4 20 12 7 20 7 4"></polygon></svg>';
      tile.appendChild(mark);
    }

    if (index === visibleCount - 1 && Number(month.count || 0) > visibleCount) {
      const more = document.createElement('span');
      more.className = 'timeline-more-overlay';
      more.textContent = `+${Number(month.count) - visibleCount}`;
      tile.appendChild(more);
    }

    tile.addEventListener('click', () => {
      rememberPosition(month.key);
      window.location.assign(monthUrl(month.key, String(item.name || '')));
    });
    return tile;
  }

  function createMonth(month) {
    const parts = monthParts(month.key);
    if (!parts || renderedMonthKeys.has(month.key)) return;
    if (parts.year !== lastRenderedYear) {
      createYearMarker(parts.year);
      lastRenderedYear = parts.year;
    }

    const section = document.createElement('article');
    section.className = 'timeline-month';
    section.id = `month-${month.key}`;
    section.dataset.month = month.key;
    section.dataset.reveal = '';

    const head = document.createElement('header');
    head.className = 'timeline-month-head';
    const title = document.createElement('a');
    title.className = 'timeline-month-title';
    title.href = monthUrl(month.key);
    title.addEventListener('click', () => rememberPosition(month.key));
    title.innerHTML = `<span class="timeline-month-number">${parts.month}</span><span class="timeline-month-unit">月</span>`;

    const meta = document.createElement('span');
    meta.className = 'timeline-month-meta';
    const videoText = Number(month.video_count || 0) > 0 ? ` · ${month.video_count} 段视频` : '';
    meta.textContent = `${formatCount(month.count)}${videoText}`;
    head.append(title, meta);

    const covers = Array.isArray(month.covers) ? month.covers.slice(0, visibleCoverLimit()) : [];
    const mosaic = document.createElement('div');
    mosaic.className = 'timeline-mosaic';
    mosaic.dataset.count = String(covers.length);
    covers.forEach((item, index) => mosaic.appendChild(createTile(item, index, covers.length, month)));

    const foot = document.createElement('footer');
    foot.className = 'timeline-month-foot';
    const open = document.createElement('a');
    open.className = 'timeline-open-month';
    open.href = monthUrl(month.key);
    open.innerHTML = `<span>查看这个月的全部 ${formatCount(month.count)}</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`;
    open.addEventListener('click', () => rememberPosition(month.key));
    foot.appendChild(open);

    section.append(head, mosaic, foot);
    stream.appendChild(section);
    renderedMonthKeys.add(month.key);
    revealObserver.observe(section);
    monthObserver.observe(section);
  }

  function renderMonths(values) {
    values.forEach(createMonth);
    if (window.feather) window.feather.replace();
  }

  function renderYears() {
    yearList.innerHTML = '';
    years.forEach((item, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `timeline-year-button${index === 0 ? ' is-current' : ''}`;
      button.textContent = String(item.year || '');
      button.addEventListener('click', async () => {
        yearPopover.hidden = true;
        currentDateButton.setAttribute('aria-expanded', 'false');
        await revealYear(String(item.year || ''));
      });
      yearList.appendChild(button);
    });
  }

  async function loadMore() {
    if (loadingMore || !hasMore || !nextBefore) return;
    loadingMore = true;
    statusText.textContent = '正在翻开更早的月份…';
    loading.hidden = false;
    try {
      const params = new URLSearchParams({ before: nextBefore, limit: '8', preview_limit: '18' });
      const response = await fetch(`/api/library/timeline?${params.toString()}`);
      const payload = await response.json();
      if (!response.ok || payload?.success !== true) throw new Error('request failed');
      const data = payload.data || {};
      const incoming = Array.isArray(data.months) ? data.months : [];
      months.push(...incoming);
      if (Array.isArray(data.years) && data.years.length) years = data.years;
      hasMore = data.has_more === true;
      nextBefore = String(data.next_before || '');
      renderMonths(incoming);
      statusText.textContent = hasMore ? '继续向下，翻阅更早的时光' : '已经来到影像的开端';
      renderYears();
    } catch (error) {
      statusText.textContent = '更早的月份暂时没有打开，向下滚动可重试';
    } finally {
      loadingMore = false;
    }
  }

  async function revealYear(year) {
    let target = document.getElementById(`year-${year}`);
    while (!target && hasMore) {
      await loadMore();
      target = document.getElementById(`year-${year}`);
    }
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function restorePosition() {
    const hashMatch = /^#month-(\d{4}-\d{2})$/.exec(window.location.hash);
    const navigationType = window.performance?.getEntriesByType?.('navigation')?.[0]?.type || '';
    let saved = null;
    try {
      saved = JSON.parse(sessionStorage.getItem(restoreKey) || 'null');
    } catch (error) {
      saved = null;
    }
    if (!hashMatch && navigationType !== 'back_forward') return;
    const targetMonth = hashMatch?.[1] || String(saved?.month || '');
    if (!targetMonth) return;

    let target = document.getElementById(`month-${targetMonth}`);
    while (!target && hasMore) {
      await loadMore();
      target = document.getElementById(`month-${targetMonth}`);
    }
    if (!target) return;
    requestAnimationFrame(() => {
      if (!hashMatch && Number.isFinite(Number(saved?.y))) window.scrollTo(0, Number(saved.y));
      else target.scrollIntoView({ block: 'start' });
    });
  }

  function pumpImageQueue() {
    while (activeImageRequests < maxImageRequests && imageQueue.length) {
      const image = imageQueue.shift();
      const src = String(image?.dataset?.src || '');
      if (!image || !src || !image.isConnected) continue;
      delete image.dataset.src;
      activeImageRequests += 1;
      const done = () => {
        activeImageRequests = Math.max(0, activeImageRequests - 1);
        pumpImageQueue();
      };
      image.addEventListener('load', done, { once: true });
      image.addEventListener('error', done, { once: true });
      image.src = src;
    }
  }

  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-revealed');
      revealObserver.unobserve(entry.target);
    });
  }, { rootMargin: '80px 0px', threshold: 0.08 });

  const imageObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const image = entry.target;
      if (image.dataset.src) imageQueue.push(image);
      imageObserver.unobserve(image);
      pumpImageQueue();
    });
  }, { rootMargin: '700px 0px' });

  const monthObserver = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
    const month = visible[0]?.target?.dataset?.month;
    const parts = monthParts(month);
    if (parts) currentLabel.textContent = `${parts.year} 年 ${parts.month} 月`;
  }, { rootMargin: '-10% 0px -68% 0px', threshold: 0 });

  const loadObserver = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) loadMore();
  }, { rootMargin: '1400px 0px' });

  currentDateButton.addEventListener('click', () => {
    const opening = yearPopover.hidden;
    yearPopover.hidden = !opening;
    currentDateButton.setAttribute('aria-expanded', String(opening));
  });

  document.addEventListener('click', (event) => {
    if (yearPopover.hidden || yearPopover.contains(event.target) || currentDateButton.contains(event.target)) return;
    yearPopover.hidden = true;
    currentDateButton.setAttribute('aria-expanded', 'false');
  });

  window.addEventListener('scroll', () => {
    stickyBar.classList.toggle('is-pinned', window.scrollY > stickyBar.offsetTop + 12);
  }, { passive: true });

  window.addEventListener('resize', () => {
    // Tile count intentionally remains stable after render to avoid scroll jumps.
  }, { passive: true });

  if (!months.length) {
    stream.innerHTML = '<div class="timeline-empty">还没有可以写进时间线的图片或视频。</div>';
    loading.hidden = true;
  } else {
    renderMonths(months);
    renderYears();
    statusText.textContent = hasMore ? '继续向下，翻阅更早的时光' : '已经来到影像的开端';
    loadObserver.observe(sentinel);
    restorePosition();
  }
})();
