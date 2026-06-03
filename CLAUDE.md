# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Cthulhu-mythos AI-driven text adventure game (克苏鲁跑团) — single-page vanilla JS app with no build step. Open `index.html` directly in a browser to play.

## Architecture

Four JS files loaded in order via `<script>` tags in `index.html`. Each file attaches a single global object to `window`:

| File | Global | Responsibility |
|------|--------|---------------|
| `config.js` | `CONFIG` | API keys, model names, initial stat values, image style prompts |
| `api.js` | `API` | Calls SiliconFlow LLM and image generation endpoints, parses JSON responses |
| `game.js` | `Game` | State machine — holds `state` (sanity, health, history, turn), builds system prompt, orchestrates LLM + image calls, applies stat deltas |
| `ui.js` | `UI` | All DOM manipulation — typewriter narration, dialogue fade-in, option buttons, stat bars, background image crossfade, loading overlay |

`index.html` contains all CSS inline in `<style>` and calls `UI.init()` + `Game.start()` on `DOMContentLoaded`.

## Game loop

1. Player types action or clicks an option button → `UI.handleInput()` → `Game.playerAction(text)`
2. `Game.processAndRender()` builds a system prompt from current state + full conversation history, calls `API.callLLM()`
3. LLM returns structured JSON with `narration`, `dialogue[]`, `scene_prompt`, `sanity_delta`, `health_delta`, `options[]`, `game_over`
4. Stats are clamped to [0, 100]; image is generated in parallel using the returned `scene_prompt`
5. If `game_over` is true or stats hit 0, `UI.renderGameOver()` is called

## API

Both LLM and image endpoints go to `api.siliconflow.cn`. The API key is in `config.js` (`CONFIG.SILICONFLOW_API_KEY`). LLM model: `deepseek-ai/DeepSeek-V4-Flash`, image model: `Kwai-Kolors/Kolors`. The LLM response is expected to be raw JSON (the code strips ``` fences and `<think>` blocks before parsing).

## No build / no tests

This is a zero-dependency vanilla JS project. There is no bundler, package manager, linter, or test framework. To run it, serve the directory with any static file server or open `index.html` directly.
