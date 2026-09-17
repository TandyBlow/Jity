"use client";

import { useEffect, useState } from "react";

import { generateBackground } from "@/lib/api";
import type { GameState, StoryOutput } from "@/types";

export function useSceneBackground(output: StoryOutput, state: GameState | null) {
  const [backgroundUrl, setBackgroundUrl] = useState("");
  const [isBackgroundLoading, setIsBackgroundLoading] = useState(false);
  const [backgroundError, setBackgroundError] = useState("");
  const [backgroundRequestNonce, setBackgroundRequestNonce] = useState(0);
  const sceneLocation = state?.current_location || output.current_location;
  const scenePrompt = output.scene_prompt?.trim() ?? "";

  useEffect(() => {
    setBackgroundUrl("");
    setBackgroundError("");
    if (!scenePrompt) {
      setIsBackgroundLoading(false);
      return;
    }

    let cancelled = false;
    setIsBackgroundLoading(true);
    setBackgroundError("");
    generateBackground({ scenePrompt, location: sceneLocation })
      .then(({ image_url: imageUrl }) => {
        const image = new window.Image();
        image.onload = () => {
          if (!cancelled) {
            setBackgroundUrl(imageUrl);
            setIsBackgroundLoading(false);
          }
        };
        image.onerror = () => {
          if (!cancelled) {
            setBackgroundError("背景图片加载失败");
            setIsBackgroundLoading(false);
          }
        };
        image.src = imageUrl;
      })
      .catch((err) => {
        console.info("Background generation unavailable:", err);
        if (!cancelled) {
          setBackgroundError(err instanceof Error ? err.message : "场景背景生成失败");
          setIsBackgroundLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [sceneLocation, scenePrompt, backgroundRequestNonce]);

  return {
    backgroundUrl,
    isBackgroundLoading,
    backgroundError,
    retryBackground: () => setBackgroundRequestNonce((value) => value + 1),
  };
}
