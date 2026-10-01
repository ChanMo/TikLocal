(() => {
  const boot = window.__TIKLOCAL_LIBRARY_BOOT__ || {};
  delete window.__TIKLOCAL_LIBRARY_BOOT__;

  const scope = boot.scope;
  const collectionId = boot.collectionId;
  let collectionCoverUri = String(boot.collectionCoverUri || '');
  const pageSize = Number(boot.pageSize || 0);
  const initialItems = Array.isArray(boot.initialItems) ? boot.initialItems : [];
  const initialHasMore = !!boot.initialHasMore;
  const initialNextOffset = Number(boot.initialNextOffset || 0);
  const initialMode = String(boot.initialMode || 'all');
  const initialSeed = String(boot.initialSeed || '');
  const minMb = Number(boot.minMb || 0);
  const emptyMessage = String(boot.emptyMessage || '');
  const timelineMonth = String(boot.timelineMonth || '');
  const focusName = new URLSearchParams(window.location.search).get('focus') || '';
  let searchQuery = new URLSearchParams(window.location.search).get('q') || '';

  const grid = document.getElementById('library-grid');
  const statusText = document.getElementById('library-status-text');
  const statusActions = document.getElementById('library-status-actions');
  const retryButton = document.getElementById('library-retry');
  const clearSearchButton = document.getElementById('library-clear-search');
  const sentinel = document.getElementById('library-sentinel');
  const searchInput = document.getElementById('library-search-input');
  const searchClearButton = document.getElementById('library-search-clear');
  const searchToggleButton = document.getElementById('library-search-toggle');
  const libraryToolbar = document.getElementById('library-toolbar');
  const collectionIdentityCover = document.getElementById('collection-identity-cover');

  const quickView = document.getElementById('quick-view');
  const quickOverlay = document.getElementById('quick-overlay');
  const quickVideo = document.getElementById('quick-video');
  const quickImage = document.getElementById('quick-image');
  const quickPlayStatus = document.getElementById('quick-play-status');
  const quickPlayIcon = document.getElementById('quick-play-icon');
  const quickCloseTop = document.getElementById('quick-close-top');
  const quickCounter = document.getElementById('quick-counter');
  const quickControls = document.getElementById('quick-controls');
  const quickProgress = document.getElementById('quick-progress');
  const quickProgressFill = document.getElementById('quick-progress-fill');
  const quickTimeCurrent = document.getElementById('quick-time-current');
  const quickTimeTotal = document.getElementById('quick-time-total');

  const quickSpeed = document.getElementById('quick-speed');
  const quickCaption = document.getElementById('quick-caption');
  const quickMagnifierToolWrap = document.getElementById('quick-magnifier-tool-wrap');
  const quickCaptionPanel = document.getElementById('quick-caption-panel');
  const quickCaptionTitle = document.getElementById('quick-caption-title');
  const quickCaptionTags = document.getElementById('quick-caption-tags');
  const uiShared = window.FlowUIShared || {};
  const actionsShared = window.FlowActionsShared || {};

  const quickFavorite = document.getElementById('quick-favorite');
  const quickSetCover = document.getElementById('quick-set-cover');
  const quickSource = document.getElementById('quick-source');
  const quickDetail = document.getElementById('quick-detail');

  let mode = scope === 'all' ? initialMode : 'all';
  let seed = initialSeed || '';
  const flowSession = window.createFlowSession({
    initialItems,
    initialHasMore: !!initialHasMore,
    initialCursor: { offset: Number(initialNextOffset || 0) },
    keyOf: (item) => String(item?.name || ''),
  });
  const items = flowSession.items;
  let currentSpeedIndex = 1;
  let clickTimer = null;
  let lastClickTime = 0;
  let wheelLocked = false;
  let isDragging = false;
  let wasPlayingBeforeDrag = false;
  let bodyOverflowBackup = '';
  let bodyScrollLocked = false;
  let focusHandled = false;
  let focusLoading = false;
  const speedOptions = [0.75, 1, 1.25, 1.5, 2];

  const { formatTime } = uiShared;

  function makeRandomSeed() {
    return `${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  }

  const currentItem = () => flowSession.currentItem();
  const getCurrentIndex = () => flowSession.getIndex();

  const magnifier = uiShared.createMagnifier({
    lens: document.getElementById('quick-magnifier'),
    toggle: document.getElementById('quick-magnifier-toggle'),
    zoomOptions: document.getElementById('quick-zoom-options'),
    badge: document.getElementById('quick-mag-badge'),
    zoomButtons: document.querySelectorAll('.quick-zoom-btn'),
    activeClass: 'is-active',
    largeClass: 'quick-magnifier-large',
    settleTransition: 'transform 0.2s ease, width 0.2s ease, height 0.2s ease',
    setMagnifying: (enabled) => flowState.setMagnifying(enabled),
    target: () => {
      const type = currentItem()?.type;
      if (type === 'video') return { type, el: quickVideo };
      if (type === 'image') return { type, el: quickImage };
      return null;
    },
  });

  const flowState = window.createFlowStateController({
    getMediaType: () => currentItem()?.type || '',
    canMagnifyMedia: (mediaType) => mediaType === 'image' || mediaType === 'video',
    onImmersiveChange: (enabled) => quickView.classList.toggle('immersive', !!enabled),
    onMagnifyingChange: (enabled) => magnifier.onStateChange(enabled),
  });

  const collections = window.TikLocalCollections.createPicker({
    button: document.getElementById('quick-collection'),
    countEl: document.getElementById('quick-collection-count'),
    modal: document.getElementById('quick-collection-modal'),
    closeBtn: document.getElementById('quick-collection-close'),
    meta: document.getElementById('quick-collection-meta'),
    createBtn: document.getElementById('quick-collection-create-btn'),
    nameInput: document.getElementById('quick-collection-name'),
    list: document.getElementById('quick-collection-list'),
    itemClass: 'quick-collection-item',
    emptyClass: 'quick-collection-empty',
    currentUri: () => currentItem()?.name,
  });

  function showPlayStatus(paused) {
    const isPaused = !!paused;
    quickPlayIcon.innerHTML = isPaused
      ? '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>'
      : '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    quickPlayStatus.classList.add('visible');
    setTimeout(() => quickPlayStatus.classList.remove('visible'), 220);
  }

  const toggleUI = () => flowState.toggleImmersive();

  function activeTab() {
    document.querySelectorAll('.mode-tab').forEach((tab) => {
      const isActive = tab.dataset.mode === mode;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-pressed', String(isActive));
    });
  }

  function syncSearchUI() {
    const hasQuery = !!String(searchInput?.value || '').trim();
    libraryToolbar?.classList.toggle('is-searching', hasQuery);
    if (searchClearButton) searchClearButton.hidden = !hasQuery;
  }

  function setSearchOpen(open, { focus = false } = {}) {
    const isOpen = !!open;
    libraryToolbar?.classList.toggle('is-search-open', isOpen);
    searchToggleButton?.setAttribute('aria-expanded', String(isOpen));
    if (isOpen && focus) requestAnimationFrame(() => searchInput?.focus());
  }

  function readLibraryStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const nextMode = params.get('mode') || 'all';
    const allowed = new Set(['all', 'image_random', 'video_latest', 'big_files']);
    return {
      mode: allowed.has(nextMode) ? nextMode : 'all',
      seed: params.get('seed') || '',
      search: params.get('q') || '',
    };
  }

  function syncLibraryUrl(replace = false) {
    if (scope !== 'all') return;
    const params = new URLSearchParams(window.location.search);
    params.delete('focus');
    if (mode === 'all') {
      params.delete('mode');
      params.delete('seed');
    } else {
      params.set('mode', mode);
      if (mode === 'image_random' && seed) params.set('seed', seed);
      else params.delete('seed');
    }
    if (mode === 'big_files' && minMb) params.set('min_mb', String(minMb));
    else params.delete('min_mb');
    if (searchQuery) params.set('q', searchQuery);
    else params.delete('q');
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}`;
    const method = replace ? 'replaceState' : 'pushState';
    window.history[method]({ mode, seed }, '', nextUrl);
  }

  function getTileAspectRatio(item) {
    const width = Number(item?.width || 0);
    const height = Number(item?.height || 0);
    if (width > 0 && height > 0) {
      return `${width} / ${height}`;
    }
    return item?.type === 'video' ? '16 / 9' : '4 / 5';
  }

  function getTileHeightRatio(item) {
    const width = Number(item?.width || 0);
    const height = Number(item?.height || 0);
    if (width > 0 && height > 0) {
      return height / width;
    }
    return item?.type === 'video' ? (9 / 16) : (5 / 4);
  }

  const waterfall = {
    count: 0,
    gap: 8,
    gridWidth: 0,
    columnWidth: 0,
    columns: [],
    heights: [],
  };
  let relayoutTimer = null;

  function getWaterfallColumnCount() {
    const width = window.innerWidth;
    if (width >= 1536) return 5;
    if (width >= 1100) return 4;
    if (width >= 768) return 3;
    return 2;
  }

  function getWaterfallGap() {
    return window.innerWidth >= 768 ? 10 : 8;
  }

  function updateWaterfallMetrics() {
    const count = Math.max(1, waterfall.count || getWaterfallColumnCount());
    const gap = getWaterfallGap();
    const gridWidth = Math.max(1, grid.clientWidth || window.innerWidth);
    waterfall.gap = gap;
    waterfall.gridWidth = gridWidth;
    waterfall.columnWidth = Math.max(1, (gridWidth - gap * (count - 1)) / count);
    grid.style.setProperty('--wf-gap', `${gap}px`);
  }

  function resetWaterfallLayout() {
    waterfall.count = 0;
    waterfall.gridWidth = 0;
    waterfall.columnWidth = 0;
    waterfall.columns = [];
    waterfall.heights = [];
    grid.innerHTML = '';
  }

  function ensureWaterfallLayout(force = false) {
    const nextCount = getWaterfallColumnCount();
    if (!force && waterfall.count === nextCount && waterfall.columns.length) {
      updateWaterfallMetrics();
      return;
    }

    waterfall.count = nextCount;
    grid.innerHTML = '';
    waterfall.columns = [];
    waterfall.heights = new Array(nextCount).fill(0);
    updateWaterfallMetrics();

    for (let i = 0; i < nextCount; i += 1) {
      const col = document.createElement('div');
      col.className = 'waterfall-col';
      grid.appendChild(col);
      waterfall.columns.push(col);
    }
  }

  function pickShortestColumnIndex() {
    if (!waterfall.heights.length) return 0;
    let target = 0;
    let minHeight = waterfall.heights[0];
    for (let i = 1; i < waterfall.heights.length; i += 1) {
      if (waterfall.heights[i] < minHeight) {
        minHeight = waterfall.heights[i];
        target = i;
      }
    }
    return target;
  }

  function estimateTileHeight(item) {
    return waterfall.columnWidth * getTileHeightRatio(item);
  }

  function createTile(item, index) {
    const tile = document.createElement('article');
    tile.className = 'media-tile';
    tile.dataset.index = String(index);
    const ratio = getTileAspectRatio(item);

    if (item.type === 'video') {
      const img = document.createElement('img');
      img.src = item.thumb_url;
      img.alt = '';
      img.loading = 'lazy';
      img.style.aspectRatio = ratio;
      tile.appendChild(img);

      const badge = document.createElement('span');
      badge.className = 'tile-video-badge';
      badge.innerHTML = feather.icons.play.toSvg({ width: 12, height: 12 });
      tile.appendChild(badge);

      if (item.progress) {
        const progress = document.createElement('span');
        progress.className = 'tile-progress';
        progress.style.setProperty('--progress', `${item.progress * 100}%`);
        tile.appendChild(progress);
      }
    } else {
      const img = document.createElement('img');
      img.src = item.thumb_url || item.media_url;
      img.alt = '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.style.aspectRatio = ratio;
      tile.appendChild(img);
    }

    if (!(item.width && item.height)) {
      // Sizes are filled in the background; until then take the real ratio once loaded.
      const img = tile.querySelector('img');
      img.addEventListener('load', () => {
        if (img.naturalWidth && img.naturalHeight) img.style.aspectRatio = `${img.naturalWidth} / ${img.naturalHeight}`;
      }, { once: true });
    }

    tile.addEventListener('click', () => openViewer(index));
    return tile;
  }

  function appendIndexToWaterfall(index) {
    const item = items[index];
    if (!item) return;
    const colIndex = pickShortestColumnIndex();
    const col = waterfall.columns[colIndex];
    if (!col) return;
    col.appendChild(createTile(item, index));
    waterfall.heights[colIndex] += estimateTileHeight(item) + waterfall.gap;
  }

  function relayoutWaterfall() {
    if (!items.length) {
      resetWaterfallLayout();
      ensureWaterfallLayout(true);
      return;
    }
    ensureWaterfallLayout(true);
    updateWaterfallMetrics();
    for (let i = 0; i < items.length; i += 1) {
      appendIndexToWaterfall(i);
    }
    feather.replace();
  }

  function scheduleWaterfallRelayout() {
    if (relayoutTimer) clearTimeout(relayoutTimer);
    relayoutTimer = setTimeout(() => {
      relayoutTimer = null;
      const nextCount = getWaterfallColumnCount();
      const nextGap = getWaterfallGap();
      const nextGridWidth = Math.max(1, grid.clientWidth || window.innerWidth);
      const layoutChanged = waterfall.count !== nextCount
        || waterfall.gap !== nextGap
        || waterfall.gridWidth !== nextGridWidth;
      if (!layoutChanged) return;
      relayoutWaterfall();
    }, 180);
  }

  function setLoadingText(text, actions = {}) {
    statusText.textContent = text;
    retryButton.hidden = actions.retry !== true;
    clearSearchButton.hidden = actions.clearSearch !== true;
    statusActions.hidden = actions.retry !== true && actions.clearSearch !== true;
  }

  function findItemIndexByName(name) {
    const expected = String(name || '').trim();
    if (!expected) return -1;
    for (let i = 0; i < items.length; i += 1) {
      if (String(items[i]?.name || '') === expected) return i;
    }
    return -1;
  }

  function apiParams(offset) {
    const params = new URLSearchParams({
      scope,
      mode,
      offset: String(offset),
      limit: String(pageSize),
    });
    if (scope === 'collection' && collectionId) {
      params.set('collection_id', String(collectionId));
    }
    if (mode === 'big_files') {
      params.set('min_mb', String(minMb));
    }
    if (mode === 'image_random') {
      if (!seed) seed = makeRandomSeed();
      params.set('seed', seed);
    }
    if (searchQuery) params.set('q', searchQuery);
    if (timelineMonth) params.set('month', timelineMonth);
    return params;
  }

  async function loadNextPage() {
    if (flowSession.isLoading() || !flowSession.hasMore()) return;
    setLoadingText('Loading...');
    try {
      await flowSession.loadMore(async (cursor) => {
        const offset = Number(cursor?.offset || 0);
        const url = `/api/library/items?${apiParams(offset).toString()}`;
        const res = await fetch(url);
        const data = await res.json();
        if (!data?.success) throw new Error('request failed');

        const payload = data.data || {};
        if (payload.seed && mode === 'image_random') seed = String(payload.seed);
        return {
          items: Array.isArray(payload.items) ? payload.items : [],
          hasMore: payload.has_more === true,
          cursor: { offset: Number(payload.next_offset || (offset + pageSize)) },
        };
      }).then((result) => {
        const appendedIndexes = result.appendedIndices || [];
        if (appendedIndexes.length) {
          ensureWaterfallLayout(!waterfall.columns.length);
          updateWaterfallMetrics();
          appendedIndexes.forEach((idx) => appendIndexToWaterfall(idx));
          feather.replace();
          if (quickView.classList.contains('active') && getCurrentIndex() >= 0) {
            quickCounter.textContent = `${getCurrentIndex() + 1} / ${items.length}`;
          }
        }
      });

      if (!items.length) {
        if (searchQuery) {
          setLoadingText(`No results for "${searchQuery}"`, { clearSearch: true });
        } else {
          setLoadingText(emptyMessage);
        }
      } else if (!flowSession.hasMore()) {
        setLoadingText('You have reached the end');
      } else {
        setLoadingText('Keep scrolling to load more');
      }
    } catch (error) {
      setLoadingText('Failed to load', { retry: true });
    }
  }

  async function maybeOpenFocusedItem() {
    if (!focusName || focusHandled || focusLoading) return;
    const directIndex = findItemIndexByName(focusName);
    if (directIndex >= 0) {
      focusHandled = true;
      openViewer(directIndex);
      return;
    }
    if (!flowSession.hasMore()) {
      focusHandled = true;
      return;
    }

    focusLoading = true;
    try {
      while (!focusHandled && flowSession.hasMore()) {
        await loadNextPage();
        const index = findItemIndexByName(focusName);
        if (index >= 0) {
          focusHandled = true;
          openViewer(index);
          return;
        }
      }
      if (!flowSession.hasMore()) {
        focusHandled = true;
      }
    } finally {
      focusLoading = false;
    }
  }

  async function reloadCurrentMode() {
    closeViewer();
    flowSession.reset({
      hasMore: true,
      cursor: { offset: 0 },
    });
    resetWaterfallLayout();
    activeTab();
    setLoadingText('Loading...');
    await loadNextPage();
  }

  async function reloadMode(nextMode) {
    mode = nextMode;
    searchQuery = '';
    if (searchInput) searchInput.value = '';
    syncSearchUI();
    setSearchOpen(false);
    if (mode === 'image_random') seed = makeRandomSeed();
    else seed = '';
    syncLibraryUrl(false);
    await reloadCurrentMode();
  }

  async function reloadModeFromUrl() {
    if (scope !== 'all') return;
    const state = readLibraryStateFromUrl();
    mode = state.mode;
    seed = state.seed;
    searchQuery = state.search;
    if (searchInput) searchInput.value = searchQuery;
    syncSearchUI();
    setSearchOpen(!!searchQuery);
    if (mode === 'image_random' && !seed) seed = makeRandomSeed();
    syncLibraryUrl(true);
    await reloadCurrentMode();
  }

  function updateCollectionCoverButton(item) {
    const shouldShow = scope === 'collection' && !!collectionId && !!item?.name;
    quickSetCover.classList.toggle('is-hidden', !shouldShow);
    if (!shouldShow) {
      quickSetCover.dataset.currentCover = 'false';
      quickSetCover.disabled = false;
      return;
    }
    const isCurrent = String(item.name) === collectionCoverUri;
    quickSetCover.dataset.currentCover = isCurrent ? 'true' : 'false';
    quickSetCover.title = isCurrent ? 'Current cover' : 'Set as Cover';
    quickSetCover.setAttribute('aria-label', quickSetCover.title);
    quickSetCover.disabled = isCurrent;
  }

  function updateCollectionIdentityCover(item) {
    if (!collectionIdentityCover || !item?.thumb_url) return;
    const collage = collectionIdentityCover.querySelector('.collection-identity-collage');
    const firstTile = collage?.querySelector('.collection-identity-tile');
    if (firstTile) {
      firstTile.dataset.uri = item.name;
      firstTile.dataset.type = item.type;
      const image = firstTile.querySelector('img');
      if (image) image.src = item.thumb_url;
      return;
    }
    const nextCollage = document.createElement('div');
    nextCollage.className = 'collection-identity-collage';
    nextCollage.dataset.count = '1';
    const tile = document.createElement('span');
    tile.className = 'collection-identity-tile';
    tile.dataset.uri = item.name;
    tile.dataset.type = item.type;
    const image = document.createElement('img');
    image.src = item.thumb_url;
    image.alt = '';
    image.decoding = 'async';
    tile.appendChild(image);
    nextCollage.appendChild(tile);
    collectionIdentityCover.replaceChildren(nextCollage);
  }

  async function syncFavoriteState(item) {
    if (!item?.name) return;
    try {
      await mediaActions.syncFavorite(item.name);
    } catch (error) {
      if (currentItem()?.name === item.name) updateFavoriteButton(false);
    }
  }

  function updateFavoriteButton(favorited) {
    quickFavorite.classList.toggle('is-favorited', !!favorited);
    quickFavorite.setAttribute('aria-pressed', String(!!favorited));
    quickFavorite.setAttribute('aria-label', favorited ? 'Remove from favorites' : 'Add to favorites');
    quickFavorite.title = favorited ? 'Remove from favorites' : 'Add to favorites';
  }

  function updateSourceButton(sourceMeta) {
    const url = String(sourceMeta?.url || '').trim();
    if (!url) {
      quickSource.classList.add('is-hidden');
      quickSource.removeAttribute('href');
      quickSource.title = 'Source not recorded';
      return;
    }
    const domain = String(sourceMeta?.source_domain || '').trim();
    quickSource.href = url;
    quickSource.title = domain ? `View source (${domain})` : 'View source';
    quickSource.classList.remove('is-hidden');
  }

  function clearCaption() {
    quickCaptionTitle.textContent = '';
    quickCaptionTags.innerHTML = '';
    quickCaptionPanel.classList.add('is-hidden');
  }

  function renderCaption(data) {
    const title = String(data?.title || '').trim();
    const tags = Array.isArray(data?.tags) ? data.tags : [];
    if (!title && tags.length === 0) {
      clearCaption();
      return;
    }
    quickCaptionPanel.classList.remove('is-hidden');
    quickCaptionTitle.textContent = title;
    quickCaptionTags.innerHTML = '';
    tags.forEach((tag) => {
      const chip = document.createElement('span');
      chip.className = 'quick-caption-tag';
      chip.textContent = String(tag || '');
      quickCaptionTags.appendChild(chip);
    });
  }

  function setCaptionLoading(loadingState) {
    quickCaption.disabled = !!loadingState;
    quickCaption.classList.toggle('is-loading', !!loadingState);
  }

  function flashCaptionError() {
    quickCaption.classList.add('is-error');
    setTimeout(() => quickCaption.classList.remove('is-error'), 1400);
  }

  const mediaActions = window.createFlowMediaActionsController({
    actions: actionsShared,
    onFavoriteChange: (value, name) => {
      if (currentItem()?.name === name) updateFavoriteButton(value);
    },
    onSourceChange: (sourceMeta) => {
      updateSourceButton(sourceMeta);
    },
    onCaptionClear: () => {
      clearCaption();
    },
    onCaptionRender: (payload) => {
      renderCaption(payload);
    },
    onCaptionLoading: (loading) => {
      setCaptionLoading(loading);
    },
    onError: (kind) => {
      if (kind === 'caption_load' || kind === 'caption_generate') {
        flashCaptionError();
      }
    },
  });

  function updateControls(item) {
    const isVideo = item?.type === 'video';
    quickControls.classList.toggle('is-hidden', !isVideo);
    quickSpeed.hidden = !isVideo;
    quickCaption.hidden = isVideo;
    quickMagnifierToolWrap.hidden = false;

    if (!isVideo) {
      quickProgress.disabled = true;
      quickProgress.value = 0;
      quickProgressFill.style.width = '0%';
      quickTimeCurrent.textContent = '';
      quickTimeTotal.textContent = '';
      quickPlayStatus.classList.remove('visible');
    } else {
      quickProgress.disabled = false;
    }
  }

  function updateVideoProgress() {
    const item = currentItem();
    if (!item || item.type !== 'video' || isDragging) return;
    const duration = quickVideo.duration;
    if (duration && !Number.isNaN(duration) && duration !== Infinity) {
      quickTimeTotal.textContent = formatTime(duration);
    }
    const pct = duration ? (quickVideo.currentTime / duration) * 100 : 0;
    const safePct = Number.isNaN(pct) ? 0 : pct;
    quickProgress.value = safePct;
    quickProgressFill.style.width = `${safePct}%`;
    quickTimeCurrent.textContent = formatTime(quickVideo.currentTime);
  }

  function togglePlay() {
    const item = currentItem();
    if (!item || item.type !== 'video') return;
    if (quickVideo.paused) {
      quickVideo.play().catch(() => {});
      showPlayStatus(false);
    } else {
      quickVideo.pause();
      showPlayStatus(true);
    }
  }

  function closeViewer() {
    flowState.reset();
    collections.close();
    quickView.classList.remove('active');
    quickView.setAttribute('aria-hidden', 'true');
    quickVideo.pause();
    quickVideo.removeAttribute('src');
    quickVideo.removeAttribute('poster');
    quickVideo.load();
    quickVideo.classList.remove('active');
    quickImage.classList.remove('active');
    quickImage.src = '';
    quickPlayStatus.classList.remove('visible');
    quickProgress.value = 0;
    quickProgressFill.style.width = '0%';
    quickTimeCurrent.textContent = '00:00';
    quickTimeTotal.textContent = '00:00';
    updateSourceButton(null);
    mediaActions.clearCaption();
    magnifier.toggle(false);
    updateCollectionCoverButton(null);
    collections.sync('');
    flowSession.setIndex(-1);
    if (bodyScrollLocked) {
      document.body.style.overflow = bodyOverflowBackup;
      bodyOverflowBackup = '';
      bodyScrollLocked = false;
    }
  }

  function showItem(index) {
    if (index < 0 || index >= items.length) return;
    flowSession.setIndex(index);
    const item = items[index];
    quickCounter.textContent = `${index + 1} / ${items.length}`;
    quickDetail.href = item.detail_url || '#';
    magnifier.toggle(false);
    flowState.onMediaChanged();
    updateControls(item);
    updateCollectionCoverButton(item);

    if (item.type === 'video') {
      mediaActions.clearCaption();
      quickImage.classList.remove('active');
      quickImage.src = '';
      const nextSrc = String(item.media_url || '');
      if (quickVideo.getAttribute('src') !== nextSrc) {
        quickVideo.src = nextSrc;
        quickVideo.load();
        TikLocalResume.track(quickVideo, item.name, item.resume || 0);
      }
      quickVideo.poster = item.thumb_url || '';
      quickVideo.classList.add('active');
      quickVideo.playbackRate = speedOptions[currentSpeedIndex];
      quickProgress.value = 0;
      quickProgressFill.style.width = '0%';
      quickTimeCurrent.textContent = '00:00';
      quickTimeTotal.textContent = formatTime(quickVideo.duration);
      quickVideo.play()
        .then(() => quickPlayStatus.classList.remove('visible'))
        .catch(() => showPlayStatus(true));
    } else {
      quickVideo.pause();
      quickVideo.classList.remove('active');
      quickVideo.removeAttribute('src');
      quickVideo.removeAttribute('poster');
      quickVideo.load();
      quickImage.src = item.media_url;
      quickImage.classList.add('active');
      mediaActions.loadCaption(item.name);
    }

    syncFavoriteState(item);
    collections.sync(item.name);
    syncSourceState(item);
    if (index >= items.length - 8 && flowSession.hasMore()) loadNextPage();
  }

  function openViewer(index) {
    if (index < 0 || index >= items.length) return;
    if (!quickView.classList.contains('active')) {
      bodyOverflowBackup = document.body.style.overflow || '';
      document.body.style.overflow = 'hidden';
      bodyScrollLocked = true;
    }
    quickView.classList.add('active');
    quickView.setAttribute('aria-hidden', 'false');
    showItem(index);
  }

  async function nextItem() {
    if (getCurrentIndex() >= items.length - 1 && flowSession.hasMore()) await loadNextPage();
    if (getCurrentIndex() < items.length - 1) await showItem(getCurrentIndex() + 1);
  }

  async function prevItem() {
    if (getCurrentIndex() > 0) await showItem(getCurrentIndex() - 1);
  }

  async function syncSourceState(item) {
    if (!item?.name) {
      updateSourceButton(null);
      return;
    }
    try {
      await mediaActions.syncSource(item.name);
    } catch (error) {
      updateSourceButton(null);
    }
  }

  quickFavorite.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const idx = getCurrentIndex();
    if (idx < 0 || idx >= items.length) return;
    const item = items[idx];
    if (!item?.name) return;
    try {
      await mediaActions.toggleFavorite(item.name);
    } catch (error) {
      await syncFavoriteState(item);
      if (currentItem()?.name === item.name) {
        quickFavorite.title = 'Favorite was not saved. Please try again.';
        quickFavorite.setAttribute('aria-label', quickFavorite.title);
      }
    }
  });

  async function setCurrentAsCollectionCover() {
    const item = currentItem();
    if (!item || !item.name || scope !== 'collection' || !collectionId) return;
    if (item.name === collectionCoverUri) return;
    quickSetCover.disabled = true;
    try {
      await window.TikLocalCollections.request(`/api/collections/${encodeURIComponent(collectionId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cover_uri: item.name }),
      });
      collectionCoverUri = String(item.name);
      updateCollectionIdentityCover(item);
      updateCollectionCoverButton(item);
    } catch (error) {
      quickSetCover.disabled = false;
      return;
    }
  }

  quickSetCover.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await setCurrentAsCollectionCover();
  });

  quickCloseTop.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    closeViewer();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && collections.isOpen()) {
      collections.close();
      return;
    }
    if (!quickView.classList.contains('active')) return;
    if (event.key === 'Escape') closeViewer();
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextItem();
    if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') prevItem();
    if (event.key === ' ') {
      event.preventDefault();
      togglePlay();
    }
  });

  quickOverlay.addEventListener('click', () => {
    const item = currentItem();
    if (!item) return;
    const now = Date.now();
    const delta = now - lastClickTime;
    if (delta > 0 && delta < 250) {
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = null;
      if (item.type === 'video') {
        togglePlay();
      }
    } else {
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = setTimeout(() => {
        toggleUI();
        clickTimer = null;
      }, 250);
    }
    lastClickTime = now;
  });

  quickSpeed.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
    const rate = speedOptions[currentSpeedIndex];
    quickSpeed.textContent = `${rate}x`;
    const item = currentItem();
    if (item?.type === 'video') {
      quickVideo.playbackRate = rate;
    }
  });

  quickCaption.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    const item = currentItem();
    if (!item || item.type !== 'image') return;
    mediaActions.generateCaption(item.name);
  });

  quickProgress.addEventListener('input', () => {
    const item = currentItem();
    if (!item || item.type !== 'video') return;

    if (!isDragging) {
      isDragging = true;
      wasPlayingBeforeDrag = !quickVideo.paused;
      quickVideo.pause();
    }
    const duration = quickVideo.duration || 0;
    const seekTime = (quickProgress.value / 100) * duration;
    quickTimeCurrent.textContent = formatTime(seekTime);
    quickProgressFill.style.width = `${quickProgress.value}%`;
  });

  quickProgress.addEventListener('change', () => {
    const item = currentItem();
    if (!item || item.type !== 'video') return;
    const duration = quickVideo.duration || 0;
    quickVideo.currentTime = (quickProgress.value / 100) * duration;
    if (wasPlayingBeforeDrag) {
      quickVideo.play().catch(() => {});
    }
    isDragging = false;
  });

  quickView.addEventListener('wheel', (event) => {
    if (!quickView.classList.contains('active')) return;
    const target = event.target;
    if (target && typeof target.closest === 'function') {
      if (target.closest('.quick-actions, #quick-controls, #quick-close-top, #quick-caption-panel, .quick-magnifier')) {
        return;
      }
    }
    if (magnifier.isActive()) return;
    const deltaY = event.deltaY || 0;
    if (Math.abs(deltaY) < 24) return;
    event.preventDefault();
    if (wheelLocked) return;
    wheelLocked = true;
    if (deltaY > 0) nextItem();
    else prevItem();
    setTimeout(() => {
      wheelLocked = false;
    }, 260);
  }, { passive: false });

  const swipe = new Hammer(quickOverlay);
  swipe.get('swipe').set({ direction: Hammer.DIRECTION_VERTICAL });
  swipe.on('swipeup', () => {
    if (magnifier.isActive()) return;
    nextItem();
  });
  swipe.on('swipedown', () => {
    if (magnifier.isActive()) return;
    prevItem();
  });

  window.addEventListener('resize', scheduleWaterfallRelayout);

  quickVideo.addEventListener('timeupdate', updateVideoProgress);
  quickVideo.addEventListener('loadedmetadata', updateVideoProgress);
  quickVideo.addEventListener('durationchange', updateVideoProgress);
  quickVideo.addEventListener('play', () => {
    quickPlayStatus.classList.remove('visible');
    magnifier.onVideoPlay(quickVideo);
  });
  quickVideo.addEventListener('seeked', () => magnifier.onVideoSeeked(quickVideo));
  quickVideo.addEventListener('pause', () => {
    const item = currentItem();
    if (item?.type === 'video') showPlayStatus(true);
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) loadNextPage();
    });
  }, { rootMargin: '1000px 0px' });
  observer.observe(sentinel);

  if (scope === 'all') {
    document.querySelectorAll('.mode-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        const targetMode = tab.dataset.mode || 'all';
        if (targetMode === mode) return;
        reloadMode(targetMode);
      });
    });
    activeTab();
    syncLibraryUrl(true);
    window.addEventListener('popstate', () => {
      reloadModeFromUrl();
    });
    let searchTimer = null;
    searchInput?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      syncSearchUI();
      searchTimer = setTimeout(async () => {
        searchQuery = String(searchInput.value || '').trim();
        if (searchQuery && mode !== 'all') {
          mode = 'all';
          seed = '';
        }
        syncLibraryUrl(true);
        await reloadCurrentMode();
      }, 300);
    });
    searchClearButton?.addEventListener('click', async () => {
      clearTimeout(searchTimer);
      searchQuery = '';
      searchInput.value = '';
      syncSearchUI();
      syncLibraryUrl(true);
      await reloadCurrentMode();
      searchInput.focus();
    });
    searchToggleButton?.addEventListener('click', () => {
      const isOpen = libraryToolbar?.classList.contains('is-search-open');
      setSearchOpen(!isOpen, { focus: !isOpen });
    });
    searchInput?.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape' || String(searchInput.value || '').trim()) return;
      event.preventDefault();
      setSearchOpen(false);
      searchToggleButton?.focus();
    });
  }

  retryButton.addEventListener('click', async () => {
    setLoadingText('Reloading...');
    await loadNextPage();
  });

  clearSearchButton.addEventListener('click', async () => {
    searchQuery = '';
    if (searchInput) searchInput.value = '';
    syncSearchUI();
    syncLibraryUrl(true);
    await reloadCurrentMode();
    searchInput?.focus();
  });

  quickSpeed.textContent = `${speedOptions[currentSpeedIndex]}x`;
  const monthHeading = document.querySelector('[data-month-heading]');
  if (monthHeading && /^\d{4}-\d{2}$/.test(timelineMonth)) {
    const [year, monthNumber] = timelineMonth.split('-');
    monthHeading.textContent = new Intl.DateTimeFormat('en', { year: 'numeric', month: 'long' }).format(new Date(year, Number(monthNumber) - 1, 1));
  }
  relayoutWaterfall();
  if (!items.length && !flowSession.hasMore()) {
    if (searchQuery) {
      setLoadingText(`No results for "${searchQuery}"`, { clearSearch: true });
    } else {
      setLoadingText(emptyMessage);
    }
  } else if (!flowSession.hasMore()) {
    setLoadingText('You have reached the end');
  } else {
    setLoadingText('Keep scrolling to load more');
  }
  feather.replace();
  syncSearchUI();
  maybeOpenFocusedItem();
})();
