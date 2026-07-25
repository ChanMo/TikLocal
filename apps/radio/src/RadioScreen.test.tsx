import { beforeEach, expect, jest, test } from "@jest/globals";
import { ActionSheetIOS } from "react-native";
import {
  render,
  screen,
  userEvent,
  waitFor,
} from "@testing-library/react-native";

import type { RadioSnapshot, Station, Track } from "./model";
import type { RadioSession } from "./radio";
import { RadioScreen } from "./RadioScreen";

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

const actionSheetChoices: number[] = [];

jest
  .spyOn(ActionSheetIOS, "showActionSheetWithOptions")
  .mockImplementation((options, callback) =>
    callback(actionSheetChoices.shift() ?? options.cancelButtonIndex ?? 0),
  );

beforeEach(() => {
  actionSheetChoices.length = 0;
});

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
    retry: jest.fn(),
    selectStation: jest.fn(),
    toggleFavorite: jest.fn(),
    encore: jest.fn(),
    setSleepTimer: jest.fn(),
  };
}

test("exposes station selection and playback progress", async () => {
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
  expect(screen.queryByText("Studio")).not.toBeOnTheScreen();
  const stationSelector = screen.getByRole("button", {
    name: "Choose station, Daily Signal",
  });
  expect(
    screen.getByRole("progressbar", { name: "Playback progress" }),
  ).toHaveAccessibilityValue({
    min: 0,
    max: 100,
    now: 25,
    text: "0:30 of 2:00",
  });

  actionSheetChoices.push(1);
  await user.press(stationSelector);
  expect(radio.selectStation).toHaveBeenCalledWith("recent");
  expect(onConnectionPress).not.toHaveBeenCalled();
});

test("routes every paused-state control to the Radio session", async () => {
  const radio = session();
  const user = userEvent.setup();
  await render(
    <RadioScreen radio={radio} onConnectionPress={jest.fn()} />,
  );

  await user.press(screen.getByRole("button", { name: "Play radio" }));
  await user.press(screen.getByRole("button", { name: "Next track" }));
  await user.press(
    screen.getByRole("button", { name: "Add to Favorites" }),
  );
  actionSheetChoices.push(0);
  await user.press(screen.getByRole("button", { name: "More Radio options" }));
  actionSheetChoices.push(1, 1);
  await user.press(screen.getByRole("button", { name: "More Radio options" }));

  expect(radio.play).toHaveBeenCalledTimes(1);
  expect(radio.next).toHaveBeenCalledTimes(1);
  expect(radio.toggleFavorite).toHaveBeenCalledTimes(1);
  expect(radio.encore).toHaveBeenCalledTimes(1);
  await waitFor(() =>
    expect(radio.setSleepTimer).toHaveBeenCalledWith(30),
  );
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

  expect(
    screen.getByRole("button", { name: "Remove from Favorites" }),
  ).toBeSelected();
  expect(screen.getByText("Queued ×2")).toBeOnTheScreen();
  expect(screen.getByText("60 min")).toBeOnTheScreen();
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

  expect(screen.getByText("Your library is quiet")).toBeOnTheScreen();
  expect(screen.getByText("Add playable audio in TikLocal")).toBeOnTheScreen();
  expect(
    screen.getByRole("alert", { name: "Your library is quiet" }),
  ).toBeOnTheScreen();
  for (const name of [
    "Play radio",
    "Next track",
    "Add to Favorites",
    "Choose station, Daily Signal",
  ]) {
    expect(screen.getByRole("button", { name })).toBeDisabled();
  }
  expect(
    screen.getByRole("button", { name: "More Radio options" }),
  ).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Open Server connection settings" }),
  ).toBeEnabled();
});

test("shows an actionable saved-connection message while offline", async () => {
  const radio = session({
    sync: {
      kind: "offline",
      message: "TikLocal Server is unavailable.",
    },
  });
  const onConnectionPress = jest.fn();
  const user = userEvent.setup();
  await render(
    <RadioScreen
      radio={radio}
      onConnectionPress={onConnectionPress}
    />,
  );

  expect(screen.getByText("Signal interrupted")).toBeOnTheScreen();
  expect(screen.getByText("Your connection is saved")).toBeOnTheScreen();
  expect(
    screen.getByText("Connection saved · tap to reconnect"),
  ).toBeOnTheScreen();
  await user.press(
    screen.getByRole("button", {
      name: "Open Server connection settings",
    }),
  );
  expect(onConnectionPress).toHaveBeenCalledTimes(1);
});
