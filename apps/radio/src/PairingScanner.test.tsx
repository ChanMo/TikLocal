import { beforeEach, expect, jest, test } from "@jest/globals";
import {
  act,
  render,
  screen,
  userEvent,
} from "@testing-library/react-native";

import { PairingScanner } from "./PairingScanner";

let mockPermission: {
  granted: boolean;
  canAskAgain: boolean;
} | null;
const mockRequestPermission = jest.fn<() => Promise<unknown>>();
let mockCameraProps: {
  barcodeScannerSettings: { barcodeTypes: string[] };
  onBarcodeScanned?: (event: { data: string; type: string }) => void;
} | null;

jest.mock("expo-camera", () => ({
  CameraView: (props: typeof mockCameraProps) => {
    mockCameraProps = props;
    return null;
  },
  useCameraPermissions: () => [mockPermission, mockRequestPermission],
}));

function callbacks() {
  return {
    onCancel: jest.fn(),
    onConfirm: jest.fn<(pairingUri: string) => void>(),
  };
}

beforeEach(() => {
  mockPermission = { granted: false, canAskAgain: true };
  mockRequestPermission.mockResolvedValue({});
  mockCameraProps = null;
});

test("requests camera access only from an explicit action", async () => {
  const props = callbacks();
  const user = userEvent.setup();
  await render(<PairingScanner {...props} />);

  expect(mockRequestPermission).not.toHaveBeenCalled();
  await user.press(
    screen.getByRole("button", { name: "Allow camera access" }),
  );
  await user.press(screen.getByRole("button", { name: "Close scanner" }));

  expect(mockRequestPermission).toHaveBeenCalledTimes(1);
  expect(props.onCancel).toHaveBeenCalledTimes(1);
});

test("explains how to recover when camera permission is blocked", async () => {
  mockPermission = { granted: false, canAskAgain: false };
  await render(<PairingScanner {...callbacks()} />);

  expect(
    screen.getByRole("alert", {
      name: /Camera access is disabled/,
    }),
  ).toBeOnTheScreen();
  expect(
    screen.queryByRole("button", { name: "Allow camera access" }),
  ).not.toBeOnTheScreen();
});

test("scans only QR codes and confirms the Server before connecting", async () => {
  mockPermission = { granted: true, canAskAgain: true };
  const props = callbacks();
  const user = userEvent.setup();
  await render(<PairingScanner {...props} />);
  const pairingUri = `tiklocal-radio://pair?server=${encodeURIComponent(
    "https://studio.local:8443",
  )}&grant=tlpg_${"a".repeat(43)}&v=1`;

  expect(mockCameraProps?.barcodeScannerSettings).toEqual({
    barcodeTypes: ["qr"],
  });
  await act(async () => {
    mockCameraProps?.onBarcodeScanned?.({
      data: pairingUri,
      type: "qr",
    });
  });

  expect(await screen.findByText("https://studio.local:8443")).toBeOnTheScreen();
  expect(props.onConfirm).not.toHaveBeenCalled();
  await user.press(
    screen.getByRole("button", {
      name: "Connect to https://studio.local:8443",
    }),
  );
  expect(props.onConfirm).toHaveBeenCalledWith(pairingUri);
});

test("pauses on an unrelated QR code and allows scanning again", async () => {
  mockPermission = { granted: true, canAskAgain: true };
  const user = userEvent.setup();
  await render(<PairingScanner {...callbacks()} />);

  await act(async () => {
    mockCameraProps?.onBarcodeScanned?.({
      data: "https://unrelated.example",
      type: "qr",
    });
  });

  expect(
    await screen.findByRole("alert", {
      name: "This QR code is not a TikLocal Radio pairing link.",
    }),
  ).toBeOnTheScreen();
  await user.press(
    screen.getByRole("button", { name: "Scan another code" }),
  );
  expect(
    screen.queryByText("This QR code is not a TikLocal Radio pairing link."),
  ).not.toBeOnTheScreen();
});
