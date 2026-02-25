(function (global) {
  'use strict';

  function noop() {}

  function createFlowStateController(options) {
    var opts = options || {};
    var getMediaType = typeof opts.getMediaType === 'function' ? opts.getMediaType : function () { return ''; };
    var canMagnifyMedia = typeof opts.canMagnifyMedia === 'function'
      ? opts.canMagnifyMedia
      : function (mediaType) { return mediaType === 'image'; };
    var onImmersiveChange = typeof opts.onImmersiveChange === 'function' ? opts.onImmersiveChange : noop;
    var onMagnifyingChange = typeof opts.onMagnifyingChange === 'function' ? opts.onMagnifyingChange : noop;

    var immersive = false;
    var magnifying = false;

    function canMagnify() {
      try {
        return !!canMagnifyMedia(getMediaType());
      } catch (error) {
        return false;
      }
    }

    function setImmersive(enabled) {
      var next = !!enabled;
      if (next === immersive) return immersive;

      if (next && magnifying) {
        magnifying = false;
        onMagnifyingChange(false);
      }

      immersive = next;
      onImmersiveChange(immersive);
      return immersive;
    }

    function toggleImmersive() {
      return setImmersive(!immersive);
    }

    function setMagnifying(enabled) {
      var next = !!enabled && canMagnify();
      if (next === magnifying) return magnifying;

      if (next && immersive) {
        immersive = false;
        onImmersiveChange(false);
      }

      magnifying = next;
      onMagnifyingChange(magnifying);
      return magnifying;
    }

    function toggleMagnifying() {
      return setMagnifying(!magnifying);
    }

    function onMediaChanged() {
      if (!canMagnify() && magnifying) {
        magnifying = false;
        onMagnifyingChange(false);
      }
    }

    function reset() {
      immersive = false;
      magnifying = false;
      onImmersiveChange(false);
      onMagnifyingChange(false);
    }

    return {
      isImmersive: function () { return immersive; },
      isMagnifying: function () { return magnifying; },
      setImmersive: setImmersive,
      toggleImmersive: toggleImmersive,
      setMagnifying: setMagnifying,
      toggleMagnifying: toggleMagnifying,
      onMediaChanged: onMediaChanged,
      reset: reset,
    };
  }

  global.createFlowStateController = createFlowStateController;
})(window);
