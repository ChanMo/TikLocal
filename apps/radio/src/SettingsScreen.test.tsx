import { expect, jest, test } from "@jest/globals";
import { render, screen, userEvent } from "@testing-library/react-native";

import type { StoredConnection } from "./model";
import { SettingsScreen } from "./SettingsScreen";

jest.mock(
  "react-native-safe-area-context",
  () => require("react-native-safe-area-context/jest/mock").default,
);

test("keeps TikLocal as an optional source beside the local library", async () => {
  const user = userEvent.setup();
  const onOpenTikLocalSource = jest.fn();

  await render(
    <SettingsScreen
      connection={null}
      mediaCount={18}
      onOpenTikLocalSource={onOpenTikLocalSource}
    />,
  );

  expect(screen.getByText("18 memories")).toBeOnTheScreen();
  expect(screen.getByText("Optional · not connected")).toBeOnTheScreen();
  expect(screen.getByText("Private by default")).toBeOnTheScreen();

  await user.press(
    screen.getByRole("button", { name: "Open optional TikLocal source" }),
  );
  expect(onOpenTikLocalSource).toHaveBeenCalledTimes(1);
});

test("shows the friendly name of a paired TikLocal source", async () => {
  const connection: StoredConnection = {
    kind: "paired",
    profile: {
      baseUrl: "https://studio.test",
      deviceId: "phone",
      serverName: "Chen’s Mac",
      token: "secret",
    },
  };

  await render(
    <SettingsScreen
      connection={connection}
      mediaCount={1}
      onOpenTikLocalSource={jest.fn()}
    />,
  );

  expect(screen.getByText("Chen’s Mac")).toBeOnTheScreen();
  expect(screen.getByText("1 memory")).toBeOnTheScreen();
});
