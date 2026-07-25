import { useCallback, useEffect } from "react";
import {
  setAudioModeAsync,
  useAudioPlayer,
  useAudioPlayerStatus,
} from "expo-audio";

import type { Track } from "./model";

export function useRadioPlayer(initialTrack: Track) {
  const player = useAudioPlayer(null, {
    updateInterval: 250,
    keepAudioSessionActive: true,
  });
  const status = useAudioPlayerStatus(player);

  const load = useCallback(
    (track: Track, shouldPlay: boolean) => {
      player.replace(track.source);
      player.setActiveForLockScreen(
        true,
        {
          title: track.title,
          artist: track.artist,
          albumTitle: track.album,
        },
        {
          showSeekForward: false,
          showSeekBackward: false,
        },
      );
      if (shouldPlay) {
        player.play();
      }
    },
    [player],
  );
  const play = useCallback(() => player.play(), [player]);
  const pause = useCallback(() => player.pause(), [player]);
  const clear = useCallback(() => {
    player.pause();
    player.replace(null);
    player.clearLockScreenControls();
  }, [player]);
  const replay = useCallback(() => {
    void player.seekTo(0).then(() => player.play());
  }, [player]);

  useEffect(() => {
    void setAudioModeAsync({
      playsInSilentMode: true,
      interruptionMode: "doNotMix",
      shouldPlayInBackground: true,
      shouldRouteThroughEarpiece: false,
      allowsRecording: false,
    });
    load(initialTrack, false);

    return () => {
      player.clearLockScreenControls();
    };
  }, [initialTrack, load, player]);

  return {
    status,
    load,
    play,
    pause,
    clear,
    replay,
  };
}
