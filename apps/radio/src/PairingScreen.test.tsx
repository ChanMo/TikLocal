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
    onCancel: jest.fn(),
    onUseDemo: jest.fn(),
  };
}

test("exposes the stored address and explicit return and Demo actions", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(
    <PairingScreen
      {...callbacks}
      initialUrl="https://studio.local:8443"
    />,
  );

  expect(screen.getByLabelText("Server address")).toHaveDisplayValue(
    "https://studio.local:8443",
  );
  expect(screen.getByLabelText("Access password")).toHaveDisplayValue("");

  await user.press(screen.getByRole("button", { name: "Return to radio" }));
  await user.press(
    screen.getByRole("button", { name: "Disconnect and use Demo" }),
  );

  expect(callbacks.onCancel).toHaveBeenCalledTimes(1);
  expect(callbacks.onUseDemo).toHaveBeenCalledTimes(1);
});

test("submits a pasted pairing link without manual credentials", async () => {
  const callbacks = props();
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  const pairingUri = `tiklocal-radio://pair?server=studio.local&grant=tlpg_${"a".repeat(43)}&v=1`;
  await user.paste(screen.getByLabelText("Pairing link"), pairingUri);
  await user.press(screen.getByRole("button", { name: "Use pairing link" }));

  expect(callbacks.onClaim).toHaveBeenCalledWith({ pairingUri });
  expect(callbacks.onConnect).not.toHaveBeenCalled();
});

test("shows and updates the target of a deep-linked pairing request", async () => {
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

  expect(screen.getByLabelText("Pairing link")).toHaveDisplayValue(
    firstPairingUri,
  );
  expect(
    screen.getByText("TARGET SERVER · https://first.local:8443"),
  ).toBeOnTheScreen();
  expect(callbacks.onClaim).not.toHaveBeenCalled();

  await view.rerender(
    <PairingScreen
      {...callbacks}
      initialPairingUri={nextPairingUri}
    />,
  );
  expect(screen.getByLabelText("Pairing link")).toHaveDisplayValue(
    nextPairingUri,
  );
  expect(
    screen.getByText("TARGET SERVER · http://next.local:8765"),
  ).toBeOnTheScreen();

  await user.press(screen.getByRole("button", { name: "Use pairing link" }));
  expect(callbacks.onClaim).toHaveBeenCalledWith({
    pairingUri: nextPairingUri,
  });
});

test("opens and closes the QR scanner from an explicit action", async () => {
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

test("disables both pairing actions while a link is being claimed", async () => {
  const connection = deferred();
  const callbacks = props();
  callbacks.onClaim.mockReturnValue(connection.promise);
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  const claim = screen.getByRole("button", { name: "Use pairing link" });
  const manual = screen.getByRole("button", {
    name: "Open private frequency",
  });
  await user.press(claim);

  expect(claim).toBeDisabled();
  expect(manual).toBeDisabled();
  await user.press(claim);
  expect(callbacks.onClaim).toHaveBeenCalledTimes(1);

  await act(async () => {
    connection.resolve();
    await connection.promise;
  });
  await waitFor(() => {
    expect(claim).toBeEnabled();
    expect(manual).toBeEnabled();
  });
});

test("submits typed credentials once and disables the action while pending", async () => {
  const connection = deferred();
  const callbacks = props();
  callbacks.onConnect.mockReturnValue(connection.promise);
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  await user.paste(
    screen.getByLabelText("Server address"),
    "studio.local:8443",
  );
  await user.paste(
    screen.getByLabelText("Access password"),
    "access-password",
  );
  const connect = screen.getByRole("button", {
    name: "Open private frequency",
  });

  await user.press(connect);

  expect(callbacks.onConnect).toHaveBeenCalledWith({
    baseUrl: "studio.local:8443",
    password: "access-password",
  });
  expect(connect).toBeDisabled();
  await user.press(connect);
  expect(callbacks.onConnect).toHaveBeenCalledTimes(1);

  await act(async () => {
    connection.resolve();
    await connection.promise;
  });
  await waitFor(() => {
    expect(connect).toBeEnabled();
  });
});

test("shows a structured TikLocal error without losing the entered address", async () => {
  const callbacks = props();
  callbacks.onConnect.mockRejectedValue(
    new TikLocalApiError("The access password is incorrect", "invalid_password", 401),
  );
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);
  await user.paste(
    screen.getByLabelText("Server address"),
    "https://studio.local",
  );

  await user.press(
    screen.getByRole("button", { name: "Open private frequency" }),
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

test("uses a stable message for an unexpected connection failure", async () => {
  const callbacks = props();
  callbacks.onConnect.mockRejectedValue(new Error("keychain failure"));
  const user = userEvent.setup();
  await render(<PairingScreen {...callbacks} />);

  await user.press(
    screen.getByRole("button", { name: "Open private frequency" }),
  );

  expect(
    await screen.findByRole("alert", {
      name: "The private frequency could not be opened.",
    }),
  ).toBeOnTheScreen();
});
