  (async () => {
    document.body.classList.add('immersive');

    const feedContainer = document.getElementById('feed-container');
    const overlayLayer = document.getElementById('overlay-layer');
    const speedBtn = document.getElementById('speed-btn');
    const captionBtn = document.getElementById('caption-btn');
    const magnifierToolWrap = document.getElementById('magnifier-tool-wrap');
    const magnifierToggle = document.getElementById('magnifier-toggle');
    const zoomOptions = document.getElementById('zoom-options');
    const magBadge = document.getElementById('mag-badge');
    const favoriteBtn = document.getElementById('favorite-btn');
    const collectionBtn = document.getElementById('collection-btn');
    const collectionCount = document.getElementById('collection-count');
    const infoBtn = document.getElementById('info-btn');
    const collectionModal = document.getElementById('collection-modal');
    const collectionModalClose = document.getElementById('collection-modal-close');
    const collectionModalMeta = document.getElementById('collection-modal-meta');

    const collectionCreateBtn = document.getElementById('collection-create-btn');
    const collectionNameInput = document.getElementById('collection-name-input');
    const collectionList = document.getElementById('collection-list');

    const playStatusIcon = document.getElementById('play-status-icon');
    const customControls = document.getElementById('custom-controls');
    const progressBar = document.getElementById('video-progress');
    const progressFill = document.getElementById('progress-fill');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');

    const magnifier = document.getElementById('magnifier');
    const captionPanel = document.getElementById('caption-panel');
    const captionTitle = document.getElementById('caption-title');
    const captionTags = document.getElementById('caption-tags');
    const uiShared = window.FlowUIShared || {};
    const actionsShared = window.FlowActionsShared || {};

    const speedOptions = [0.75, 1, 1.25, 1.5, 2];

    const flowSession = window.createFlowSession({
      initialItems: [],
      initialHasMore: true,
      initialCursor: { page: 1 },
      keyOf: (item) => String(item?.name || ''),
    });
    const feedItems = flowSession.items;
    let seed = '';

    let currentSpeedIndex = 1;
    let isImmersive = false;
    let isDragging = false;
    let wasPlayingBeforeDrag = false;
    let clickTimer = null;
    let lastClickTime = 0;
    let touchStartX = 0;
    let touchStartY = 0;

    let isMagnifying = false;
    let magX = 0;
    let magY = 0;
    let zoomLevel = 2.5;
    let magnifierFrameRequest = null;
    const collectionStateCache = new Map();
    let collectionCatalog = [];
    let collectionSelectedIds = new Set();
    let collectionSelectedNames = [];
    let collectionModalOpenedAt = 0;
    const collectionModalGuardMs = 520;

    function formatTime(seconds) {
      return uiShared.formatTime(seconds);
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
        isImmersive = !!enabled;
        document.body.classList.toggle('immersive-mode', isImmersive);
      },
      onMagnifyingChange: (enabled) => {
        isMagnifying = !!enabled;
        if (!isMagnifying) {
          cancelMagnifierFrameRequest();
          magnifierToggle.classList.remove('active');
          zoomOptions.classList.remove('show');
          magnifier.classList.remove('active');
        }
      },
    });

    function setImmersive(enabled) {
      flowState.setImmersive(enabled);
    }

    function toggleUI() {
      flowState.toggleImmersive();
    }

    function clearCaption() {
      captionTitle.textContent = '';
      captionTitle.classList.add('hidden');
      captionTags.innerHTML = '';
      captionPanel.classList.add('is-hidden');
    }

    function renderCaption(data) {
      if (!data) {
        clearCaption(false);
        return;
      }
      const title = String(data.title || '').trim();
      const tags = Array.isArray(data.tags) ? data.tags : [];
      if (!title && tags.length === 0) {
        clearCaption(false);
        return;
      }
      captionPanel.classList.remove('is-hidden');
      captionTitle.textContent = title;
      captionTitle.classList.toggle('hidden', !title);
      captionTags.innerHTML = '';
      tags.forEach((tag) => {
        const chip = document.createElement('span');
        chip.className = 'caption-tag';
        chip.textContent = String(tag || '');
        captionTags.appendChild(chip);
      });
    }

    function setCaptionLoading(loading) {
      captionBtn.disabled = !!loading;
      captionBtn.classList.toggle('is-loading', !!loading);
    }

    function flashCaptionError() {
      captionBtn.classList.add('is-error');
      setTimeout(() => captionBtn.classList.remove('is-error'), 1400);
    }

    const mediaActions = window.createFlowMediaActionsController({
      actions: actionsShared,
      onFavoriteChange: (value) => {
        favoriteBtn.classList.toggle('is-active', !!value);
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
      confirmCaptionReplace: async () => window.confirm('已存在标题，是否覆盖生成？'),
    });

    async function loadCaption(uri) {
      await mediaActions.loadCaption(uri);
    }

    async function generateCaption(uri, force = false) {
      await mediaActions.generateCaption(uri, { confirmExisting: !force });
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

    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function setCollectionMeta(names) {
      if (!collectionModalMeta) return;
      const items = Array.isArray(names) ? names.filter(Boolean) : [];
      if (!items.length) {
        collectionModalMeta.textContent = '当前未加入任何集合';
        return;
      }
      const preview = items.slice(0, 2).join('、');
      const rest = items.length - 2;
      collectionModalMeta.textContent = rest > 0 ? `已加入：${preview} +${rest}` : `已加入：${preview}`;
    }

    function setCollectionButtonState(names) {
      const items = Array.isArray(names) ? names.filter(Boolean) : [];
      const count = items.length;
      collectionBtn.classList.toggle('has-collection', count > 0);
      collectionCount.textContent = count > 99 ? '99+' : String(count);
      const preview = items.slice(0, 2).join('、');
      const suffix = items.length > 2 ? ` +${items.length - 2}` : '';
      collectionBtn.title = count > 0 ? `已加入：${preview}${suffix}` : '加入集合';
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

    function closeCollectionModal() {
      collectionModal.classList.remove('active');
      collectionModal.setAttribute('aria-hidden', 'true');
      collectionCreateBtn.disabled = false;
      collectionModalOpenedAt = 0;
    }

    function renderCollectionList(items, selectedIds) {
      if (!Array.isArray(items) || !items.length) {
        collectionList.innerHTML = '<div class="collection-modal-empty">暂无集合，先新建一个。</div>';
        return;
      }
      collectionList.innerHTML = items.map((item) => {
        const id = String(item.id || '');
        const safeName = escapeHtml(String(item.name || '未命名集合'));
        const count = Number(item.item_count || 0);
        const checked = selectedIds.has(id) ? 'checked' : '';
        const isSelected = selectedIds.has(id) ? 'is-selected' : '';
        return `
          <label class="collection-modal-item ${isSelected}" data-id="${id}">
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
      if (!item || !item.name) return;
      collectionModalOpenedAt = Date.now();
      collectionModal.classList.add('active');
      collectionModal.setAttribute('aria-hidden', 'false');
      collectionList.innerHTML = '<div class="collection-modal-empty">加载中...</div>';
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
        collectionList.innerHTML = '<div class="collection-modal-empty">加载失败，请重试。</div>';
      }
      feather.replace();
    }

    async function createCollectionInModal() {
      const name = String(collectionNameInput.value || '').trim();
      if (!name) return;
      collectionCreateBtn.disabled = true;
      try {
        const created = await collectionsRequest('/api/collections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        const createdId = String(created?.item?.id || '').trim();
        const item = currentItem();
        if (createdId && item?.name) {
          await collectionsRequest(`/api/collections/${encodeURIComponent(createdId)}/items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uris: [item.name] }),
          });
          collectionStateCache.delete(item.name);
        }
        collectionNameInput.value = '';
        await openCollectionModal();
      } catch (error) {
        collectionCreateBtn.disabled = false;
        return;
      }
      collectionCreateBtn.disabled = false;
    }

    async function toggleCollectionMembership(collectionId, checked, rowEl, inputEl) {
      const item = currentItem();
      if (!item || !item.name) return;
      if (!collectionId) return;
      rowEl?.classList.add('is-pending');
      if (inputEl) inputEl.disabled = true;
      try {
        await collectionsRequest(`/api/collections/${encodeURIComponent(collectionId)}/items`, {
          method: checked ? 'POST' : 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uris: [item.name] }),
        });
        await syncCollectionState(item, true);
        collectionCatalog = collectionCatalog.map((entry) => {
          if (String(entry?.id || '') !== collectionId) return entry;
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

    async function goNext() {
      if (getCurrentIndex() >= feedItems.length - 1 && flowSession.hasMore()) {
        await loadFeed();
      }
      if (getCurrentIndex() < feedItems.length - 1) {
        await showItem(getCurrentIndex() + 1);
      }
    }

    async function goPrev() {
      if (getCurrentIndex() > 0) {
        await showItem(getCurrentIndex() - 1);
      }
    }

    function goGroupNext() {
      const item = currentItem();
      if (!item || item.type !== 'image_group' || typeof item.renderChild !== 'function') return false;
      const entries = Array.isArray(item.items) ? item.items : [];
      const nextIndex = (Number(item.activeChildIndex) || 0) + 1;
      if (nextIndex >= entries.length) return false;
      item.activeChildIndex = item.renderChild(nextIndex);
      return true;
    }

    function goGroupPrev() {
      const item = currentItem();
      if (!item || item.type !== 'image_group' || typeof item.renderChild !== 'function') return false;
      const nextIndex = (Number(item.activeChildIndex) || 0) - 1;
      if (nextIndex < 0) return false;
      item.activeChildIndex = item.renderChild(nextIndex);
      return true;
    }

    function updateFavoriteState(name) {
      mediaActions.syncFavorite(name)
        .catch(() => favoriteBtn.classList.remove('is-active'));
    }

    function updateControls(item) {
      const isVideo = item.type === 'video';
      const isThemeStrip = item.type === 'theme_strip';
      const isImageGroup = item.type === 'image_group';
      const displayEntry = currentDisplayEntry();
      infoBtn.hidden = isThemeStrip;
      favoriteBtn.hidden = isThemeStrip;
      collectionBtn.hidden = isThemeStrip;
      speedBtn.hidden = !isVideo;
      captionBtn.hidden = isVideo || isThemeStrip || isImageGroup;
      magnifierToolWrap.hidden = isThemeStrip || isImageGroup;
      customControls.hidden = !isVideo;

      if (isThemeStrip) {
        favoriteBtn.dataset.value = '';
        favoriteBtn.classList.remove('is-active');
        setCollectionButtonState([]);
        setCollectionMeta([]);
        infoBtn.removeAttribute('href');
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
        return;
      }

      const detailUrl = String(displayEntry?.detail_url || item.detail_url || '#');
      const mediaName = String(displayEntry?.name || item.name || '');
      infoBtn.href = detailUrl;
      favoriteBtn.dataset.value = mediaName;
      if (mediaName) {
        updateFavoriteState(mediaName);
        syncCollectionState({ name: mediaName });
      }

      if (isVideo) {
        progressBar.disabled = false;
        playStatusIcon.classList.remove('hidden');
      } else {
        progressBar.disabled = true;
        progressBar.value = 0;
        progressFill.style.width = '0%';
        timeCurrent.textContent = '';
        timeTotal.textContent = '';
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
      }
    }

    function ensureVideoSrc(videoEl) {
      if (!videoEl) return;
      if (!videoEl.src) {
        videoEl.src = videoEl.dataset.src || '';
        videoEl.load();
      }
    }

    function preloadNextVideo() {
      for (let i = getCurrentIndex() + 1; i < feedItems.length; i++) {
        const item = feedItems[i];
        if (item.type !== 'video') continue;
        const v = item.el;
        if (v && !v.src) {
          ensureVideoSrc(v);
        }
        break;
      }
    }

    function updateVideoProgress(videoEl) {
      if (!videoEl || currentItem()?.el !== videoEl || isDragging) return;
      if (timeTotal.textContent === '00:00' || timeTotal.textContent === '') {
        const duration = videoEl.duration;
        if (duration && !isNaN(duration) && duration !== Infinity) {
          timeTotal.textContent = formatTime(duration);
        }
      }
      const pct = (videoEl.currentTime / videoEl.duration) * 100;
      progressBar.value = isNaN(pct) ? 0 : pct;
      progressFill.style.width = `${isNaN(pct) ? 0 : pct}%`;
      timeCurrent.textContent = formatTime(videoEl.currentTime);
    }

    function applyZoom(level) {
      zoomLevel = level;
      magBadge.textContent = `${level}x`;
      document.querySelectorAll('.zoom-btn').forEach((btn) => {
        const btnLevel = Number.parseFloat(btn.getAttribute('data-level') || '2.5');
        btn.classList.toggle('active', btnLevel === level);
      });
      if (level >= 5) {
        magnifier.classList.add('magnifier-large');
      } else {
        magnifier.classList.remove('magnifier-large');
      }
      if (isMagnifying) {
        setTimeout(updateMagnifierContent, 40);
      }
    }

    function currentImageEl() {
      const item = currentItem();
      if (!item) return null;
      if (item.type === 'image_group') {
        return item.el?.querySelector('.image-group-media') || null;
      }
      if (item.type !== 'image') return null;
      return item.el;
    }

    function currentVideoEl() {
      const item = currentItem();
      if (!item || item.type !== 'video') return null;
      return item.el;
    }

    function currentDisplayEntry() {
      const item = currentItem();
      if (!item) return null;
      if (item.type === 'image_group') {
        const entries = Array.isArray(item.items) ? item.items : [];
        const idx = Math.max(0, Math.min(Number(item.activeChildIndex) || 0, entries.length - 1));
        return entries[idx] || null;
      }
      return item;
    }

    function getImageContainRect(imgEl) {
      return uiShared.getImageContainRect(imgEl);
    }

    function getVideoContainRect(videoEl) {
      return uiShared.getVideoContainRect(videoEl);
    }

    function updateMagnifierPosition() {
      uiShared.setMagnifierPosition(magnifier, magX, magY);
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
          lensEl: magnifier,
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
        lensEl: magnifier,
        centerX: magX,
        centerY: magY,
        zoomLevel,
      });
    }

    function toggleMagnifier(active) {
      isMagnifying = flowState.setMagnifying(active);
      if (isMagnifying) {
        magnifierToggle.classList.add('active');
        zoomOptions.classList.add('show');
        magnifier.classList.add('active');
        const item = currentItem();
        const contentRect = item?.type === 'video'
          ? getVideoContainRect(currentVideoEl())
          : getImageContainRect(currentImageEl());
        if (contentRect) {
          magX = contentRect.left + contentRect.width / 2;
          magY = contentRect.top + contentRect.height / 2;
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
        magnifierToggle.classList.remove('active');
        zoomOptions.classList.remove('show');
        magnifier.classList.remove('active');
      }
    }

    function clearPreviousState(prevItem) {
      toggleMagnifier(false);

      if (!prevItem) return;
      prevItem.el.classList.remove('active');
      prevItem.el.style.display = 'none';
      if (prevItem.type === 'video') {
        prevItem.el.pause();
        prevItem.el.muted = true;
        return;
      }
      if (prevItem.type === 'theme_strip') {
        const previewVideo = prevItem.el.querySelector('.theme-strip-preview-media');
        if (previewVideo && previewVideo.tagName === 'VIDEO') previewVideo.pause();
        const groupVideo = prevItem.el.querySelector('.theme-strip-group-media');
        if (groupVideo && groupVideo.tagName === 'VIDEO') groupVideo.pause();
      }
    }

    async function showItem(nextIndex) {
      if (!feedItems.length) return;
      const safeIndex = Math.max(0, Math.min(nextIndex, feedItems.length - 1));
      const prevItem = currentItem();
      clearPreviousState(prevItem);

      setCurrentIndex(safeIndex);
      const item = currentItem();
      if (!item) return;
      flowState.onMediaChanged();

      item.el.style.display = item.type === 'theme_strip' ? '' : 'block';
      requestAnimationFrame(() => item.el.classList.add('active'));
      updateControls(item);

      if (item.type === 'video') {
        progressBar.disabled = false;
        ensureVideoSrc(item.el);
        item.el.muted = false;
        item.el.playbackRate = speedOptions[currentSpeedIndex];
        progressBar.value = 0;
        progressFill.style.width = '0%';
        timeCurrent.textContent = '00:00';
        timeTotal.textContent = formatTime(item.el.duration);
        clearCaption();

        const playPromise = item.el.play();
        if (playPromise !== undefined) {
          playPromise
            .then(() => playStatusIcon.classList.remove('visible'))
            .catch(() => playStatusIcon.classList.add('visible'));
        }
        preloadNextVideo();
      } else if (item.type === 'image_group') {
        clearCaption();
        if (typeof item.renderChild === 'function') {
          item.activeChildIndex = item.renderChild(Number(item.activeChildIndex) || 0);
        }
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
      } else if (item.type === 'theme_strip') {
        clearCaption();
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
      } else {
        playStatusIcon.classList.remove('visible');
        await loadCaption(item.name);
      }

      if (getCurrentIndex() >= feedItems.length - 4 && flowSession.hasMore()) {
        loadFeed();
      }
    }

    function buildMediaElement(item) {
      if (item.type === 'theme_strip') {
        const panel = document.createElement('section');
        panel.className = 'feed-media feed-theme-strip';
        panel.dataset.name = item.name;
        panel.innerHTML = `
          <div class="theme-strip-header">
            <h2>${escapeHtml(item.title || '主题精选')}</h2>
          </div>
          <div class="theme-strip-rail"></div>
        `;
        const rail = panel.querySelector('.theme-strip-rail');
        const children = Array.isArray(item.items) ? item.items : [];
        children.forEach((entry, index) => {
          if (!rail || !entry || !entry.name || !entry.thumb_url) return;
          const card = document.createElement('button');
          card.type = 'button';
          card.className = 'theme-strip-card';
          card.innerHTML = `
            <div class="theme-strip-thumb">
              <img src="${escapeHtml(entry.thumb_url)}" alt="${escapeHtml(entry.name)}" loading="lazy" decoding="async">
            </div>
          `;
          card.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            window.location.href = entry.focus_url || item.target_url || entry.detail_url || '/library';
          });
          rail.appendChild(card);
        });
        return panel;
      }

      if (item.type === 'image_group') {
        const panel = document.createElement('section');
        panel.className = 'feed-media feed-image-group';
        panel.dataset.name = item.name;
        panel.innerHTML = `
          <div class="image-group-stage"></div>
          <div class="image-group-overlay">
            <div class="image-group-counter"></div>
          </div>
        `;
        const stage = panel.querySelector('.image-group-stage');
        const counterEl = panel.querySelector('.image-group-counter');
        const children = Array.isArray(item.items) ? item.items : [];

        function renderImageGroup(index) {
          if (!stage || !counterEl || !children.length) return;
          const safeIndex = Math.max(0, Math.min(index, children.length - 1));
          const entry = children[safeIndex];
          if (!entry || !entry.media_url) return;
          const previousIndex = Number(panel._activeChildIndex);
          const direction = Number.isFinite(previousIndex) && safeIndex < previousIndex ? -1 : 1;
          const previousMedia = stage.querySelector('.image-group-media');
          const img = document.createElement('img');
          img.className = 'image-group-media';
          img.src = entry.media_url;
          img.alt = entry.name || '';
          img.loading = 'eager';
          img.decoding = 'async';
          img.style.opacity = '0';
          img.style.transform = `translateX(${direction * 18}px)`;
          stage.appendChild(img);
          requestAnimationFrame(() => {
            img.style.opacity = '1';
            img.style.transform = 'translateX(0)';
            if (previousMedia) {
              previousMedia.style.opacity = '0';
              previousMedia.style.transform = `translateX(${direction * -12}px)`;
            }
          });
          if (previousMedia) {
            window.setTimeout(() => {
              if (previousMedia.parentNode === stage) previousMedia.remove();
            }, 220);
          }
          panel._activeChildIndex = safeIndex;
          counterEl.textContent = `${safeIndex + 1} / ${children.length}`;
          if (currentItem()?.el === panel) {
            currentItem().activeChildIndex = safeIndex;
            updateControls(currentItem());
          }
        }

        panel._renderImageGroup = renderImageGroup;
        panel._activeChildIndex = 0;
        renderImageGroup(0);
        return panel;
      }

      if (item.type === 'video') {
        const video = document.createElement('video');
        video.className = 'feed-media feed-video';
        video.muted = true;
        video.loop = true;
        video.playsInline = true;
        video.controls = false;
        video.preload = 'metadata';
        video.poster = item.thumb_url || '';
        video.dataset.src = item.media_url;
        video.dataset.name = item.name;
        video.addEventListener('timeupdate', () => updateVideoProgress(video));
        const updateDuration = () => {
          if (currentItem()?.el !== video) return;
          const duration = video.duration;
          if (duration && !isNaN(duration) && duration !== Infinity) {
            timeTotal.textContent = formatTime(duration);
          }
        };
        video.addEventListener('loadedmetadata', updateDuration);
        video.addEventListener('durationchange', updateDuration);
        video.addEventListener('play', () => {
          if (isMagnifying && currentVideoEl() === video) {
            scheduleMagnifierFrameLoop(video);
          }
        });
        video.addEventListener('seeked', () => {
          if (isMagnifying && currentVideoEl() === video) {
            updateMagnifierContent();
          }
        });
        return video;
      }

      const img = document.createElement('img');
      img.className = 'feed-media feed-image';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = item.name;
      img.src = item.media_url;
      img.dataset.name = item.name;
      return img;
    }

    async function loadFeed() {
      if (flowSession.isLoading() || !flowSession.hasMore()) return;
      try {
        const result = await flowSession.loadMore(async (cursor) => {
          const page = Number(cursor?.page || 1);
          const query = new URLSearchParams({
            page: String(page),
            size: '24',
          });
          if (seed) query.set('seed', seed);

          const res = await fetch(`/api/feed/mix?${query.toString()}`);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();

          if (!seed && data.seed) seed = String(data.seed);
          const incoming = Array.isArray(data.items) ? data.items : [];
          const normalized = incoming.map((item) => {
            if (!item || !item.type || !item.name) return null;
            const mediaEl = buildMediaElement(item);
            if (!mediaEl) return null;
            return {
              type: item.type,
              name: item.name,
              media_url: item.media_url || '',
              detail_url: item.detail_url || '#',
              thumb_url: item.thumb_url || '',
              title: item.title || '',
              subtitle: item.subtitle || '',
              target_url: item.target_url || '',
              target_label: item.target_label || '',
              items: Array.isArray(item.items) ? item.items : [],
              renderChild: typeof mediaEl._renderImageGroup === 'function' ? (index) => {
                mediaEl._renderImageGroup(index);
                return Number(mediaEl._activeChildIndex) || 0;
              } : null,
              activeChildIndex: Number(mediaEl._activeChildIndex) || 0,
              el: mediaEl,
            };
          }).filter(Boolean);

          return {
            items: normalized,
            hasMore: data.has_more !== false,
            cursor: { page: page + 1 },
          };
        });

        (result.appendedIndices || []).forEach((itemIndex) => {
          const entry = feedItems[itemIndex];
          if (entry?.el) feedContainer.appendChild(entry.el);
        });

        if (feedItems.length > 100) {
          const removeCount = 30;
          const removed = flowSession.dropHead(removeCount);
          removed.forEach((entry) => entry.el.remove());
        }
      } catch (error) {
        flowSession.setHasMore(false);
      }
    }

    function togglePlay() {
      const item = currentItem();
      if (!item || item.type !== 'video') return;
      const video = item.el;
      if (video.paused) {
        video.play();
        playStatusIcon.classList.remove('visible');
      } else {
        video.pause();
        playStatusIcon.classList.add('visible');
      }
    }

    const hammer = new Hammer(overlayLayer);
    hammer.get('swipe').set({ direction: Hammer.DIRECTION_ALL });
    hammer.on('swipeup', () => {
      if (isMagnifying) return;
      goNext();
    });
    hammer.on('swipedown', () => {
      if (isMagnifying) return;
      goPrev();
    });
    hammer.on('swipeleft', () => {
      if (isMagnifying) return;
      goGroupNext();
    });
    hammer.on('swiperight', () => {
      if (isMagnifying) return;
      goGroupPrev();
    });

    overlayLayer.addEventListener('click', () => {
      const now = Date.now();
      const delta = now - lastClickTime;

      if (delta < 250 && delta > 0) {
        if (clickTimer) clearTimeout(clickTimer);
        clickTimer = null;
        const item = currentItem();
        if (item?.type === 'video') {
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
    overlayLayer.addEventListener('touchstart', (event) => {
      const touch = event.changedTouches && event.changedTouches[0];
      if (!touch) return;
      touchStartX = touch.clientX;
      touchStartY = touch.clientY;
    }, { passive: true });
    overlayLayer.addEventListener('touchend', (event) => {
      const item = currentItem();
      if (!item || item.type !== 'image_group' || isMagnifying) return;
      const touch = event.changedTouches && event.changedTouches[0];
      if (!touch) return;
      const deltaX = touch.clientX - touchStartX;
      const deltaY = touch.clientY - touchStartY;
      if (Math.abs(deltaX) < 36 || Math.abs(deltaX) <= Math.abs(deltaY)) return;
      if (deltaX < 0) goGroupNext();
      else goGroupPrev();
    }, { passive: true });

    speedBtn.addEventListener('click', () => {
      currentSpeedIndex = (currentSpeedIndex + 1) % speedOptions.length;
      const rate = speedOptions[currentSpeedIndex];
      speedBtn.textContent = `${rate}x`;
      const item = currentItem();
      if (item?.type === 'video') {
        item.el.playbackRate = rate;
      }
    });

    favoriteBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      const name = favoriteBtn.dataset.value || '';
      if (!name) return;
      try {
        await mediaActions.toggleFavorite(name);
      } catch (error) {
        updateFavoriteState(name);
      }
    });

    collectionBtn.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await openCollectionModal();
    });
    collectionBtn.addEventListener('keydown', async (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      await openCollectionModal();
    });

    collectionModalClose.addEventListener('click', (event) => {
      event.preventDefault();
      closeCollectionModal();
    });

    collectionModal.addEventListener('click', (event) => {
      if (collectionModalOpenedAt && (Date.now() - collectionModalOpenedAt) < collectionModalGuardMs) {
        return;
      }
      if (event.target === collectionModal) closeCollectionModal();
    });
    collectionCreateBtn.addEventListener('click', async (event) => {
      event.preventDefault();
      await createCollectionInModal();
    });
    collectionNameInput.addEventListener('keydown', async (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      await createCollectionInModal();
    });
    collectionList.addEventListener('change', async (event) => {
      const inputEl = event.target.closest('input[type="checkbox"]');
      if (!inputEl) return;
      const rowEl = inputEl.closest('[data-id]');
      const collectionId = String(rowEl?.getAttribute('data-id') || '').trim();
      if (!collectionId) return;
      await toggleCollectionMembership(collectionId, !!inputEl.checked, rowEl, inputEl);
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && collectionModal.classList.contains('active')) {
        closeCollectionModal();
        return;
      }
      const target = event.target;
      if (target && typeof target.closest === 'function') {
        if (target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])')) {
          return;
        }
      }
      if (event.key === 'ArrowRight') {
        if (!goGroupNext()) goNext();
      }
      if (event.key === 'ArrowLeft') {
        if (!goGroupPrev()) goPrev();
      }
      if (event.key === 'ArrowDown') goNext();
      if (event.key === 'ArrowUp') goPrev();
      if (event.key === ' ') {
        event.preventDefault();
        togglePlay();
      }
    });

    progressBar.addEventListener('input', () => {
      const item = currentItem();
      if (!item || item.type !== 'video') return;
      const video = item.el;

      if (!isDragging) {
        isDragging = true;
        wasPlayingBeforeDrag = !video.paused;
        video.pause();
      }

      const seekTime = (progressBar.value / 100) * video.duration;
      timeCurrent.textContent = formatTime(seekTime);
      progressFill.style.width = `${progressBar.value}%`;
    });

    progressBar.addEventListener('change', () => {
      const item = currentItem();
      if (!item || item.type !== 'video') return;
      const video = item.el;

      const seekTime = (progressBar.value / 100) * video.duration;
      video.currentTime = seekTime;
      if (wasPlayingBeforeDrag) {
        video.play();
        playStatusIcon.classList.remove('visible');
      }
      isDragging = false;
    });

    captionBtn.addEventListener('click', (e) => {
      e.preventDefault();
      const item = currentItem();
      if (!item || item.type !== 'image') return;
      generateCaption(item.name);
    });

    magnifierToggle.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMagnifier(!isMagnifying);
    });

    document.querySelectorAll('.zoom-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const level = Number.parseFloat(btn.getAttribute('data-level') || '2.5');
        applyZoom(level);
      });
    });

    const magHammer = new Hammer(magnifier);
    magHammer.get('pan').set({ direction: Hammer.DIRECTION_ALL, threshold: 0 });
    let startX = 0;
    let startY = 0;

    magHammer.on('panstart', () => {
      startX = magX;
      startY = magY;
      magnifier.style.transition = 'none';
    });

    magHammer.on('panmove', (e) => {
      magX = startX + e.deltaX;
      magY = startY + e.deltaY;
      updateMagnifierPosition();
      updateMagnifierContent();
    });

    magHammer.on('panend', () => {
      magnifier.style.transition = 'transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)';
    });

    window.addEventListener('resize', () => {
      if (isMagnifying) updateMagnifierContent();
    });

    applyZoom(2.5);

    await loadFeed();
    if (feedItems.length > 0) {
      await showItem(0);
    }
  })();
