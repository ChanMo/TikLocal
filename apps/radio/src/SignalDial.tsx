import { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { colors, radii } from "./theme";

export function SignalDial({
  accent,
  isPlaying,
  size,
}: {
  accent: string;
  isPlaying: boolean;
  size: number;
}) {
  const rotation = useRef(new Animated.Value(0)).current;
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduceMotion,
    );
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (!isPlaying || reduceMotion) {
      return;
    }
    const animation = Animated.loop(
      Animated.timing(rotation, {
        duration: 20000,
        easing: Easing.linear,
        toValue: 1,
        useNativeDriver: true,
      }),
    );
    animation.start();
    return () => animation.stop();
  }, [isPlaying, reduceMotion, rotation]);

  const recordSize = size * 0.72;
  return (
    <View style={[styles.dial, { width: size, height: size }]}>
      <View
        style={[
          styles.glow,
          {
            width: size * 0.84,
            height: size * 0.84,
            borderRadius: size,
            backgroundColor: accent,
          },
        ]}
      />
      <View style={[styles.arc, styles.outerArc]} />
      <View
        style={[
          styles.arc,
          styles.accentArc,
          { borderTopColor: accent },
        ]}
      />
      {Array.from({ length: 12 }, (_, index) => (
        <View
          key={index}
          style={[
            styles.tickTrack,
            {
              width: size,
              height: size,
              transform: [{ rotate: `${index * 30}deg` }],
            },
          ]}
        >
          <View
            style={[
              styles.tick,
              index % 3 === 0 && styles.majorTick,
              index === 1 && { backgroundColor: accent },
            ]}
          />
        </View>
      ))}
      <View
        style={[
          styles.signalPoint,
          {
            right: size * 0.08,
            top: size * 0.24,
            backgroundColor: accent,
          },
        ]}
      />
      <Animated.View
        style={[
          styles.record,
          {
            width: recordSize,
            height: recordSize,
            borderRadius: recordSize / 2,
            transform: [
              {
                rotate: rotation.interpolate({
                  inputRange: [0, 1],
                  outputRange: ["0deg", "360deg"],
                }),
              },
            ],
          },
        ]}
      >
        <View style={[styles.groove, styles.outerGroove]} />
        <View style={[styles.groove, styles.innerGroove]} />
        <View
          style={[
            styles.label,
            {
              width: recordSize * 0.38,
              height: recordSize * 0.38,
              borderRadius: recordSize,
              backgroundColor: accent,
            },
          ]}
        >
          <Text style={styles.labelMark}>TL</Text>
          <View style={styles.spindle} />
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  dial: {
    alignSelf: "center",
    alignItems: "center",
    justifyContent: "center",
  },
  glow: {
    position: "absolute",
    opacity: 0.08,
  },
  arc: {
    position: "absolute",
    width: "100%",
    height: "100%",
    borderColor: "transparent",
    borderWidth: 1,
    borderRadius: radii.pill,
  },
  outerArc: {
    borderTopColor: colors.line,
    borderLeftColor: colors.line,
    transform: [{ rotate: "24deg" }],
  },
  accentArc: {
    width: "89%",
    height: "89%",
    opacity: 0.48,
    transform: [{ rotate: "-40deg" }],
  },
  tickTrack: {
    position: "absolute",
    alignItems: "center",
  },
  tick: {
    width: 1,
    height: 5,
    borderRadius: 1,
    backgroundColor: colors.line,
  },
  majorTick: {
    height: 9,
    backgroundColor: colors.inkMuted,
  },
  signalPoint: {
    position: "absolute",
    width: 9,
    height: 9,
    borderColor: colors.paper,
    borderWidth: 2,
    borderRadius: 5,
  },
  record: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.ink,
    shadowColor: colors.ink,
    shadowOffset: { width: 0, height: 18 },
    shadowOpacity: 0.23,
    shadowRadius: 28,
    elevation: 9,
  },
  groove: {
    position: "absolute",
    borderColor: "rgba(255,253,248,0.10)",
    borderWidth: 1,
    borderRadius: radii.pill,
  },
  outerGroove: {
    width: "84%",
    height: "84%",
  },
  innerGroove: {
    width: "61%",
    height: "61%",
  },
  label: {
    alignItems: "center",
    justifyContent: "center",
  },
  labelMark: {
    color: colors.white,
    fontFamily: "Georgia",
    fontSize: 25,
    fontWeight: "700",
  },
  spindle: {
    width: 5,
    height: 5,
    marginTop: 6,
    borderRadius: 3,
    backgroundColor: colors.paper,
  },
});
