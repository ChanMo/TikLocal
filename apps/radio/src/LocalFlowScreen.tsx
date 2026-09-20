import { SymbolView } from "expo-symbols";
import { useVideoPlayer, VideoView } from "expo-video";
import { useEffect, useRef, useState } from "react";
import {
  FlatList,
  Image,
  type LayoutChangeEvent,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type ViewToken,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { LocalMediaItem } from "./localLibrary";
import { colors } from "./theme";

type LocalFlowScreenProps = {
  initialIndex: number;
  items: LocalMediaItem[];
  onClose?(): void;
  onShuffle?(): void;
};

export function LocalFlowScreen({
  initialIndex,
  items,
  onClose,
  onShuffle,
}: LocalFlowScreenProps) {
  const { height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const [viewportHeight, setViewportHeight] = useState(height);
  const itemHeight = viewportHeight || height;
  const viewabilityConfig = useRef({ itemVisiblePercentThreshold: 80 });
  const onViewableItemsChanged = useRef(
    ({ viewableItems }: { viewableItems: ViewToken<LocalMediaItem>[] }) => {
      const index = viewableItems[0]?.index;
      if (typeof index === "number") {
        setActiveIndex(index);
      }
    },
  );

  return (
    <View
      onLayout={(event: LayoutChangeEvent) => {
        const nextHeight = Math.round(event.nativeEvent.layout.height);
        if (nextHeight > 0 && nextHeight !== viewportHeight) {
          setViewportHeight(nextHeight);
        }
      }}
      style={styles.screen}
    >
      <FlatList
        data={items}
        decelerationRate="fast"
        getItemLayout={(_data, index) => ({
          index,
          length: itemHeight,
          offset: itemHeight * index,
        })}
        initialScrollIndex={initialIndex}
        key={`flow:${itemHeight}:${items.length}`}
        keyExtractor={(item) => item.id}
        onViewableItemsChanged={onViewableItemsChanged.current}
        pagingEnabled
        renderItem={({ item, index }) => (
          <FlowItem
            active={index === activeIndex}
            height={itemHeight}
            item={item}
          />
        )}
        showsVerticalScrollIndicator={false}
        viewabilityConfig={viewabilityConfig.current}
        windowSize={3}
      />

      <View style={[styles.topBar, { paddingTop: insets.top + 6 }]}>
        {onClose ? (
          <Pressable
            accessibilityLabel="Close local Flow"
            accessibilityRole="button"
            onPress={onClose}
            style={({ pressed }) => [styles.close, pressed && styles.pressed]}
          >
            <SymbolView
              name="xmark"
              size={16}
              tintColor={colors.white}
              weight="bold"
            />
          </Pressable>
        ) : (
          <View style={styles.brandLockup}>
            <View style={styles.brandSignal} />
            <Text style={styles.brand}>LUMAFOLD</Text>
          </View>
        )}
        {onShuffle ? (
          <Pressable
            accessibilityLabel="Shuffle Flow"
            accessibilityRole="button"
            onPress={onShuffle}
            style={({ pressed }) => [styles.close, pressed && styles.pressed]}
          >
            <SymbolView
              name="shuffle"
              size={17}
              tintColor={colors.white}
              weight="semibold"
            />
          </Pressable>
        ) : (
          <Text style={styles.counter}>{activeIndex + 1} / {items.length}</Text>
        )}
      </View>
    </View>
  );
}

function FlowItem({
  active,
  height,
  item,
}: {
  active: boolean;
  height: number;
  item: LocalMediaItem;
}) {
  return (
    <View style={[styles.item, { height }]}>
      {item.kind === "image" ? (
        <Image source={{ uri: item.uri }} style={styles.media} />
      ) : (
        <LocalVideo active={active} uri={item.uri} />
      )}
      <View pointerEvents="none" style={styles.scrim} />
      <View pointerEvents="none" style={styles.caption}>
        <Text style={styles.source}>A MEMORY ON THIS IPHONE</Text>
      </View>
    </View>
  );
}

function LocalVideo({ active, uri }: { active: boolean; uri: string }) {
  const [paused, setPaused] = useState(false);
  const player = useVideoPlayer(uri, (createdPlayer) => {
    createdPlayer.loop = true;
    createdPlayer.muted = false;
  });

  useEffect(() => {
    if (active && !paused) {
      player.play();
    } else {
      player.pause();
    }
    return () => player.pause();
  }, [active, paused, player]);

  return (
    <Pressable
      accessibilityLabel={paused ? "Play video" : "Pause video"}
      accessibilityRole="button"
      disabled={!active}
      onPress={() => setPaused((value) => !value)}
      style={styles.media}
    >
      <VideoView
        contentFit="contain"
        nativeControls={false}
        player={player}
        style={styles.media}
      />
      {paused && active ? (
        <View pointerEvents="none" style={styles.pausedMark}>
          <SymbolView
            name="play.fill"
            size={26}
            tintColor={colors.white}
            weight="bold"
          />
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#050806",
  },
  item: {
    width: "100%",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#050806",
  },
  media: {
    width: "100%",
    height: "100%",
    resizeMode: "contain",
  },
  scrim: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: "transparent",
    borderBottomColor: "rgba(0,0,0,0.35)",
    borderBottomWidth: 150,
  },
  topBar: {
    position: "absolute",
    top: 0,
    right: 0,
    left: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
  },
  close: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 21,
    backgroundColor: "rgba(5, 8, 6, 0.7)",
  },
  brandLockup: {
    minHeight: 42,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    paddingHorizontal: 3,
  },
  brandSignal: {
    width: 5,
    height: 18,
    borderRadius: 3,
    backgroundColor: colors.signal,
  },
  brand: {
    color: colors.white,
    fontSize: 11,
    fontWeight: "900",
    letterSpacing: 2.2,
  },
  counter: {
    overflow: "hidden",
    paddingHorizontal: 12,
    paddingVertical: 8,
    color: colors.white,
    fontSize: 11,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
    borderRadius: 16,
    backgroundColor: "rgba(5, 8, 6, 0.7)",
  },
  caption: {
    position: "absolute",
    right: 24,
    bottom: 34,
    left: 24,
  },
  pausedMark: {
    position: "absolute",
    top: "50%",
    left: "50%",
    width: 64,
    height: 64,
    alignItems: "center",
    justifyContent: "center",
    marginTop: -32,
    marginLeft: -32,
    paddingLeft: 4,
    borderRadius: 32,
    backgroundColor: "rgba(5, 8, 6, 0.72)",
  },
  source: {
    marginTop: 7,
    color: "rgba(255,253,248,0.68)",
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 1.4,
  },
  pressed: {
    opacity: 0.55,
  },
});
