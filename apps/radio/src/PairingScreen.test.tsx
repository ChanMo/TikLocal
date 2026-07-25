import { expect, jest, test } from "@jest/globals";
import {
  act,
  render,
  screen,
  userEvent,
  waitFor,
} from "@testing-library/react-native";

import { TikLocalApiError } from "./api";
import { PairingScreen } from "./PairingScreen";

jest.mock("expo-camera", () => ({
  CameraView: () => null,
  useCameraPermissions: () => [
    { granted: false, canAskAgain: true },
    jest.fn(),
  ],
}));

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

function props() {
  return {
    onConnect: jest.fn<
      (input: { baseUrl: string; password: string }) => Promise<void>
    >().mockResolvedValue(),
    onClaim: jest.fn<
      (input: { pairingUri: string }) => Promise<void>
    >().mockResolvedValue(),
    onUseDemo: jest.fn(),
  };
}

test("starts with focused connection choices and explains a remembered Server", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(
    <PairingScreen
      {...callbacks}
      initialServerName="Studio"
      initialUrl="https://studio.local:8443"
    />,
  );

  expect(screen.getByText("Reconnect to Studio.")).toBeOnTheScreen();
  expect(screen.getByText("https://studio.local:8443")).toBeOnTheScreen();
  expect(screen.queryByLabelText("Server address")).not.toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Enter Manually" }));

  expect(screen.getByLabelText("Server address")).toHaveDisplayValue(
    "https://studio.local:8443",
  );
  expect(screen.getByLabelText("Access password")).toHaveDisplayValue("");
});

test("keeps Demo as a secondary non-destructive choice", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  await user.press(
    screen.getByRole("button", { name: "Continue with Demo Radio" }),
  );

  expect(callbacks.onUseDemo).toHaveBeenCalledTimes(1);
});

test("submits a pairing link from its own progressive step", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  await user.press(screen.getByRole("button", { name: "Paste Pairing Link" }));
  const pairingUri = `tiklocal-radio://pair?server=studio.local&grant=tlpg_${"a".repeat(43)}&v=1`;
  await user.paste(screen.getByLabelText("Pairing link"), pairingUri);
  await user.press(screen.getByRole("button", { name: "Use pairing link" }));

  expect(callbacks.onClaim).toHaveBeenCalledWith({ pairingUri });
  expect(callbacks.onConnect).not.toHaveBeenCalled();
});

test("shows and updates a deep-linked Server before explicit confirmation", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  const firstPairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
    "https://first.local:8443",
  )}&grant=tlpg_${"a".repeat(43)}&v=1`;
  const nextPairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
    "http://next.local:8765",
  )}&grant=tlpg_${"b".repeat(43)}&v=1`;
  const view = await render(
    <PairingScreen
      {...callbacks}
      initialPairingUri={firstPairingUri}
    />,
  );

  expect(screen.getByText("https://first.local:8443")).toBeOnTheScreen();
  expect(callbacks.onClaim).not.toHaveBeenCalled();

  await view.rerender(
    <PairingScreen
      {...callbacks}
      initialPairingUri={nextPairingUri}
    />,
  );
  expect(screen.getByText("http://next.local:8765")).toBeOnTheScreen();

  await user.press(
    screen.getByRole("button", { name: "Confirm Server connection" }),
  );
  expect(callbacks.onClaim).toHaveBeenCalledWith({
    pairingUri: nextPairingUri,
  });
});

test("opens and closes the QR scanner from the primary action", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  await user.press(
    screen.getByRole("button", { name: "Scan pairing QR code" }),
  );
  expect(await screen.findByText("Scan without typing.")).toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Close scanner" }));
  expect(screen.queryByText("Scan without typing.")).not.toBeOnTheScreen();
});

test("submits credentials once and keeps the remembered address on error", async () => {
  const connection = deferred();
  const callbacks = props();
  callbacks.onConnect.mockReturnValueOnce(connection.promise);
  const user = userEvent.setup();
  await render(
    <PairingScreen
      {...callbacks}
      initialUrl="https://studio.local"
    />,
  );
  await user.press(screen.getByRole("button", { name: "Enter Manually" }));
  await user.paste(
    screen.getByLabelText("Access password"),
    "access-password",
  );
  const connect = screen.getByRole("button", {
    name: "Connect to TikLocal Server",
  });

  await user.press(connect);
  expect(connect).toBeDisabled();
  await user.press(connect);
  expect(callbacks.onConnect).toHaveBeenCalledTimes(1);
  expect(callbacks.onConnect).toHaveBeenCalledWith({
    baseUrl: "https://studio.local",
    password: "access-password",
  });

  await act(async () => {
    connection.resolve();
    await connection.promise;
  });
  await waitFor(() => expect(connect).toBeEnabled());
});

test("shows a structured error without losing the entered address", async () => {
  const callbacks = props();
  callbacks.onConnect.mockRejectedValue(
    new TikLocalApiError(
      "The access password is incorrect",
      "invalid_password",
      401,
    ),
  );
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);
  await user.press(screen.getByRole("button", { name: "Enter Manually" }));
  await user.paste(
    screen.getByLabelText("Server address"),
    "https://studio.local",
  );
  await user.press(
    screen.getByRole("button", { name: "Connect to TikLocal Server" }),
  );

  expect(
    await screen.findByRole("alert", {
      name: "The access password is incorrect",
    }),
  ).toBeOnTheScreen();
  expect(screen.getByLabelText("Server address")).toHaveDisplayValue(
    "https://studio.local",
  );
});
