(() => {
  const grid = document.getElementById('collections-grid');
  const stateEl = document.getElementById('collections-state');
  const stateTitle = document.getElementById('collections-state-title');
  const stateCopy = document.getElementById('collections-state-copy');
  const stateAction = document.getElementById('collections-state-action');
  const openBtn = document.getElementById('open-create-collection');
  const modal = document.getElementById('create-modal');
  const cancelBtn = document.getElementById('cancel-create');
  const submitBtn = document.getElementById('submit-create');
  const nameInput = document.getElementById('create-name');
  const descInput = document.getElementById('create-description');
  const renameModal = document.getElementById('rename-modal');
  const renameCancelBtn = document.getElementById('cancel-rename');
  const renameSubmitBtn = document.getElementById('submit-rename');
  const renameInput = document.getElementById('rename-name');
  const collectionsById = new Map();
  let renamingCollectionId = '';

  function showState(kind) {
    const states = {
      loading: ['Loading collections', 'Your organization stays on this device.', '', 'loader'],
      empty: ['No collections yet', 'Create a collection for media you want to revisit.', 'Create Your First Collection', 'layers'],
      error: ['Collections could not be loaded', 'Check your connection and try again.', 'Reload', 'wifi-off'],
    };
    const [title, copy, action, icon] = states[kind] || states.loading;
    stateTitle.textContent = title;
    stateCopy.textContent = copy;
    stateAction.textContent = action;
    stateAction.hidden = !action;
    const iconWrap = stateEl.querySelector('.collections-state-icon');
    iconWrap.innerHTML = `<i data-feather="${icon}"></i>`;
    stateEl.hidden = false;
    feather.replace();
  }

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let payload = {};
    try {
      payload = await response.json();
    } catch (error) {
      payload = {};
    }
    if (!response.ok || !payload.success) {
      throw new Error(payload.error || 'Request failed');
    }
    return payload.data || {};
  }

  function openCreateModal() {
    modal.classList.add('active');
    modal.setAttribute('aria-hidden', 'false');
    nameInput.focus();
  }

  function closeCreateModal() {
    modal.classList.remove('active');
    modal.setAttribute('aria-hidden', 'true');
    nameInput.value = '';
    descInput.value = '';
  }

  function openRenameModal(collectionId) {
    const id = String(collectionId || '').trim();
    const item = collectionsById.get(id);
    if (!id || !item) return;
    renamingCollectionId = id;
    renameInput.value = String(item.name || '').trim();
    renameModal.classList.add('active');
    renameModal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => {
      renameInput.focus();
      renameInput.select();
    });
  }

  function closeRenameModal() {
    renameModal.classList.remove('active');
    renameModal.setAttribute('aria-hidden', 'true');
    renameInput.value = '';
    renamingCollectionId = '';
  }

  function renderCards(items) {
    if (!Array.isArray(items) || !items.length) {
      grid.innerHTML = '';
      showState('empty');
      return;
    }
    stateEl.hidden = true;
    collectionsById.clear();
    grid.innerHTML = items.map((item) => {
      const id = String(item.id || '');
      collectionsById.set(id, item);
      const count = Number(item.item_count || 0);
      const detail = String(item.detail_url || '#');
      const name = escapeHtml(item.name || 'Untitled collection');
      const previewItems = Array.isArray(item.preview_items) ? item.preview_items.slice(0, 4) : [];
      let coverHtml;
      if (!previewItems.length) {
        coverHtml = `<div class="collection-cover-empty"><i data-feather="folder"></i></div>`;
      } else {
        const tiles = previewItems.map((preview, index) => {
          const thumbUrl = escapeHtml(String(preview.thumb_url || ''));
          const isMainVideo = index === 0 && String(preview.type || '') === 'video';
          const videoMark = isMainVideo
            ? `<span class="collection-cover-video-mark" aria-hidden="true"><i data-feather="play"></i></span>`
            : '';
          return `<span class="collection-cover-tile"><img src="${thumbUrl}" alt="" loading="lazy" decoding="async" />${videoMark}</span>`;
        }).join('');
        coverHtml = `<div class="collection-cover-collage" data-count="${previewItems.length}">${tiles}</div>`;
      }
      return `
        <article class="collection-item" data-collection-id="${id}">
          <a class="collection-card" href="${detail}">
            <div class="collection-cover">${coverHtml}</div>
            <div class="collection-meta">
              <div class="collection-name">${name}</div>
              <div class="collection-sub">${count} media items</div>
            </div>
          </a>
          <div class="collection-menu" data-menu-id="${id}">
            <button class="collection-menu-btn" type="button" data-menu-toggle="1" data-id="${id}" aria-label="More actions for ${name}" aria-expanded="false">
              <i data-feather="more-horizontal"></i>
            </button>
            <div class="collection-menu-panel">
              <button class="collection-menu-item" type="button" data-action="rename" data-id="${id}">Rename</button>
              <button class="collection-menu-item danger" type="button" data-action="delete" data-id="${id}">Delete</button>
            </div>
          </div>
        </article>
      `;
    }).join('');
    feather.replace();
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  async function loadCollections() {
    showState('loading');
    const data = await api('/api/collections');
    renderCards(data.items || []);
  }

  function closeMenus(exceptId = '') {
    grid.querySelectorAll('.collection-menu.open').forEach((node) => {
      if (exceptId && node.getAttribute('data-menu-id') === exceptId) return;
      node.classList.remove('open');
      node.querySelector('[data-menu-toggle]')?.setAttribute('aria-expanded', 'false');
    });
  }

  function toggleMenu(collectionId) {
    const id = String(collectionId || '').trim();
    if (!id) return;
    const target = grid.querySelector(`.collection-menu[data-menu-id="${id}"]`);
    if (!target) return;
    const shouldOpen = !target.classList.contains('open');
    closeMenus(id);
    target.classList.toggle('open', shouldOpen);
    target.querySelector('[data-menu-toggle]')?.setAttribute('aria-expanded', String(shouldOpen));
  }

  async function createCollection() {
    const name = String(nameInput.value || '').trim();
    const description = String(descInput.value || '').trim();
    if (!name) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating…';
    try {
      await api('/api/collections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description }),
      });
      closeCreateModal();
      await loadCollections();
    } catch (error) {
      TikLocalUI.toast(error.message || 'Failed to create collection', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create';
    }
  }

  async function submitRenameCollection() {
    const collectionId = String(renamingCollectionId || '').trim();
    const name = String(renameInput.value || '').trim();
    if (!collectionId || !name) return;
    renameSubmitBtn.disabled = true;
    renameSubmitBtn.textContent = 'Saving…';
    try {
      await api(`/api/collections/${encodeURIComponent(collectionId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      closeRenameModal();
      await loadCollections();
    } catch (error) {
      TikLocalUI.toast(error.message || 'Failed to rename collection', 'error');
    } finally {
      renameSubmitBtn.disabled = false;
      renameSubmitBtn.textContent = 'Save';
    }
  }

  async function deleteCollection(collectionId) {
    const item = collectionsById.get(collectionId);
    if (!item) return;
    const ok = await TikLocalUI.confirm({
      title: `Delete "${String(item.name || 'Untitled collection')}"?`,
      message: 'The collection is removed. The media inside it stays in your library.',
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(`/api/collections/${encodeURIComponent(collectionId)}`, { method: 'DELETE' });
      await loadCollections();
    } catch (error) {
      TikLocalUI.toast(error.message || 'Failed to delete collection', 'error');
    }
  }

  openBtn.addEventListener('click', openCreateModal);
  stateAction.addEventListener('click', () => {
    if (stateTitle.textContent === 'No collections yet') {
      openCreateModal();
      return;
    }
    loadCollections().catch(() => showState('error'));
  });
  cancelBtn.addEventListener('click', closeCreateModal);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeCreateModal();
  });
  submitBtn.addEventListener('click', createCollection);
  nameInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      createCollection();
    }
  });
  grid.addEventListener('click', async (event) => {
    const menuToggle = event.target.closest('[data-menu-toggle][data-id]');
    if (menuToggle) {
      event.preventDefault();
      event.stopPropagation();
      const collectionId = String(menuToggle.getAttribute('data-id') || '').trim();
      toggleMenu(collectionId);
      return;
    }

    const button = event.target.closest('[data-action][data-id]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    closeMenus();
    const action = String(button.getAttribute('data-action') || '').trim();
    const collectionId = String(button.getAttribute('data-id') || '').trim();
    if (!action || !collectionId) return;
    if (action === 'rename') {
      openRenameModal(collectionId);
      return;
    }
    if (action === 'delete') {
      await deleteCollection(collectionId);
    }
  });

  document.addEventListener('click', (event) => {
    if (event.target.closest('.collection-menu')) return;
    closeMenus();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (renameModal.classList.contains('active')) {
      closeRenameModal();
      return;
    }
    if (modal.classList.contains('active')) {
      closeCreateModal();
      return;
    }
    closeMenus();
  });
  renameCancelBtn.addEventListener('click', closeRenameModal);
  renameModal.addEventListener('click', (event) => {
    if (event.target === renameModal) closeRenameModal();
  });
  renameSubmitBtn.addEventListener('click', submitRenameCollection);
  renameInput.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    submitRenameCollection();
  });

  loadCollections().catch(() => showState('error'));
})();
