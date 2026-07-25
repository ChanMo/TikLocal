import { beforeEach, expect, jest, test } from "@jest/globals";
import { Alert } from "react-native";
import {
  render,
  screen,
  userEvent,
} from "@testing-library/react-native";

import { ConnectionScreen } from "./ConnectionScreen";
import type { StoredConnection, SyncState } from "./model";

const paired: StoredConnection = {
  kind: "paired",
  profile: {
    baseUrl: "http://studio.local:8888",
    serverName: "Studio",
    deviceId: "device-1",
    token: "secret-token",
  },
};

function props(
  connection: StoredConnection | null = paired,
  sync: SyncState = { kind: "ready", serverName: "Studio" },
) {
  return {
    connection,
    sync,
    onChangeServer: jest.fn(),
    onDisconnect: jest.fn(),
    onReconnect: jest.fn(),
    onRetry: jest.fn(),
  };
}

beforeEach(() => {
  jest.restoreAllMocks();
});

test("shows the remembered Server and keeps replacement explicit", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(<ConnectionScreen {...callbacks} />);

  expect(screen.getByText("CONNECTED")).toBeOnTheScreen();
  expect(screen.getByText("Studio")).toBeOnTheScreen();
  expect(screen.getByText("http://studio.local:8888")).toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Change Server" }));

  expect(callbacks.onRetry).not.toHaveBeenCalled();
  expect(callbacks.onChangeServer).toHaveBeenCalledTimes(1);
});

test("explains that an offline connection remains saved and offers Retry", async () => {
  const callbacks = props(paired, {
    kind: "offline",
    message: "TikLocal Server is unavailable.",
  });
  const user = userEvent.setup();
  await render(<ConnectionScreen {...callbacks} />);

  expect(screen.getByText("OFFLINE · CONNECTION SAVED")).toBeOnTheScreen();
  expect(
    screen.getByText(/Your connection is still saved/),
  ).toBeOnTheScreen();

  await user.press(
    screen.getByRole("button", { name: "Retry Server connection" }),
  );
  expect(callbacks.onRetry).toHaveBeenCalledTimes(1);
});

test("offers focused reauthorization for a known Server", async () => {
  const known: StoredConnection = {
    kind: "known",
    server: {
      baseUrl: "http://studio.local:8888",
      serverName: "Studio",
    },
  };
  const callbacks = props(known, { kind: "demo" });
  const user = userEvent.setup();
  await render(<ConnectionScreen {...callbacks} />);

  expect(screen.getByText("AUTHORIZATION REQUIRED")).toBeOnTheScreen();
  await user.press(
    screen.getByRole("button", { name: "Reconnect to Studio" }),
  );
  expect(callbacks.onReconnect).toHaveBeenCalledTimes(1);
});

test("requires destructive confirmation before forgetting a Server", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  let confirm: (() => void) | undefined;
  jest.spyOn(Alert, "alert").mockImplementation((_title, _message, buttons) => {
    confirm = buttons?.find((button) => button.style === "destructive")
      ?.onPress;
  });
  await render(<ConnectionScreen {...callbacks} />);

  await user.press(
    screen.getByRole("button", { name: "Forget this Server" }),
  );
  expect(callbacks.onDisconnect).not.toHaveBeenCalled();

  confirm?.();
  expect(callbacks.onDisconnect).toHaveBeenCalledTimes(1);
});
