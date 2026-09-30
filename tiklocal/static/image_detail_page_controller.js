const imageDetailBoot = window.__TIKLOCAL_IMAGE_DETAIL_BOOT__ || {};

document.addEventListener('DOMContentLoaded', () => {
  const mainImage = document.getElementById('main-image');
  const imageContainer = document.getElementById('image-container');
  const zoomInBtn = document.getElementById('zoom-in-btn');
  const zoomOutBtn = document.getElementById('zoom-out-btn');
  const zoomResetBtn = document.getElementById('zoom-reset-btn');
  const zoomLabel = document.getElementById('zoom-label');
  const fullscreenBtn = document.getElementById('fullscreen-btn');
  const fullscreenModal = document.getElementById('fullscreen-modal');
  const fullscreenStage = document.getElementById('fullscreen-stage');
  const fullscreenViewerImage = document.getElementById('fullscreen-viewer-image');
  const fullscreenZoomIn = document.getElementById('fullscreen-zoom-in');
  const fullscreenZoomOut = document.getElementById('fullscreen-zoom-out');
  const fullscreenReset = document.getElementById('fullscreen-reset');
  const fullscreenZoomLabel = document.getElementById('fullscreen-zoom-label');
  const closeFullscreen = document.getElementById('close-fullscreen');
  const copyLinkBtn = document.getElementById('copy-link-btn');
  const moreMenuBtn = document.getElementById('more-menu-btn');
  const moreMenu = document.getElementById('detail-action-menu');
  const captionBtn = document.getElementById('caption-primary-btn');
  const captionPrimaryLabel = document.getElementById('caption-primary-label');
  const captionEmptyCta = document.getElementById('caption-empty-cta');
  const captionAdvancedBtn = document.getElementById('caption-advanced-btn');
  const captionContent = document.getElementById('caption-content');
  const captionTitle = document.getElementById('caption-title');
  const captionTags = document.getElementById('caption-tags');
  const embeddedGenerationCard = document.getElementById('embedded-generation-card');
  const embeddedModel = document.getElementById('embedded-model');
  const embeddedPrompt = document.getElementById('embedded-prompt');
  const embeddedPromptToggle = document.getElementById('embedded-prompt-toggle');
  const promptModal = document.getElementById('caption-prompt-modal');
  const promptCloseBtn = document.getElementById('caption-prompt-close');
  const promptCancelBtn = document.getElementById('caption-override-cancel');
  const promptGenerateBtn = document.getElementById('caption-override-generate');
  const promptSystemInput = document.getElementById('caption-override-system');
  const promptUserInput = document.getElementById('caption-override-user');
  const promptTemperatureInput = document.getElementById('caption-override-temperature');
  const promptTagsInput = document.getElementById('caption-override-tags');
  const imageUri = imageDetailBoot.uri;
  const imageUriEncoded = imageDetailBoot.uriEncoded;
  let promptConfigCache = null;
  // The cached thumbnail paints first and carries the page transition; full resolution swaps in when ready.
  const fullImage = new Image();
  fullImage.onload = () => { mainImage.src = fullImage.src; };
  fullImage.src = mainImage.dataset.fullSrc;

  const mainViewer = window.createImageViewerController({
    stage: imageContainer,
    image: mainImage,
    zoomInButton: zoomInBtn,
    zoomOutButton: zoomOutBtn,
    resetButton: zoomResetBtn,
    zoomLabel
  });
  const fullscreenViewer = window.createImageViewerController({
    stage: fullscreenStage,
    image: fullscreenViewerImage,
    zoomInButton: fullscreenZoomIn,
    zoomOutButton: fullscreenZoomOut,
    resetButton: fullscreenReset,
    zoomLabel: fullscreenZoomLabel
  });

  // Swipe the unzoomed image: sideways for its neighbour, down to put it back where it came from.
  const previousUrl = imageDetailBoot.previousUrl;
  const nextUrl = imageDetailBoot.nextUrl;
  const easeOut = 'cubic-bezier(0.22, 1, 0.36, 1)';
  let swipe = null;

  const dismiss = () => {
    if (document.referrer.startsWith(location.origin) && history.length > 1) history.back();
    else window.location.href = '/library';
  };

  const springBack = () => {
    const from = { translate: mainImage.style.translate || '0 0', scale: mainImage.style.scale || '1' };
    mainImage.style.translate = '';
    mainImage.style.scale = '';
    imageContainer.style.backgroundColor = '';
    mainImage.animate([from, { translate: '0 0', scale: '1' }], { duration: 280, easing: easeOut });
  };

  imageContainer.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0 || imageContainer.classList.contains('is-zoomed')) return;
    if (event.target.closest('button, a')) return;
    swipe = { id: event.pointerId, x: event.clientX, y: event.clientY, time: event.timeStamp, axis: '', dx: 0, dy: 0 };
  });

  imageContainer.addEventListener('pointermove', (event) => {
    if (!swipe || event.pointerId !== swipe.id) return;
    const dx = event.clientX - swipe.x;
    const dy = event.clientY - swipe.y;
    if (!swipe.axis) {
      if (Math.hypot(dx, dy) < 10) return;
      swipe.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : (dy > 0 ? 'y' : 'none');
      if (swipe.axis !== 'none') imageContainer.setPointerCapture(event.pointerId);
    }
    if (swipe.axis === 'x') {
      swipe.dx = (dx < 0 ? nextUrl : previousUrl) ? dx : dx * 0.25;
      mainImage.style.translate = `${swipe.dx}px 0`;
    } else if (swipe.axis === 'y') {
      swipe.dy = Math.max(0, dy);
      const progress = Math.min(swipe.dy / 420, 1);
      mainImage.style.translate = `${dx * 0.6}px ${swipe.dy}px`;
      mainImage.style.scale = String(1 - progress * 0.28);
      imageContainer.style.backgroundColor = `color-mix(in srgb, var(--detail-stage) ${Math.round(100 - progress * 100)}%, transparent)`;
    }
  });

  const endSwipe = (event, cancelled) => {
    if (!swipe || event.pointerId !== swipe.id) return;
    const current = swipe;
    swipe = null;
    if (!current.axis || current.axis === 'none') return;
    const speed = (current.axis === 'x' ? Math.abs(current.dx) : current.dy) / Math.max(event.timeStamp - current.time, 1);
    if (!cancelled && current.axis === 'x') {
      const target = current.dx < 0 ? nextUrl : previousUrl;
      if (target && (Math.abs(current.dx) > imageContainer.clientWidth * 0.22 || (speed > 0.5 && Math.abs(current.dx) > 30))) {
        window.location.href = target;
        return;
      }
    }
    if (!cancelled && current.axis === 'y' && (current.dy > 120 || (speed > 0.5 && current.dy > 40))) {
      dismiss();
      return;
    }
    springBack();
  };

  imageContainer.addEventListener('pointerup', (event) => endSwipe(event, false));
  imageContainer.addEventListener('pointercancel', (event) => endSwipe(event, true));
  window.addEventListener('pageshow', springBack);

  const closeMoreMenu = () => {
    if (!moreMenu || !moreMenuBtn) return;
    moreMenu.hidden = true;
    moreMenuBtn.setAttribute('aria-expanded', 'false');
  };

  const toggleMoreMenu = () => {
    if (!moreMenu || !moreMenuBtn) return;
    const nextOpen = moreMenu.hidden;
    moreMenu.hidden = !nextOpen;
    moreMenuBtn.setAttribute('aria-expanded', nextOpen ? 'true' : 'false');
  };

  moreMenuBtn?.addEventListener('click', (event) => {
    event.preventDefault();
    event.stopPropagation();
    toggleMoreMenu();
  });

  document.addEventListener('click', (event) => {
    if (!moreMenu || moreMenu.hidden) return;
    const target = event.target;
    if (moreMenu.contains(target) || moreMenuBtn?.contains(target)) return;
    closeMoreMenu();
  });
  
  // Fullscreen.
  fullscreenBtn?.addEventListener('click', () => {
    fullscreenModal.classList.remove('hidden');
    requestAnimationFrame(() => fullscreenViewer.reset());
  });
  
  closeFullscreen?.addEventListener('click', () => {
    fullscreenModal.classList.add('hidden');
  });
  
  // Close when the modal backdrop is clicked.
  fullscreenModal?.addEventListener('click', (e) => {
    if (e.target === fullscreenModal) {
      fullscreenModal.classList.add('hidden');
    }
  });
  
  // Escape closes fullscreen.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (moreMenu && !moreMenu.hidden) {
      closeMoreMenu();
      moreMenuBtn?.focus();
      return;
    }
    if (promptModal && !promptModal.classList.contains('hidden')) {
      closePromptModal();
      return;
    }
    if (!fullscreenModal.classList.contains('hidden')) {
      fullscreenModal.classList.add('hidden');
    }
  });
  
  // Copy link.
  copyLinkBtn?.addEventListener('click', async () => {
    closeMoreMenu();
    try {
      const url = window.location.origin + '/media?uri=' + imageUriEncoded;
      await navigator.clipboard.writeText(url);
      TikLocalUI.toast('Link copied to clipboard', 'success');
    } catch (err) {
      TikLocalUI.toast('Copy failed. Please copy the link manually.', 'error');
    }
  });

  const setCaptionEmptyVisible = (visible) => {
    if (!captionEmptyCta) return;
    captionEmptyCta.hidden = !visible;
    captionEmptyCta.setAttribute('aria-hidden', visible ? 'false' : 'true');
    captionEmptyCta.classList.toggle('hidden', !visible);
  };

  const renderCaption = (data) => {
    const title = data?.title || '';
    const tags = Array.isArray(data?.tags) ? data.tags : [];
    if (!title && tags.length === 0) {
      captionTitle.textContent = '';
      captionTags.innerHTML = '';
      captionTitle.classList.add('hidden');
      captionContent.classList.add('hidden');
      setCaptionEmptyVisible(true);
      if (captionPrimaryLabel) captionPrimaryLabel.textContent = 'Generate Title';
      return;
    }
    captionContent.classList.remove('hidden');
    setCaptionEmptyVisible(false);
    if (captionPrimaryLabel) captionPrimaryLabel.textContent = 'Refresh';
    captionTitle.textContent = title;
    captionTitle.classList.toggle('hidden', !title);
    captionTags.innerHTML = '';
    tags.forEach(tag => {
      const chip = document.createElement('span');
      chip.className = 'detail-tag';
      chip.textContent = tag;
      captionTags.appendChild(chip);
    });
  };

  const mediaActions = window.createFlowMediaActionsController({
    onCaptionRender: renderCaption,
    onCaptionLoading: (loading) => {
      captionBtn.disabled = loading;
      captionBtn.classList.toggle('is-loading', loading);
    },
    onError: (kind, error) => {
      if (kind === 'caption_load') setCaptionEmptyVisible(false);
      TikLocalUI.toast(error.message || 'Title request failed', 'error');
    },
    confirmCaptionReplace: () => TikLocalUI.confirm({ title: 'Replace the existing title?', message: 'The current title and tags will be regenerated.', confirmLabel: 'Replace' }),
  });

  const renderEmbeddedGeneration = (data) => {
    const embedded = data && data.embedded_generation ? data.embedded_generation : null;
    if (!embedded || (!embedded.prompt && !embedded.model)) {
      embeddedGenerationCard?.classList.add('hidden');
      return;
    }
    embeddedGenerationCard?.classList.remove('hidden');
    embeddedModel.textContent = embedded.model || 'Unknown';
    embeddedPrompt.textContent = embedded.prompt || '';
    embeddedPromptToggle.hidden = !embedded.prompt;
    if (typeof feather !== 'undefined') feather.replace();
  };

  const loadEmbeddedGeneration = async () => {
    try {
      const res = await fetch(`/api/image/embedded-metadata?uri=${encodeURIComponent(imageUri)}`);
      const data = await res.json();
      if (data.success) {
        renderEmbeddedGeneration(data.data);
      }
    } catch (err) {
      embeddedGenerationCard?.classList.add('hidden');
    }
  };

  embeddedPromptToggle?.addEventListener('click', () => {
    const expanded = embeddedPrompt.classList.toggle('is-expanded');
    embeddedPromptToggle.textContent = expanded ? 'Collapse' : 'Show All';
  });

  const openPromptModal = () => {
    if (!promptModal) return;
    promptModal.classList.remove('hidden');
  };

  const closePromptModal = () => {
    if (!promptModal) return;
    promptModal.classList.add('hidden');
  };

  const loadPromptConfig = async () => {
    if (promptConfigCache) return promptConfigCache;
    const res = await fetch('/api/ai/vision-config');
    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || 'Failed to load prompt configuration');
    }
    promptConfigCache = data.data;
    return promptConfigCache;
  };

  const fillPromptModal = async () => {
    try {
      const configData = await loadPromptConfig();
      const source = configData.effective || configData.config || configData.default;
      if (!source) return;
      promptSystemInput.value = source.system_prompt || '';
      promptUserInput.value = source.user_prompt || '';
      promptTemperatureInput.value = Number(source.temperature ?? 0.6).toFixed(1);
      promptTagsInput.value = Number(source.tags_limit ?? 5);
      openPromptModal();
    } catch (err) {
      TikLocalUI.toast(err.message || 'Failed to load prompt configuration', 'error');
    }
  };

  const collectPromptOverride = () => {
    const systemPrompt = (promptSystemInput?.value || '').trim();
    const userPrompt = (promptUserInput?.value || '').trim();
    const temperature = Number(promptTemperatureInput?.value || 0.6);
    const tagsLimit = Number(promptTagsInput?.value || 5);
    if (!systemPrompt || !userPrompt) {
      throw new Error('System Prompt and User Prompt cannot be empty');
    }
    if (temperature < 0 || temperature > 2) {
      throw new Error('temperature must be between 0 and 2');
    }
    if (!Number.isInteger(tagsLimit) || tagsLimit < 1 || tagsLimit > 20) {
      throw new Error('tags_limit must be between 1 and 20');
    }
    return {
      system_prompt: systemPrompt,
      user_prompt: userPrompt,
      temperature,
      tags_limit: tagsLimit
    };
  };

  const generateCaption = async (force = false, promptOverride = null) => {
    const result = await mediaActions.generateCaption(imageUri, {
      confirmExisting: !force, force, promptOverride,
    });
    if (result?.success) TikLocalUI.toast('Title updated', 'success');
  };

  captionBtn?.addEventListener('click', () => generateCaption());
  captionEmptyCta?.addEventListener('click', () => generateCaption());
  captionAdvancedBtn?.addEventListener('click', () => {
    closeMoreMenu();
    fillPromptModal();
  });
  promptCloseBtn?.addEventListener('click', closePromptModal);
  promptCancelBtn?.addEventListener('click', closePromptModal);
  promptModal?.addEventListener('click', (e) => {
    if (e.target === promptModal) {
      closePromptModal();
    }
  });
  promptGenerateBtn?.addEventListener('click', async () => {
    try {
      const override = collectPromptOverride();
      closePromptModal();
      await generateCaption(false, override);
    } catch (err) {
      TikLocalUI.toast(err.message || 'Invalid override configuration', 'error');
    }
  });
  mediaActions.loadCaption(imageUri);
  loadEmbeddedGeneration();
  
  // Keyboard navigation.
  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea, select') || !promptModal.classList.contains('hidden')) return;
    if (fullscreenModal.classList.contains('hidden')) {
      switch(e.key) {
        case ' ':
        case 'Enter':
          e.preventDefault();
          mainViewer.zoomIn();
          break;
        case 'f':
        case 'F':
          e.preventDefault();
          fullscreenBtn.click();
          break;
        case 'ArrowLeft':
          if (previousUrl) window.location.href = previousUrl;
          break;
        case 'ArrowRight':
          if (nextUrl) window.location.href = nextUrl;
          break;
      }
    }
  });
});

// Delete moves the file to the trash and continues to a neighbour, where Undo is offered.
function confirmDelete() {
  TikLocalUI.trash(imageDetailBoot.deleteUrl, imageDetailBoot.nextUrl || imageDetailBoot.previousUrl);
}
