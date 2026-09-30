  (async () => {
    document.body.classList.add('immersive');

    const feedContainer = document.getElementById('feed-container');
    const videoStartCover = document.getElementById('video-start-cover');
    const overlayLayer = document.getElementById('overlay-layer');
    const speedBtn = document.getElementById('speed-btn');
    const captionBtn = document.getElementById('caption-btn');
    const magnifierToolWrap = document.getElementById('magnifier-tool-wrap');
    const favoriteBtn = document.getElementById('favorite-btn');
    const collectionBtn = document.getElementById('collection-btn');
    const infoBtn = document.getElementById('info-btn');

    const playStatusIcon = document.getElementById('play-status-icon');
    const customControls = document.getElementById('custom-controls');
    const progressBar = document.getElementById('video-progress');
    const progressFill = document.getElementById('progress-fill');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');

    const captionPanel = document.getElementById('caption-panel');
    const captionTitle = document.getElementById('caption-title');
    const captionTags = document.getElementById('caption-tags');
    const flowStatus = document.getElementById('flow-state');
    const flowStatusTitle = document.getElementById('flow-state-title');
    const flowStatusDetail = document.getElementById('flow-state-detail');
    const flowStatusActions = document.getElementById('flow-state-actions');
    const flowStatusRetry = document.getElementById('flow-state-retry');
    const flowStatusNext = document.getElementById('flow-state-next');
    const flowStatusLibrary = document.getElementById('flow-state-library');
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
    const activitySessionId = globalThis.crypto?.randomUUID?.()
      || `flow-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    let activeActivity = null;

    function postActivity(events, useBeacon = false) {
      const valid = events.filter(Boolean);
      if (!valid.length) return;
      const body = JSON.stringify({
        events: valid,
        _csrf_token: window.TikLocalSecurity?.csrfToken || '',
      });
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon('/api/activity', new Blob([body], { type: 'application/json' }));
        return;
      }
      fetch('/api/activity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        keepalive: true,
      }).catch(() => {});
    }

    function activityTarget(item) {
      if (!item) return null;
      if (item.type === 'image_group') {
        const entries = Array.isArray(item.items) ? item.items : [];
        const index = Math.max(0, Math.min(Number(item.activeChildIndex) || 0, entries.length - 1));
        const entry = entries[index];
        return entry?.name ? { uri: entry.name, type: 'image', el: item.el } : null;
      }
      if (!['video', 'image'].includes(item.type) || !item.name) return null;
      return { uri: item.name, type: item.type, el: item.el };
    }

    function beginActivity(item) {
      const target = activityTarget(item);
      if (!target) return null;
      if (target.type === 'video' && target.el) {
        target.el._completedInView = false;
        target.el._activityPlayedSeconds = 0;
        target.el._activityLastPosition = null;
      }
      activeActivity = { target, startedAt: performance.now() };
      return {
        session_id: activitySessionId,
        uri: target.uri,
        media_type: target.type,
        surface: 'flow',
        event: 'impression',
      };
    }

    function finishActivity() {
      if (!activeActivity) return null;
      const { target, startedAt } = activeActivity;
      activeActivity = null;
      const visibleMs = Math.max(0, Math.round(performance.now() - startedAt));
      let ratio = null;
      if (target.type === 'video' && Number.isFinite(target.el?.duration) && target.el.duration > 0) {
        ratio = Math.max(0, Math.min(Number(target.el._activityPlayedSeconds || 0) / target.el.duration, 1));
      }
      const completed = target.type === 'video'
        ? !!target.el?._completedInView
        : visibleMs >= 5000;
      const skipped = target.type === 'video'
        ? visibleMs < 2200 && (ratio === null || ratio < 0.12)
        : visibleMs < 1600;
      return {
        session_id: activitySessionId,
        uri: target.uri,
        media_type: target.type,
        surface: 'flow',
        event: completed ? 'complete' : (skipped ? 'skip' : 'consumed'),
        ratio,
        visible_ms: visibleMs,
      };
    }

    let currentSpeedIndex = 1;
    let isDragging = false;
    let wasPlayingBeforeDrag = false;
    let flowLoadingTimer = null;
    let videoStartCoverTimer = null;
    let videoActivationId = 0;

    function isVideoStartReady(videoEl) {
      return videoEl?._startReady === true
        && videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
    }

    function showVideoStartCover(item) {
      clearTimeout(videoStartCoverTimer);
      // The thumbnail matches what the page slid in with, so the hand-off does not flash black.
      videoStartCover.style.backgroundImage = item?.thumb_url ? `url("${item.thumb_url}")` : '';
      videoStartCover.classList.remove('is-waiting');
      videoStartCover.classList.add('is-visible');
      videoStartCover.setAttribute('aria-hidden', 'false');
      videoStartCoverTimer = setTimeout(() => {
        videoStartCover.classList.add('is-waiting');
      }, 250);
    }

    function hideVideoStartCover() {
      clearTimeout(videoStartCoverTimer);
      videoStartCover.classList.remove('is-visible', 'is-waiting');
      videoStartCover.setAttribute('aria-hidden', 'true');
    }

    function showFlowStatus(kind, title, detail = '') {
      clearTimeout(flowLoadingTimer);
      flowLoadingTimer = null;
      flowStatus.dataset.kind = kind;
      flowStatusTitle.textContent = title;
      flowStatusDetail.textContent = detail;
      flowStatusRetry.hidden = !['error', 'media-error'].includes(kind);
      flowStatusNext.hidden = kind !== 'media-error';
      flowStatusLibrary.hidden = !['empty', 'error'].includes(kind);
      flowStatusActions.hidden = !['empty', 'error', 'media-error'].includes(kind);
      flowStatus.classList.add('is-visible');
      flowStatus.setAttribute('aria-hidden', 'false');
    }

    function hideFlowStatus() {
      clearTimeout(flowLoadingTimer);
      flowLoadingTimer = null;
      flowStatus.classList.remove('is-visible');
      flowStatus.setAttribute('aria-hidden', 'true');
    }

    function scheduleFlowLoadingStatus() {
      clearTimeout(flowLoadingTimer);
      flowLoadingTimer = setTimeout(() => {
        showFlowStatus('loading', 'Preparing your media');
      }, 250);
    }

    const { formatTime } = uiShared;
    const currentItem = () => flowSession.currentItem();
    const getCurrentIndex = () => flowSession.getIndex();

    const magnifier = uiShared.createMagnifier({
      lens: document.getElementById('magnifier'),
      toggle: document.getElementById('magnifier-toggle'),
      zoomOptions: document.getElementById('zoom-options'),
      badge: document.getElementById('mag-badge'),
      zoomButtons: document.querySelectorAll('.zoom-btn'),
      largeClass: 'magnifier-large',
      settleTransition: 'transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)',
      setMagnifying: (enabled) => flowState.setMagnifying(enabled),
      target: () => {
        const item = currentItem();
        if (item?.type === 'video') return { type: 'video', el: item.el };
        if (item?.type === 'image') return { type: 'image', el: item.el };
        if (item?.type === 'image_group') return { type: 'image', el: item.el?.querySelector('.image-group-media') };
        return null;
      },
    });

    const flowState = window.createFlowStateController({
      getMediaType: () => currentItem()?.type || '',
      canMagnifyMedia: (mediaType) => mediaType === 'image' || mediaType === 'video',
      onImmersiveChange: (enabled) => document.body.classList.toggle('immersive-mode', !!enabled),
      onMagnifyingChange: (enabled) => magnifier.onStateChange(enabled),
    });

    const toggleUI = () => flowState.toggleImmersive();

    const collections = window.TikLocalCollections.createPicker({
      button: collectionBtn,
      countEl: document.getElementById('collection-count'),
      modal: document.getElementById('collection-modal'),
      closeBtn: document.getElementById('collection-modal-close'),
      meta: document.getElementById('collection-modal-meta'),
      createBtn: document.getElementById('collection-create-btn'),
      nameInput: document.getElementById('collection-name-input'),
      list: document.getElementById('collection-list'),
      itemClass: 'collection-modal-item',
      emptyClass: 'collection-modal-empty',
      currentUri: () => (currentItem()?.type === 'theme_strip' ? '' : currentDisplayEntry()?.name),
    });

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
      onFavoriteChange: (value, name) => {
        if (favoriteBtn.dataset.value !== name) return;
        favoriteBtn.classList.toggle('is-active', !!value);
        favoriteBtn.setAttribute('aria-pressed', String(!!value));
        favoriteBtn.setAttribute('aria-label', value ? 'Remove from favorites' : 'Add to favorites');
        favoriteBtn.title = value ? 'Remove from favorites' : 'Add to favorites';
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
      confirmCaptionReplace: () => TikLocalUI.confirm({ title: 'Replace the existing title?', message: 'The current title and tags will be regenerated.', confirmLabel: 'Replace' }),
    });


    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    async function goNext() {
      if (getCurrentIndex() >= feedItems.length - 1 && flowSession.hasMore()) {
        await loadFeed();
      }
      slidePage(1);
    }

    function goPrev() {
      slidePage(-1);
    }

    // Paging moves the current item and its neighbour together, so a swipe follows the finger.
    const pageEase = 'cubic-bezier(0.22, 1, 0.36, 1)';
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let pager = null;
    let settling = false;

    function setPeek(item, visible) {
      if (!item) return;
      item.el.classList.toggle('active', visible);
      item.el.style.display = visible ? (item.type === 'theme_strip' ? '' : 'block') : 'none';
      item.el.style.removeProperty('transition');
      item.el.style.translate = '';
    }

    function placePage(offset, duration = 0) {
      const transition = duration ? `translate ${duration}ms ${pageEase}` : 'none';
      const height = feedContainer.clientHeight;
      [currentItem()?.el, videoStartCover].forEach((el) => {
        if (!el) return;
        // Inline !important: the global stylesheet disables transitions on img/video.
        el.style.setProperty('transition', transition, 'important');
        el.style.translate = `0 ${offset}px`;
      });
      if (pager?.peer) {
        pager.peer.el.style.setProperty('transition', transition, 'important');
        pager.peer.el.style.translate = `0 ${offset + pager.dir * height}px`;
      }
    }

    function beginPage(dir) {
      const index = getCurrentIndex() + dir;
      const peer = feedItems[index] || null;
      if (pager?.peer && pager.peer !== peer) setPeek(pager.peer, false);
      pager = { dir, index, peer };
      if (peer) setPeek(peer, true);
    }

    function settlePage(commit, offset) {
      if (!pager) return;
      const { index, peer, dir } = pager;
      const height = feedContainer.clientHeight;
      const moving = commit && !!peer;
      const target = moving ? -dir * height : 0;
      const distance = Math.abs(target - offset) / Math.max(height, 1);
      const duration = reduceMotion.matches ? 0 : Math.round(Math.min(340, Math.max(170, distance * 380)));
      settling = true;
      if (duration) placePage(target, duration);
      window.setTimeout(() => {
        [currentItem()?.el, videoStartCover].forEach((el) => {
          if (!el) return;
          el.style.removeProperty('transition');
          el.style.translate = '';
        });
        if (moving) {
          peer.el.style.removeProperty('transition');
          peer.el.style.translate = '';
        } else {
          setPeek(peer, false);
        }
        pager = null;
        settling = false;
        if (moving) showItem(index);
      }, duration);
    }

    function slidePage(dir) {
      if (settling || pager || !feedItems[getCurrentIndex() + dir]) return;
      beginPage(dir);
      placePage(0);
      void feedContainer.offsetHeight;
      settlePage(true, 0);
    }

    function goGroupNext() {
      const item = currentItem();
      if (!item || item.type !== 'image_group' || typeof item.renderChild !== 'function') return false;
      const entries = Array.isArray(item.items) ? item.items : [];
      const nextIndex = (Number(item.activeChildIndex) || 0) + 1;
      if (nextIndex >= entries.length) return false;
      const previousActivity = finishActivity();
      item.activeChildIndex = item.renderChild(nextIndex);
      postActivity([previousActivity, beginActivity(item)]);
      return true;
    }

    function goGroupPrev() {
      const item = currentItem();
      if (!item || item.type !== 'image_group' || typeof item.renderChild !== 'function') return false;
      const nextIndex = (Number(item.activeChildIndex) || 0) - 1;
      if (nextIndex < 0) return false;
      const previousActivity = finishActivity();
      item.activeChildIndex = item.renderChild(nextIndex);
      postActivity([previousActivity, beginActivity(item)]);
      return true;
    }

    function updateFavoriteState(name) {
      mediaActions.syncFavorite(name)
        .catch(() => {
          if (favoriteBtn.dataset.value === name) favoriteBtn.classList.remove('is-active');
        });
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
        collections.sync('');
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
        collections.sync(mediaName);
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

    function waitForVideoState(videoEl, eventNames, condition, timeoutMs = 8000) {
      if (condition()) return Promise.resolve();
      return new Promise((resolve, reject) => {
        let timeoutId = null;
        const names = Array.isArray(eventNames) ? eventNames : [eventNames];
        const cleanup = () => {
          names.forEach((name) => videoEl.removeEventListener(name, onStateChange));
          videoEl.removeEventListener('error', onError);
          clearTimeout(timeoutId);
        };
        const onStateChange = () => {
          if (!condition()) return;
          cleanup();
          resolve();
        };
        const onError = () => {
          cleanup();
          reject(new Error('Video failed while preparing random start'));
        };
        names.forEach((name) => videoEl.addEventListener(name, onStateChange));
        videoEl.addEventListener('error', onError, { once: true });
        timeoutId = setTimeout(() => {
          cleanup();
          reject(new Error('Timed out while preparing random start'));
        }, timeoutMs);
      });
    }

    function prepareVideoStart(videoEl) {
      if (!videoEl) return Promise.reject(new Error('Missing video element'));
      if (isVideoStartReady(videoEl)) return Promise.resolve(videoEl);
      if (videoEl._startPromise) return videoEl._startPromise;

      videoEl._startReady = false;
      videoEl.preload = 'auto';
      ensureVideoSrc(videoEl);
      videoEl._startPromise = (async () => {
        await waitForVideoState(
          videoEl,
          ['loadeddata', 'canplay'],
          () => videoEl.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA,
        );
        videoEl._startReady = true;
        videoEl._startPromise = null;
        videoEl._activityLastPosition = videoEl.currentTime;
        videoEl.preload = 'metadata';
        return videoEl;
      })().catch((error) => {
        videoEl._startPromise = null;
        videoEl.preload = 'metadata';
        throw error;
      });
      return videoEl._startPromise;
    }

    function preloadNextVideo() {
      for (let i = getCurrentIndex() + 1; i < feedItems.length; i++) {
        const item = feedItems[i];
        if (item.type !== 'video') continue;
        const v = item.el;
        if (v) prepareVideoStart(v).catch(() => {});
        break;
      }
    }

    function waitForPresentedVideoFrame(videoEl, timeoutMs = 350) {
      if (typeof videoEl.requestVideoFrameCallback !== 'function') return Promise.resolve();
      return new Promise((resolve) => {
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          clearTimeout(timeoutId);
          resolve();
        };
        const timeoutId = setTimeout(finish, timeoutMs);
        videoEl.requestVideoFrameCallback(finish);
      });
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

    function clearPreviousState(prevItem) {
      magnifier.toggle(false);

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
      const previousActivity = finishActivity();
      clearPreviousState(prevItem);

      flowSession.setIndex(safeIndex);
      const item = currentItem();
      if (!item) return;
      const activationId = ++videoActivationId;
      postActivity([previousActivity, beginActivity(item)]);
      flowState.onMediaChanged();

      const needsVideoStartCover = item.type === 'video' && !isVideoStartReady(item.el);
      if (needsVideoStartCover) showVideoStartCover(item);
      else hideVideoStartCover();

      item.el.style.display = item.type === 'theme_strip' ? '' : 'block';
      requestAnimationFrame(() => item.el.classList.add('active'));
      updateControls(item);
      preloadNextVideo();

      if (item.type === 'video') {
        progressBar.disabled = false;
        if (item.el._loadFailed) handleMediaFailure(item.el);
        item.el.playbackRate = speedOptions[currentSpeedIndex];
        progressBar.value = 0;
        progressFill.style.width = '0%';
        timeCurrent.textContent = '00:00';
        timeTotal.textContent = formatTime(item.el.duration);
        mediaActions.clearCaption();

        try {
          await prepareVideoStart(item.el);
        } catch (error) {
          if (activationId !== videoActivationId || currentItem()?.el !== item.el) return;
          hideVideoStartCover();
          if (item.el._loadFailed) handleMediaFailure(item.el);
          item.el.muted = false;
          const fallbackPlayPromise = item.el.play();
          if (fallbackPlayPromise !== undefined) {
            fallbackPlayPromise
              .then(() => playStatusIcon.classList.remove('visible'))
              .catch(() => playStatusIcon.classList.add('visible'));
          } else {
            playStatusIcon.classList.remove('visible');
          }
          preloadNextVideo();
          return;
        }

        if (activationId !== videoActivationId || currentItem()?.el !== item.el) return;
        item.el.muted = false;
        try {
          const playPromise = item.el.play();
          if (playPromise !== undefined) await playPromise;
          await waitForPresentedVideoFrame(item.el);
          if (activationId !== videoActivationId || currentItem()?.el !== item.el) return;
          playStatusIcon.classList.remove('visible');
        } catch (error) {
          if (activationId !== videoActivationId || currentItem()?.el !== item.el) return;
          playStatusIcon.classList.add('visible');
        }
        if (needsVideoStartCover) hideVideoStartCover();
      } else if (item.type === 'image_group') {
        mediaActions.clearCaption();
        if (typeof item.renderChild === 'function') {
          item.activeChildIndex = item.renderChild(Number(item.activeChildIndex) || 0);
        }
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
      } else if (item.type === 'theme_strip') {
        mediaActions.clearCaption();
        playStatusIcon.classList.add('hidden');
        playStatusIcon.classList.remove('visible');
      } else {
        playStatusIcon.classList.remove('visible');
        mediaActions.loadCaption(item.name);
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
            <h2>${escapeHtml(item.title || 'Featured Theme')}</h2>
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

        function renderImageGroup(index, force = false) {
          if (!stage || !counterEl || !children.length) return;
          const safeIndex = Math.max(0, Math.min(index, children.length - 1));
          const entry = children[safeIndex];
          if (!entry || !entry.media_url) return;
          const previousIndex = Number(panel._activeChildIndex);
          const direction = Number.isFinite(previousIndex) && safeIndex < previousIndex ? -1 : 1;
          const previousMedia = stage.querySelector('.image-group-media');
          const img = document.createElement('img');
          img.className = 'image-group-media';
          img.addEventListener('error', () => handleMediaFailure(panel));
          img.src = force
            ? `${entry.media_url}${entry.media_url.includes('?') ? '&' : '?'}retry=${Date.now()}`
            : entry.media_url;
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
        if (item.thumb_url) video.poster = item.thumb_url;
        video.dataset.src = item.media_url;
        video.dataset.name = item.name;
        video.addEventListener('error', () => {
          video._loadFailed = true;
          handleMediaFailure(video);
        });
        video.addEventListener('loadeddata', () => {
          video._loadFailed = false;
        });
        video.addEventListener('timeupdate', () => {
          updateVideoProgress(video);
          const duration = Number(video.duration || 0);
          const current = Number(video.currentTime || 0);
          const previous = video._activityLastPosition;
          const playedDelta = current - previous;
          if (Number.isFinite(previous) && playedDelta > 0 && playedDelta <= 2.5) {
            video._activityPlayedSeconds = Number(video._activityPlayedSeconds || 0) + playedDelta;
          }
          video._activityLastPosition = current;
          if (duration > 0 && previous > duration * 0.85 && current < 1.5) {
            video._completedInView = true;
            postActivity([{
              session_id: activitySessionId,
              uri: item.name,
              media_type: 'video',
              surface: 'flow',
              event: 'replay',
            }]);
          }
          video._lastActivityTime = current;
        });
        const updateDuration = () => {
          if (currentItem()?.el !== video) return;
          const duration = video.duration;
          if (duration && !isNaN(duration) && duration !== Infinity) {
            timeTotal.textContent = formatTime(duration);
          }
        };
        video.addEventListener('loadedmetadata', updateDuration);
        video.addEventListener('durationchange', updateDuration);
        video.addEventListener('play', () => magnifier.onVideoPlay(video));
        video.addEventListener('seeked', () => magnifier.onVideoSeeked(video));
        return video;
      }

      const img = document.createElement('img');
      img.className = 'feed-media feed-image';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.alt = item.name;
      img.addEventListener('error', () => handleMediaFailure(img));
      img.src = item.media_url;
      img.dataset.name = item.name;
      return img;
    }

    async function loadFeed() {
      if (flowSession.isLoading() || !flowSession.hasMore()) return;
      const isInitialLoad = feedItems.length === 0;
      if (isInitialLoad) scheduleFlowLoadingStatus();
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
              recommendation_reason: item.recommendation_reason || '',
              items: Array.isArray(item.items) ? item.items : [],
              renderChild: typeof mediaEl._renderImageGroup === 'function' ? (index, force = false) => {
                mediaEl._renderImageGroup(index, force);
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
        if (feedItems.length) {
          hideFlowStatus();
        } else if (!flowSession.hasMore()) {
          showFlowStatus('empty', 'There is nothing to browse yet', 'Add media and refresh the index to see it here.');
        }
        return result;
      } catch (error) {
        clearTimeout(flowLoadingTimer);
        flowLoadingTimer = null;
        const reachedEnd = getCurrentIndex() >= feedItems.length - 1;
        if (isInitialLoad || reachedEnd) {
          showFlowStatus('error', 'Your media could not be loaded', 'Try again or browse the existing media in your library.');
        }
        return null;
      }
    }

    function handleMediaFailure(mediaEl) {
      if (currentItem()?.el !== mediaEl) return;
      showFlowStatus('media-error', 'This media cannot be opened', 'The file may have moved, be offline, or use an unsupported format.');
    }

    async function retryCurrentMedia() {
      const item = currentItem();
      if (!item) return;
      hideFlowStatus();
      const retryUrl = `${item.media_url}${item.media_url.includes('?') ? '&' : '?'}retry=${Date.now()}`;
      if (item.type === 'video') {
        item.el.pause();
        item.el._loadFailed = false;
        item.el._startReady = false;
        item.el._startPromise = null;
        item.el.src = retryUrl;
        item.el.load();
        await showItem(getCurrentIndex());
      } else if (item.type === 'image') {
        item.el.src = retryUrl;
      } else if (item.type === 'image_group' && typeof item.renderChild === 'function') {
        item.activeChildIndex = item.renderChild(Number(item.activeChildIndex) || 0, true);
      }
    }

    async function retryFlowLoad() {
      flowSession.setHasMore(true);
      showFlowStatus('loading', 'Reloading');
      const result = await loadFeed();
      if (result && feedItems.length && getCurrentIndex() < 0) {
        await showItem(0);
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

    // One pointer gesture for the stage: drag to page, tap to play or reveal, double-tap to favorite.
    const tapSlop = 10;
    const doubleTapMs = 250;
    const longPressMs = 450;
    let gesture = null;
    let lastTap = { time: 0, x: 0, y: 0 };
    let tapTimer = null;

    function likeAt(x, y) {
      if (favoriteBtn.hidden || !favoriteBtn.dataset.value) return;
      const heart = document.createElement('div');
      heart.className = 'tap-heart';
      heart.style.left = `${x}px`;
      heart.style.top = `${y}px`;
      heart.style.setProperty('--tilt', `${Math.round(Math.random() * 28 - 14)}deg`);
      heart.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
      heart.addEventListener('animationend', () => heart.remove());
      document.body.appendChild(heart);
      if (!favoriteBtn.classList.contains('is-active')) favoriteBtn.click();
    }

    function handleTap(x, y) {
      const now = performance.now();
      const isDouble = now - lastTap.time < doubleTapMs && Math.hypot(x - lastTap.x, y - lastTap.y) < 40;
      lastTap = isDouble ? { time: 0, x: 0, y: 0 } : { time: now, x, y };
      clearTimeout(tapTimer);
      if (isDouble) {
        likeAt(x, y);
        return;
      }
      // A single tap waits out the double-tap window, so a double tap never touches playback.
      const item = currentItem();
      tapTimer = setTimeout(() => {
        if (currentItem() !== item) return;
        if (item?.type === 'video') togglePlay();
        else toggleUI();
      }, doubleTapMs);
    }

    function releaseVelocity(samples) {
      const last = samples[samples.length - 1];
      const first = samples.find(([time]) => last[0] - time <= 90) || last;
      return last[0] > first[0] ? (last[1] - first[1]) / (last[0] - first[0]) : 0;
    }

    overlayLayer.addEventListener('pointerdown', (event) => {
      if (!event.isPrimary || event.button !== 0 || magnifier.isActive() || settling) return;
      overlayLayer.setPointerCapture(event.pointerId);
      gesture = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        mode: 'pending',
        offset: 0,
        dx: 0,
        samples: [[event.timeStamp, event.clientY]],
        longPressed: false,
      };
      gesture.timer = setTimeout(() => {
        if (gesture?.mode !== 'pending') return;
        gesture.longPressed = true;
        clearTimeout(tapTimer);
        toggleUI();
      }, longPressMs);
    });

    overlayLayer.addEventListener('pointermove', (event) => {
      if (!gesture || event.pointerId !== gesture.id) return;
      const dx = event.clientX - gesture.x;
      const dy = event.clientY - gesture.y;
      if (gesture.mode === 'pending') {
        if (Math.hypot(dx, dy) < tapSlop) return;
        clearTimeout(gesture.timer);
        clearTimeout(tapTimer);
        gesture.mode = gesture.longPressed ? 'none' : (Math.abs(dy) > Math.abs(dx) ? 'vertical' : 'horizontal');
      }
      if (gesture.mode === 'horizontal') gesture.dx = dx;
      if (gesture.mode !== 'vertical') return;
      const dir = dy < 0 ? 1 : -1;
      if (!pager || pager.dir !== dir) beginPage(dir);
      gesture.offset = pager.peer ? dy : dy * 0.25;
      gesture.samples.push([event.timeStamp, event.clientY]);
      if (gesture.samples.length > 6) gesture.samples.shift();
      placePage(gesture.offset);
    });

    function endGesture(event, cancelled) {
      if (!gesture || event.pointerId !== gesture.id) return;
      const current = gesture;
      gesture = null;
      clearTimeout(current.timer);
      if (current.mode === 'vertical' && pager) {
        const height = feedContainer.clientHeight;
        const toward = -current.offset * pager.dir;
        const fling = -releaseVelocity(current.samples) * pager.dir > 0.45;
        const commit = !cancelled && (toward > height * 0.22 || (fling && toward > 24));
        if (commit && !pager.peer && pager.dir > 0 && flowSession.hasMore()) loadFeed();
        settlePage(commit, current.offset);
        return;
      }
      if (cancelled) return;
      if (current.mode === 'horizontal' && Math.abs(current.dx) > 36) {
        if (current.dx < 0) goGroupNext();
        else goGroupPrev();
        return;
      }
      if (current.mode === 'pending' && !current.longPressed) handleTap(event.clientX, event.clientY);
    }

    overlayLayer.addEventListener('pointerup', (event) => endGesture(event, false));
    overlayLayer.addEventListener('pointercancel', (event) => endGesture(event, true));

    // Wheel and trackpad page once per gesture; momentum is absorbed until the wheel goes quiet.
    let wheelLocked = false;
    let wheelQuietTimer = null;
    overlayLayer.addEventListener('wheel', (event) => {
      event.preventDefault();
      if (magnifier.isActive()) return;
      clearTimeout(wheelQuietTimer);
      wheelQuietTimer = setTimeout(() => { wheelLocked = false; }, 200);
      if (wheelLocked || Math.abs(event.deltaY) < 12) return;
      wheelLocked = true;
      if (event.deltaY > 0) goNext();
      else goPrev();
    }, { passive: false });

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
      if (!name || favoriteBtn.disabled) return;
      const item = currentItem();
      favoriteBtn.disabled = true;
      try {
        const isFavorite = await mediaActions.toggleFavorite(name);
        postActivity([{
          session_id: activitySessionId,
          uri: name,
          media_type: item?.type === 'video' ? 'video' : 'image',
          surface: 'flow',
          event: isFavorite ? 'favorite' : 'unfavorite',
        }]);
      } catch (error) {
        if (favoriteBtn.dataset.value === name) {
          favoriteBtn.title = 'Favorite was not saved. Please try again.';
          favoriteBtn.setAttribute('aria-label', favoriteBtn.title);
        }
      } finally {
        favoriteBtn.disabled = false;
      }
    });

    infoBtn.addEventListener('click', () => {
      const target = activityTarget(currentItem());
      if (!target) return;
      postActivity([{
        session_id: activitySessionId,
        uri: target.uri,
        media_type: target.type,
        surface: 'flow',
        event: 'open_detail',
      }]);
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && collections.isOpen()) {
        collections.close();
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

    flowStatusRetry.addEventListener('click', async () => {
      if (flowStatus.dataset.kind === 'media-error') {
        await retryCurrentMedia();
      } else {
        await retryFlowLoad();
      }
    });

    flowStatusNext.addEventListener('click', async () => {
      hideFlowStatus();
      await goNext();
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
      mediaActions.generateCaption(item.name, { confirmExisting: true });
    });

    window.addEventListener('pagehide', () => {
      postActivity([finishActivity()], true);
    });


    await loadFeed();
    if (feedItems.length > 0) {
      await showItem(0);
    }
  })();
