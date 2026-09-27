// Site-wide feedback: TikLocalUI.toast(message, type, action), await TikLocalUI.confirm({...}),
// and TikLocalUI.trash(deleteUrl, nextUrl), which offers Undo on the page it lands on.
(function () {
  function icon(name) {
    var el = document.createElement('i');
    el.setAttribute('data-feather', name);
    return el;
  }

  var UNDO_KEY = 'tiklocal:undo';

  // action: optional { label, run } rendered as a button; such toasts stay a little longer.
  function toast(message, type, action) {
    type = type || 'success';
    var wrap = document.querySelector('.ui-toast-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'ui-toast-wrap';
      wrap.setAttribute('aria-live', 'polite');
      document.body.appendChild(wrap);
    }
    var el = document.createElement('div');
    el.className = 'ui-toast ' + type;
    var copy = document.createElement('span');
    copy.textContent = message;
    el.append(icon(type === 'error' ? 'alert-circle' : type === 'info' ? 'info' : 'check-circle'), copy);
    function leave() {
      el.classList.add('is-leaving');
      setTimeout(function () { el.remove(); }, 180);
    }
    if (action) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'ui-toast-action';
      button.textContent = action.label;
      button.addEventListener('click', function () {
        leave();
        action.run();
      });
      el.append(button);
    }
    wrap.replaceChildren(el);
    if (window.feather) feather.replace();
    setTimeout(leave, action ? 6000 : 3000);
  }

  function readJson(response) {
    return response.json().catch(function () { return {}; }).then(function (data) {
      if (!response.ok) throw new Error(data.error || '');
      return data;
    });
  }

  // Moves a file to the trash, then continues to nextUrl where the Undo toast appears.
  function trash(deleteUrl, nextUrl) {
    return fetch(deleteUrl, { method: 'POST', headers: { Accept: 'application/json' } })
      .then(readJson)
      .then(function (entry) {
        try { sessionStorage.setItem(UNDO_KEY, JSON.stringify({ id: entry.id, at: Date.now() })); } catch (_) {}
        location.replace(nextUrl || '/library');
      })
      .catch(function (error) { toast(error.message || 'Delete failed. Please try again.', 'error'); });
  }

  function offerUndo() {
    var entry = null;
    try {
      entry = JSON.parse(sessionStorage.getItem(UNDO_KEY));
      sessionStorage.removeItem(UNDO_KEY);
    } catch (_) {}
    if (!entry || Date.now() - entry.at > 10000) return;
    toast('Moved to trash', 'info', {
      label: 'Undo',
      run: function () {
        fetch('/api/trash/' + encodeURIComponent(entry.id) + '/restore', { method: 'POST' })
          .then(readJson)
          .then(function (data) { location.href = data.url; })
          .catch(function (error) { toast(error.message || 'Restore failed. Please try again.', 'error'); });
      },
    });
  }

  // Resolves true when confirmed; Escape, Cancel and the backdrop resolve false.
  function confirm(options) {
    options = options || {};
    return new Promise(function (resolve) {
      var previousFocus = document.activeElement;
      var mask = document.createElement('div');
      mask.className = 'ui-dialog-mask';
      mask.innerHTML =
        '<section class="ui-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ui-dialog-title" aria-describedby="ui-dialog-copy">' +
          '<h2 id="ui-dialog-title" class="ui-dialog-title"></h2>' +
          '<p id="ui-dialog-copy" class="ui-dialog-copy"></p>' +
          '<div class="ui-dialog-actions">' +
            '<button type="button" class="ui-button" data-cancel></button>' +
            '<button type="button" class="ui-button" data-accept></button>' +
          '</div>' +
        '</section>';
      mask.querySelector('.ui-dialog-title').textContent = options.title || 'Are you sure?';
      var copy = mask.querySelector('.ui-dialog-copy');
      if (options.message) copy.textContent = options.message;
      else copy.remove();
      var cancel = mask.querySelector('[data-cancel]');
      var accept = mask.querySelector('[data-accept]');
      cancel.textContent = options.cancelLabel || 'Cancel';
      accept.textContent = options.confirmLabel || 'Confirm';
      accept.classList.add(options.tone === 'danger' ? 'is-danger' : 'is-primary');

      function close(result) {
        document.removeEventListener('keydown', onKey, true);
        mask.remove();
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(result);
      }
      function onKey(event) {
        if (event.key === 'Escape') {
          event.stopPropagation();
          close(false);
        } else if (event.key === 'Tab') {
          event.preventDefault();
          (document.activeElement === cancel ? accept : cancel).focus();
        }
      }

      cancel.addEventListener('click', function () { close(false); });
      accept.addEventListener('click', function () { close(true); });
      mask.addEventListener('click', function (event) { if (event.target === mask) close(false); });
      document.addEventListener('keydown', onKey, true);
      document.body.appendChild(mask);
      cancel.focus();
    });
  }

  window.TikLocalUI = { toast: toast, confirm: confirm, trash: trash };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', offerUndo);
  else offerUndo();
})();
