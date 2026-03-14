(() => {
  const boot = window.__TIKLOCAL_LIBRARY_BOOT__ || {};
  delete window.__TIKLOCAL_LIBRARY_BOOT__;

  const scope = boot.scope;
  const collectionId = boot.collectionId;
  const pageSize = Number(boot.pageSize || 0);
  const initialItems = Array.isArray(boot.initialItems) ? boot.initialItems : [];
  const initialHasMore = !!boot.initialHasMore;
  const initialNextOffset = Number(boot.initialNextOffset || 0);
  const initialMode = String(boot.initialMode || 'all');
  const initialSeed = String(boot.initialSeed || '');
  const minMb = Number(boot.minMb || 0);
  const emptyMessage = String(boot.emptyMessage || '');
  const focusName = new URLSearchParams(window.location.search).get('focus') || '';

  const grid = document.getElementById('library-grid');
  const loadingEl = document.getElementById('library-loading');
  const sentinel = document.getElementById('library-sentinel');

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
  const quickMagnifierToggle = document.getElementById('quick-magnifier-toggle');
  const quickZoomOptions = document.getElementById('quick-zoom-options');
  const quickMagBadge = document.getElementById('quick-mag-badge');
  const quickMagnifier = document.getElementById('quick-magnifier');
  const quickCaptionPanel = document.getElementById('quick-caption-panel');
  const quickCaptionTitle = document.getElementById('quick-caption-title');
  const quickCaptionTags = document.getElementById('quick-caption-tags');
  const uiShared = window.FlowUIShared || {};
  const actionsShared = window.FlowActionsShared || {};

  const quickFavorite = document.getElementById('quick-favorite');
  const quickCollection = document.getElementById('quick-collection');
  const quickCollectionCount = document.getElementById('quick-collection-count');
  const quickSetCover = document.getElementById('quick-set-cover');
  const quickSource = document.getElementById('quick-source');
  const quickDetail = document.getElementById('quick-detail');
  const quickCollectionModal = document.getElementById('quick-collection-modal');
  const quickCollectionClose = document.getElementById('quick-collection-close');
  const quickCollectionMeta = document.getElementById('quick-collection-meta');

  const quickCollectionCreateBtn = document.getElementById('quick-collection-create-btn');
  const quickCollectionNameInput = document.getElementById('quick-collection-name');
  const quickCollectionList = document.getElementById('quick-collection-list');

  let mode = scope === 'all' ? initialMode : 'all';
  let seed = initialSeed || '';
  const collectionStateCache = new Map();
  let collectionCatalog = [];
  let collectionSelectedIds = new Set();
  let collectionSelectedNames = [];
  let collectionModalOpenedAt = 0;
  const collectionModalGuardMs = 520;
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

  let isMagnifying = false;
  let magX = 0;
  let magY = 0;
  let zoomLevel = 2.5;
  let magnifierFrameRequest = null;
  let focusHandled = false;
  let focusLoading = false;
  const speedOptions = [0.75, 1, 1.25, 1.5, 2];

  function formatTime(seconds) {
    return uiShared.formatTime(seconds);
  }

  function makeRandomSeed() {
    return `${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  }

  function currentItem() {
    return flowSession.currentItem();
  }

  function getCurrentIndex() {
    return flowSession.getIndex();
  }

  function setCurrentIndex(next) {
    return flowSession.setIndex(next);
  }

  const flowState = window.createFlowStateController({
    getMediaType: () => currentItem()?.type || '',
    canMagnifyMedia: (mediaType) => mediaType === 'image' || mediaType === 'video',
    onImmersiveChange: (enabled) => {
      quickView.classList.toggle('immersive', !!enabled);
    },
    onMagnifyingChange: (enabled) => {
      isMagnifying = !!enabled;
      if (!isMagnifying) {
        cancelMagnifierFrameRequest();
        quickMagnifierToggle.classList.remove('is-active');
        quickZoomOptions.classList.remove('show');
        quickMagnifier.classList.remove('active');
      }
    },
  });

  function showPlayStatus(paused) {
    const isPaused = !!paused;
    quickPlayIcon.innerHTML = isPaused
      ? '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>'
      : '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    quickPlayStatus.classList.add('visible');
    setTimeout(() => quickPlayStatus.classList.remove('visible'), 220);
  }

  function setImmersive(enabled) {
    flowState.setImmersive(enabled);
  }

  function toggleUI() {
    flowState.toggleImmersive();
  }

  function activeTab() {
    document.querySelectorAll('.mode-tab').forEach((tab) => {
      tab.classList.toggle('is-active', tab.dataset.mode === mode);
    });
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
    waterfall.columnWidth = Math.max(1, (gridWidth - gap * (count - 1)) / count);
    grid.style.setProperty('--wf-gap', `${gap}px`);
  }

  function resetWaterfallLayout() {
    waterfall.count = 0;
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
    } else {
      const img = document.createElement('img');
      img.src = item.media_url;
      img.alt = '';
      img.loading = 'lazy';
      img.style.aspectRatio = ratio;
      tile.appendChild(img);
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
      relayoutWaterfall();
    }, 180);
  }

  function setLoadingText(text) {
    loadingEl.textContent = text;
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
    return params;
  }

  async function loadNextPage() {
    if (flowSession.isLoading() || !flowSession.hasMore()) return;
    setLoadingText('正在加载...');
    try {
      await flowSession.loadMore(async (cursor) => {
        const offset = Number(cursor?.offset || 0);
        const res = await fetch(`/api/library/items?${apiParams(offset).toString()}`);
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
        setLoadingText(emptyMessage);
      } else if (!flowSession.hasMore()) {
        setLoadingText('到底了');
      } else {
        setLoadingText('继续下滑加载更多');
      }
    } catch (error) {
      setLoadingText('加载失败，下滑重试');
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

  async function reloadMode(nextMode) {
    closeViewer();
    mode = nextMode;
    if (mode === 'image_random') seed = makeRandomSeed();
    else seed = '';

    flowSession.reset({
      hasMore: true,
      cursor: { offset: 0 },
    });
    resetWaterfallLayout();
    activeTab();
    setLoadingText('正在加载...');
    await loadNextPage();
  }

  async function collectionsRequest(url, options = {}) {
    const response = await fetch(url, options);
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }
    if (!response.ok || !(payload && payload.success)) {
      throw new Error((payload && payload.error) || '请求失败');
    }
    return payload.data || {};
  }

  function flashActionButton(buttonEl) {
    if (!buttonEl) return;
    buttonEl.classList.add('is-active');
    setTimeout(() => buttonEl.classList.remove('is-active'), 220);
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setCollectionMeta(names) {
    if (!quickCollectionMeta) return;
    const values = Array.isArray(names) ? names.filter(Boolean) : [];
    if (!values.length) {
      quickCollectionMeta.textContent = '当前未加入任何集合';
      return;
    }
    const preview = values.slice(0, 2).join('、');
    const rest = values.length - 2;
    quickCollectionMeta.textContent = rest > 0 ? `已加入：${preview} +${rest}` : `已加入：${preview}`;
  }

  function setCollectionButtonState(names) {
    const values = Array.isArray(names) ? names.filter(Boolean) : [];
    const count = values.length;
    quickCollection.classList.toggle('has-collection', count > 0);
    quickCollectionCount.textContent = count > 99 ? '99+' : String(count);
    const preview = values.slice(0, 2).join('、');
    const suffix = values.length > 2 ? ` +${values.length - 2}` : '';
    quickCollection.title = count > 0 ? `已加入：${preview}${suffix}` : '加入集合';
  }

  async function fetchCollectionMembership(uri, force = false) {
    const key = String(uri || '').trim();
    if (!key) return { ids: new Set(), names: [] };
    if (!force && collectionStateCache.has(key)) {
      const cached = collectionStateCache.get(key) || {};
      return {
        ids: new Set(Array.isArray(cached.ids) ? cached.ids : []),
        names: Array.isArray(cached.names) ? cached.names.slice() : [],
      };
    }
    const encoded = encodeURIComponent(key);
    const selectedData = await collectionsRequest(`/api/collections/by-media?uri=${encoded}`);
    const selectedItems = Array.isArray(selectedData.items) ? selectedData.items : [];
    const ids = [];
    const names = [];
    selectedItems.forEach((entry) => {
      const id = String(entry?.id || '').trim();
      const name = String(entry?.name || '').trim();
      if (id) ids.push(id);
      if (name) names.push(name);
    });
    collectionStateCache.set(key, { ids, names });
    return { ids: new Set(ids), names };
  }

  async function syncCollectionState(item, force = false) {
    const expectedName = String(item?.name || '');
    if (!expectedName) {
      collectionSelectedIds = new Set();
      collectionSelectedNames = [];
      setCollectionButtonState([]);
      setCollectionMeta([]);
      return;
    }
    try {
      const state = await fetchCollectionMembership(expectedName, force);
      if (String(currentItem()?.name || '') !== expectedName) return;
      collectionSelectedIds = new Set(state.ids);
      collectionSelectedNames = state.names.slice();
      setCollectionButtonState(collectionSelectedNames);
      setCollectionMeta(collectionSelectedNames);
    } catch (error) {
      if (String(currentItem()?.name || '') !== expectedName) return;
      collectionSelectedIds = new Set();
      collectionSelectedNames = [];
      setCollectionButtonState([]);
      setCollectionMeta([]);
    }
  }

  function updateCollectionCoverButton(item) {
    const shouldShow = scope === 'collection' && !!collectionId && !!item?.name;
    quickSetCover.classList.toggle('is-hidden', !shouldShow);
  }

  function closeCollectionModal() {
    if (!quickCollectionModal) return;
    quickCollectionModal.classList.remove('active');
    quickCollectionModal.setAttribute('aria-hidden', 'true');
    quickCollectionCreateBtn.disabled = false;
    collectionModalOpenedAt = 0;
  }

  function renderCollectionList(collections, selectedIds) {
    if (!quickCollectionList) return;
    if (!Array.isArray(collections) || !collections.length) {
      quickCollectionList.innerHTML = '<div class="quick-collection-empty">暂无集合，先新建一个。</div>';
      return;
    }
    quickCollectionList.innerHTML = collections.map((item) => {
      const id = String(item.id || '');
      const safeName = escapeHtml(String(item.name || '未命名集合'));
      const count = Number(item.item_count || 0);
      const checked = selectedIds.has(id) ? 'checked' : '';
      const isSelected = selectedIds.has(id) ? 'is-selected' : '';
      return `
        <label class="quick-collection-item ${isSelected}" data-id="${id}">
          <span class="coll-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          </span>
          <span class="coll-name">${safeName}</span>
          <em class="coll-count">${count > 0 ? count : ''}</em>
          <span class="coll-check">
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </span>
          <input type="checkbox" ${checked} />
        </label>
      `;
    }).join('');
  }

  async function openCollectionModal() {
    const item = currentItem();
    if (!item || !item.name || !quickCollectionModal) return;
    collectionModalOpenedAt = Date.now();
    quickCollectionModal.classList.add('active');
    quickCollectionModal.setAttribute('aria-hidden', 'false');
    quickCollectionList.innerHTML = '<div class="quick-collection-empty">加载中...</div>';
    try {
      const [allData, selectedState] = await Promise.all([
        collectionsRequest('/api/collections'),
        fetchCollectionMembership(item.name, true),
      ]);
      const allItems = Array.isArray(allData.items) ? allData.items : [];
      collectionCatalog = allItems;
      collectionSelectedIds = new Set(selectedState.ids);
      collectionSelectedNames = selectedState.names.slice();
      setCollectionButtonState(collectionSelectedNames);
      setCollectionMeta(collectionSelectedNames);
      renderCollectionList(allItems, collectionSelectedIds);
    } catch (error) {
      quickCollectionList.innerHTML = '<div class="quick-collection-empty">加载失败，请重试。</div>';
    }
    feather.replace();
  }

  async function createCollectionInModal() {
    const name = String(quickCollectionNameInput?.value || '').trim();
    if (!name) return;
    quickCollectionCreateBtn.disabled = true;
    try {
      const createdData = await collectionsRequest('/api/collections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const createdId = String(createdData?.item?.id || '').trim();
      const item = currentItem();
      if (createdId && item?.name) {
        await collectionsRequest(`/api/collections/${encodeURIComponent(createdId)}/items`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uris: [item.name] }),
        });
        collectionStateCache.delete(item.name);
      }
      if (quickCollectionNameInput) quickCollectionNameInput.value = '';
      await openCollectionModal();
    } catch (error) {
      quickCollectionCreateBtn.disabled = false;
      return;
    }
    quickCollectionCreateBtn.disabled = false;
  }

  async function toggleCollectionMembership(targetCollectionId, checked, rowEl, inputEl) {
    const item = currentItem();
    if (!item || !item.name) return;
    if (!targetCollectionId) return;
    rowEl?.classList.add('is-pending');
    if (inputEl) inputEl.disabled = true;
    try {
      await collectionsRequest(`/api/collections/${encodeURIComponent(targetCollectionId)}/items`, {
        method: checked ? 'POST' : 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uris: [item.name] }),
      });
      await syncCollectionState(item, true);
      collectionCatalog = collectionCatalog.map((entry) => {
        if (String(entry?.id || '') !== targetCollectionId) return entry;
        const baseCount = Number(entry?.item_count || 0);
        const nextCount = checked ? (baseCount + 1) : Math.max(0, baseCount - 1);
        return { ...entry, item_count: nextCount };
      });
      renderCollectionList(collectionCatalog, collectionSelectedIds);
    } catch (error) {
      if (inputEl) inputEl.checked = !checked;
      return;
    } finally {
      rowEl?.classList.remove('is-pending');
      if (inputEl) inputEl.disabled = false;
    }
  }

  async function syncFavoriteState(item) {
    if (!item?.name) return;
    try {
      await mediaActions.syncFavorite(item.name);
    } catch (error) {
      updateFavoriteButton(false);
    }
  }

  function updateFavoriteButton(favorited) {
    quickFavorite.classList.toggle('is-favorited', !!favorited);
  }

  function updateSourceButton(sourceMeta) {
    const url = String(sourceMeta?.url || '').trim();
    if (!url) {
      quickSource.classList.add('is-hidden');
      quickSource.removeAttribute('href');
      quickSource.title = '未记录来源';
      return;
    }
    const domain = String(sourceMeta?.source_domain || '').trim();
    quickSource.href = url;
    quickSource.title = domain ? `查看来源（${domain}）` : '查看来源';
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
    onFavoriteChange: (value) => {
      updateFavoriteButton(value);
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

  async function loadCaption(uri) {
    await mediaActions.loadCaption(uri);
  }

  async function generateCaption(uri) {
    await mediaActions.generateCaption(uri);
  }

  function currentImageEl() {
    const item = currentItem();
    if (!item || item.type !== 'image') return null;
    return quickImage;
  }

  function currentVideoEl() {
    const item = currentItem();
    if (!item || item.type !== 'video') return null;
    return quickVideo;
  }

  function getImageContainRect(imgEl) {
    return uiShared.getImageContainRect(imgEl);
  }

  function getVideoContainRect(videoEl) {
    return uiShared.getVideoContainRect(videoEl);
  }

  function updateMagnifierPosition() {
    uiShared.setMagnifierPosition(quickMagnifier, magX, magY);
  }

  function cancelMagnifierFrameRequest() {
    if (!magnifierFrameRequest) return;
    if (magnifierFrameRequest.kind === 'rvfc') {
      const videoEl = magnifierFrameRequest.videoEl;
      if (videoEl && typeof videoEl.cancelVideoFrameCallback === 'function') {
        try {
          videoEl.cancelVideoFrameCallback(magnifierFrameRequest.id);
        } catch (error) {
          // Ignore cancellation failures when media element lifecycle changes.
        }
      }
    } else if (magnifierFrameRequest.kind === 'raf') {
      cancelAnimationFrame(magnifierFrameRequest.id);
    } else if (magnifierFrameRequest.kind === 'timeout') {
      clearTimeout(magnifierFrameRequest.id);
    }
    magnifierFrameRequest = null;
  }

  function scheduleMagnifierFrameLoop(videoEl) {
    cancelMagnifierFrameRequest();
    if (!videoEl) return;

    const tick = () => {
      magnifierFrameRequest = null;
      if (!isMagnifying) return;
      const activeVideo = currentVideoEl();
      if (!activeVideo || activeVideo !== videoEl) return;
      updateMagnifierContent();

      if (videoEl.paused || videoEl.ended) {
        const timeoutId = setTimeout(() => {
          scheduleMagnifierFrameLoop(videoEl);
        }, 120);
        magnifierFrameRequest = { kind: 'timeout', id: timeoutId, videoEl };
        return;
      }
      scheduleMagnifierFrameLoop(videoEl);
    };

    if (typeof videoEl.requestVideoFrameCallback === 'function') {
      const id = videoEl.requestVideoFrameCallback(() => tick());
      magnifierFrameRequest = { kind: 'rvfc', id, videoEl };
    } else {
      const id = requestAnimationFrame(tick);
      magnifierFrameRequest = { kind: 'raf', id, videoEl };
    }
  }

  function updateMagnifierContent() {
    const item = currentItem();
    if (!item) return;

    if (item.type === 'video') {
      const videoEl = currentVideoEl();
      if (!videoEl) return;
      uiShared.updateVideoMagnifierContent({
        videoEl,
        lensEl: quickMagnifier,
        centerX: magX,
        centerY: magY,
        zoomLevel,
        maxPixelRatio: 2,
      });
      return;
    }

    const imgEl = currentImageEl();
    if (!imgEl) return;
    uiShared.updateMagnifierContent({
      imageEl: imgEl,
      lensEl: quickMagnifier,
      centerX: magX,
      centerY: magY,
      zoomLevel,
    });
  }

  function applyZoom(level) {
    zoomLevel = level;
    quickMagBadge.textContent = `${level}x`;
    document.querySelectorAll('.quick-zoom-btn').forEach((btn) => {
      const btnLevel = Number.parseFloat(btn.dataset.level || '2.5');
      btn.classList.toggle('active', btnLevel === level);
    });
    if (level >= 5) quickMagnifier.classList.add('quick-magnifier-large');
    else quickMagnifier.classList.remove('quick-magnifier-large');
    if (isMagnifying) {
      setTimeout(updateMagnifierContent, 30);
    }
  }

  function toggleMagnifier(active) {
    isMagnifying = flowState.setMagnifying(active);
    if (isMagnifying) {
      quickMagnifierToggle.classList.add('is-active');
      quickZoomOptions.classList.add('show');
      quickMagnifier.classList.add('active');
      const item = currentItem();
      const rect = item?.type === 'video'
        ? getVideoContainRect(currentVideoEl())
        : getImageContainRect(currentImageEl());
      if (rect) {
        magX = rect.left + rect.width / 2;
        magY = rect.top + rect.height / 2;
      } else {
        magX = window.innerWidth / 2;
        magY = window.innerHeight / 2;
      }
      updateMagnifierPosition();
      updateMagnifierContent();
      if (item?.type === 'video') {
        scheduleMagnifierFrameLoop(currentVideoEl());
      } else {
        cancelMagnifierFrameRequest();
      }
    } else {
      cancelMagnifierFrameRequest();
      quickMagnifierToggle.classList.remove('is-active');
      quickZoomOptions.classList.remove('show');
      quickMagnifier.classList.remove('active');
    }
  }

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
    closeCollectionModal();
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
    clearCaption();
    toggleMagnifier(false);
    updateCollectionCoverButton(null);
    setCollectionButtonState([]);
    setCollectionMeta([]);
    setCurrentIndex(-1);
    if (bodyScrollLocked) {
      document.body.style.overflow = bodyOverflowBackup;
      bodyOverflowBackup = '';
      bodyScrollLocked = false;
    }
  }

  async function showItem(index) {
    if (index < 0 || index >= items.length) return;
    setCurrentIndex(index);
    const item = items[index];
    quickCounter.textContent = `${index + 1} / ${items.length}`;
    quickDetail.href = item.detail_url || '#';
    toggleMagnifier(false);
    flowState.onMediaChanged();
    updateControls(item);
    updateCollectionCoverButton(item);

    if (item.type === 'video') {
      clearCaption();
      quickImage.classList.remove('active');
      quickImage.src = '';
      const nextSrc = String(item.media_url || '');
      if (quickVideo.getAttribute('src') !== nextSrc) {
        quickVideo.src = nextSrc;
        quickVideo.load();
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
      await loadCaption(item.name);
    }

    syncFavoriteState(item);
    syncCollectionState(item);
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
    }
  });

  async function setCurrentAsCollectionCover() {
    const item = currentItem();
    if (!item || !item.name || scope !== 'collection' || !collectionId) return;
    quickSetCover.disabled = true;
    try {
      await collectionsRequest(`/api/collections/${encodeURIComponent(collectionId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cover_uri: item.name }),
      });
      flashActionButton(quickSetCover);
    } catch (error) {
      quickSetCover.disabled = false;
      return;
    }
    quickSetCover.disabled = false;
  }

  quickCollection.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await openCollectionModal();
  });
  quickCollection.addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    await openCollectionModal();
  });

  quickSetCover.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await setCurrentAsCollectionCover();
  });

  quickCollectionClose.addEventListener('click', (event) => {
    event.preventDefault();
    closeCollectionModal();
  });

  quickCollectionModal.addEventListener('click', (event) => {
    if (collectionModalOpenedAt && (Date.now() - collectionModalOpenedAt) < collectionModalGuardMs) {
      return;
    }
    if (event.target === quickCollectionModal) closeCollectionModal();
  });
  quickCollectionCreateBtn.addEventListener('click', async (event) => {
    event.preventDefault();
    event.stopPropagation();
    await createCollectionInModal();
  });
  quickCollectionNameInput.addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    await createCollectionInModal();
  });
  quickCollectionList.addEventListener('change', async (event) => {
    const inputEl = event.target.closest('input[type="checkbox"]');
    if (!inputEl) return;
    const rowEl = inputEl.closest('[data-id]');
    const targetCollectionId = String(rowEl?.getAttribute('data-id') || '').trim();
    if (!targetCollectionId) return;
    await toggleCollectionMembership(targetCollectionId, !!inputEl.checked, rowEl, inputEl);
  });

  quickCloseTop.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    closeViewer();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && quickCollectionModal.classList.contains('active')) {
      closeCollectionModal();
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
    generateCaption(item.name);
  });

  quickMagnifierToggle.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleMagnifier(!isMagnifying);
  });

  document.querySelectorAll('.quick-zoom-btn').forEach((btn) => {
    btn.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const level = Number.parseFloat(btn.dataset.level || '2.5');
      applyZoom(level);
    });
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
    if (isMagnifying) return;
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
    if (isMagnifying) return;
    nextItem();
  });
  swipe.on('swipedown', () => {
    if (isMagnifying) return;
    prevItem();
  });

  const magHammer = new Hammer(quickMagnifier);
  magHammer.get('pan').set({ direction: Hammer.DIRECTION_ALL, threshold: 0 });
  let startMagX = 0;
  let startMagY = 0;
  magHammer.on('panstart', () => {
    startMagX = magX;
    startMagY = magY;
    quickMagnifier.style.transition = 'none';
  });
  magHammer.on('panmove', (event) => {
    magX = startMagX + event.deltaX;
    magY = startMagY + event.deltaY;
    updateMagnifierPosition();
    updateMagnifierContent();
  });
  magHammer.on('panend', () => {
    quickMagnifier.style.transition = 'transform 0.2s ease, width 0.2s ease, height 0.2s ease';
  });

  window.addEventListener('resize', () => {
    if (isMagnifying) updateMagnifierContent();
    scheduleWaterfallRelayout();
  });

  quickVideo.addEventListener('timeupdate', updateVideoProgress);
  quickVideo.addEventListener('loadedmetadata', updateVideoProgress);
  quickVideo.addEventListener('durationchange', updateVideoProgress);
  quickVideo.addEventListener('play', () => {
    quickPlayStatus.classList.remove('visible');
    if (isMagnifying && currentVideoEl() === quickVideo) {
      scheduleMagnifierFrameLoop(quickVideo);
    }
  });
  quickVideo.addEventListener('seeked', () => {
    if (isMagnifying && currentVideoEl() === quickVideo) {
      updateMagnifierContent();
    }
  });
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
  }

  quickSpeed.textContent = `${speedOptions[currentSpeedIndex]}x`;
  applyZoom(2.5);
  relayoutWaterfall();
  if (!items.length && !flowSession.hasMore()) {
    setLoadingText(emptyMessage);
  } else if (!flowSession.hasMore()) {
    setLoadingText('到底了');
  } else {
    setLoadingText('继续下滑加载更多');
  }
  feather.replace();
  maybeOpenFocusedItem();
})();
