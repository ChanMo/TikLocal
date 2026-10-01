// Cross-document view transitions: opened media grows out of where it was tapped, and shrinks back.
// Detail pages name their own media `media-hero` in CSS; this names the matching element on other pages.
(function () {
  var HERO = 'media-hero';
  var PAGE_SOURCES = '.quick-media.active, #feed-container .feed-media.active';
  var clicked = null;
  var named = null;

  function mediaKey(href) {
    var url = new URL(href, location.href);
    if (url.origin !== location.origin) return '';
    if (url.pathname === '/image') return url.searchParams.get('uri') || '';
    if (url.pathname.indexOf('/detail/') === 0) return decodeURIComponent(url.pathname.slice(8));
    return '';
  }

  function onScreen(el) {
    var rect = el && el.getBoundingClientRect();
    return !!rect && rect.width > 0 && rect.bottom > 0 && rect.top < innerHeight;
  }

  function nameHero(el) {
    if (named) named.style.viewTransitionName = '';
    named = onScreen(el) ? el : null;
    if (named) named.style.viewTransitionName = HERO;
  }

  document.addEventListener('click', function (event) {
    var link = event.target.closest && event.target.closest('a[href]');
    clicked = link && mediaKey(link.href) ? { link: link, at: Date.now() } : null;
  }, true);

  window.addEventListener('pageswap', function (event) {
    try { sessionStorage.setItem('tiklocal:vt-from', location.href); } catch (_) {}
    if (!event.viewTransition || document.querySelector('.detail-hero')) return;
    if (!clicked || Date.now() - clicked.at > 3000) return;
    nameHero(clicked.link.querySelector('img, video') || document.querySelector(PAGE_SOURCES));
  });

  window.addEventListener('pagereveal', function (event) {
    nameHero(null);
    clicked = null;
    var from = '';
    try { from = sessionStorage.getItem('tiklocal:vt-from') || ''; } catch (_) {}
    var key = from && mediaKey(from);
    if (!event.viewTransition || !key || document.querySelector('.detail-hero')) return;
    var match = Array.prototype.find.call(document.querySelectorAll('a[href]'), function (link) {
      return mediaKey(link.href) === key && link.querySelector('img, video');
    });
    nameHero(match ? match.querySelector('img, video') : document.querySelector(PAGE_SOURCES));
    event.viewTransition.finished.finally(function () { nameHero(null); });
  });
})();
