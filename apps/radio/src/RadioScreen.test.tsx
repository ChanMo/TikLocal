import { expect, jest, test } from "@jest/globals";
import {
  render,
  screen,
  userEvent,
} from "@testing-library/react-native";

import type { RadioSnapshot, Station, Track } from "./model";
import type { RadioSession } from "./radio";
import { RadioScreen } from "./RadioScreen";

const stations: Station[] = [
  {
    id: "default",
    name: "Daily Signal",
    description: "A quiet mix",
  },
  {
    id: "recent",
    name: "New Air",
    description: "Recently arrived",
  },
  {
    id: "favorites",
    name: "Kept Close",
    description: "Guided by favorites",
  },
];

const track: Track = {
  id: "track-1",
  uri: "@music/track-1.mp3",
  title: "Paper Sun",
  artist: "Field Unit",
  album: "Private Frequency",
  source: 1,
  accent: "#D9633B",
  isFavorite: false,
};

function snapshot(overrides: Partial<RadioSnapshot> = {}): RadioSnapshot {
  return {
    station: stations[0]!,
    stations,
    track,
    playback: { kind: "paused" },
    sync: { kind: "ready", serverName: "Studio" },
    currentTime: 30,
    duration: 120,
    isFavorite: false,
    encoreCount: 0,
    sleepMinutes: 0,
    ...overrides,
  };
}

function session(overrides: Partial<RadioSnapshot> = {}): RadioSession {
  return {
    snapshot: snapshot(overrides),
    play: jest.fn(),
    pause: jest.fn(),
    next: jest.fn(),
    selectStation: jest.fn(),
    toggleFavorite: jest.fn(),
    encore: jest.fn(),
    setSleepTimer: jest.fn(),
  };
}

test("exposes station selection, server action, and playback progress", async () => {
  const radio = session();
  const onConnectionPress = jest.fn();
  const user = userEvent.setup();
  await render(
    <RadioScreen
      radio={radio}
      onConnectionPress={onConnectionPress}
    />,
  );

  expect(screen.getByText("Paper Sun")).toBeOnTheScreen();
  expect(screen.getByText("Field Unit")).toBeOnTheScreen();
  expect(screen.getByText("STUDIO")).toBeOnTheScreen();
  expect(
    screen.getByRole("button", { name: "Daily Signal" }),
  ).toBeSelected();
  expect(
    screen.getByRole("button", { name: "New Air" }),
  ).not.toBeSelected();
  expect(
    screen.getByRole("progressbar", { name: "Playback progress" }),
  ).toHaveAccessibilityValue({
    min: 0,
    max: 100,
    now: 25,
    text: "0:30 of 2:00",
  });

  await user.press(screen.getByRole("button", { name: "New Air" }));
  await user.press(
    screen.getByRole("button", { name: "Change TikLocal Server" }),
  );

  expect(radio.selectStation).toHaveBeenCalledWith("recent");
  expect(onConnectionPress).toHaveBeenCalledTimes(1);
});

test("routes every paused-state control to the Radio session", async () => {
  const radio = session();
  const user = userEvent.setup();
  await render(
    <RadioScreen radio={radio} onConnectionPress={jest.fn()} />,
  );

  await user.press(screen.getByRole("button", { name: "Play radio" }));
  await user.press(screen.getByRole("button", { name: "Next track" }));
  await user.press(screen.getByRole("button", { name: "KEEP" }));
  await user.press(screen.getByRole("button", { name: "ENCORE" }));
  await user.press(screen.getByRole("button", { name: "SLEEP" }));

  expect(radio.play).toHaveBeenCalledTimes(1);
  expect(radio.next).toHaveBeenCalledTimes(1);
  expect(radio.toggleFavorite).toHaveBeenCalledTimes(1);
  expect(radio.encore).toHaveBeenCalledTimes(1);
  expect(radio.setSleepTimer).toHaveBeenCalledWith(30);
});

test("announces active controls and routes pause", async () => {
  const radio = session({
    playback: { kind: "playing" },
    isFavorite: true,
    encoreCount: 2,
    sleepMinutes: 60,
  });
  const user = userEvent.setup();
  await render(
    <RadioScreen radio={radio} onConnectionPress={jest.fn()} />,
  );

  expect(screen.getByRole("button", { name: "KEPT" })).toBeSelected();
  expect(
    screen.getByRole("button", { name: "ENCORE ×2" }),
  ).toBeSelected();
  expect(
    screen.getByRole("button", { name: "SLEEP 60" }),
  ).toBeSelected();
  await user.press(screen.getByRole("button", { name: "Pause radio" }));

  expect(radio.pause).toHaveBeenCalledTimes(1);
});

test("announces an empty library and disables every playback action", async () => {
  const radio = session({
    sync: {
      kind: "empty",
      serverName: "Studio",
      message: "No playable audio was found.",
    },
  });
  await render(
    <RadioScreen radio={radio} onConnectionPress={jest.fn()} />,
  );

  expect(screen.getByText("NO AUDIO")).toBeOnTheScreen();
  expect(
    screen.getByRole("alert", { name: "No playable audio was found." }),
  ).toBeOnTheScreen();
  for (const name of [
    "Play radio",
    "Next track",
    "KEEP",
    "ENCORE",
    "SLEEP",
  ]) {
    expect(screen.getByRole("button", { name })).toBeDisabled();
  }
  expect(
    screen.getByRole("button", { name: "Change TikLocal Server" }),
  ).toBeEnabled();
});
