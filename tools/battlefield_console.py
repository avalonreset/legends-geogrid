#!/usr/bin/env python3
"""Generate a self-contained Radial Strategy-Game Battlefield Console (battlefield-console.html).

Iteration 2 Architecture (Tuned for 1109px Canvas B & Full-Screen 4K Viewports):
- Watermark-free OpenStreetMap tiles with custom dark tactical cartography filter
- 2-Deck Fixed-Height Top Command HUD (zero wrapping, zero overlap at 1109px width)
- Asymmetric viewport-aware fitBounds padding (centers radial rings in the open map stage)
- Leader-line offset Citadel HQ markers (never obscures inner 0.55km / 1.2km rings)
- 11-Column CSS Grid Bottom Faction Dock (all 11 factions fit edge-to-edge without scrolling)
- Full-width Mode 4 Strategic Playbook Overlay
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _sanitize_no_em_dash(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\u2014", " - ").replace("\u2013", "-")
    if isinstance(value, list):
        return [_sanitize_no_em_dash(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_no_em_dash(v) for k, v in value.items()}
    return value


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>__PAGE_TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --bg-obsidian: #05080f;
    --bg-glass: rgba(9, 14, 24, 0.90);
    --bg-glass-heavy: rgba(7, 11, 20, 0.96);
    --border-subtle: rgba(148, 163, 184, 0.20);
    --border-bright: rgba(56, 189, 248, 0.55);
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --text-dim: #64748b;
    --emerald: #10b981;
    --amber: #f59e0b;
    --crimson: #ef4444;
    --cyan: #06b6d4;
    --blue: #3b82f6;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', 'Consolas', 'SFMono-Regular', monospace;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
  }

  html, body {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: var(--bg-obsidian);
    color: var(--text-main);
    font-family: var(--font-sans);
    -webkit-font-smoothing: antialiased;
  }

  /* ============================================================================
     FULL-BLEED MAP CANVAS (100% OF VIEWPORT) + DARK TACTICAL FILTER
     ============================================================================ */
  #map-stage {
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    z-index: 1;
    background: radial-gradient(circle at 50% 50%, #0a1222 0%, #04070d 100%);
  }

  #leaflet-map {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 1;
    background: #060a12;
  }

  /* Watermark-free OpenStreetMap inverted into a high-contrast dark tactical map */
  #map-stage.basemap-dark .leaflet-tile-pane {
    filter: invert(92%) hue-rotate(180deg) brightness(90%) contrast(122%) saturate(80%);
  }

  #map-stage.basemap-street .leaflet-tile-pane {
    filter: contrast(105%) brightness(97%);
  }

  #tactical-canvas {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    z-index: 400;
    pointer-events: none;
  }

  .leaflet-control-attribution {
    background: rgba(5, 8, 15, 0.72) !important;
    color: #64748b !important;
    font-size: 9px !important;
    padding: 1px 6px !important;
  }
  .leaflet-control-attribution a {
    color: #94a3b8 !important;
  }

  .hud-glass {
    background: var(--bg-glass);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--border-subtle);
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    border-radius: 9px;
    pointer-events: auto;
  }

  /* ============================================================================
     2-DECK FIXED-HEIGHT TOP COMMAND BAR (NEVER WRAPS OR OVERLAPS AT 1109PX)
     ============================================================================ */
  #hud-top {
    position: fixed;
    top: 10px;
    left: 12px;
    right: 12px;
    z-index: 600;
    display: flex;
    flex-direction: column;
    gap: 6px;
    pointer-events: none;
  }

  .top-deck-1 {
    height: 44px;
    padding: 0 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .top-deck-2 {
    height: 34px;
    padding: 0 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  /* Commander Identity */
  .cmd-badge {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    flex-shrink: 0;
  }

  .cmd-shield {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.28), rgba(6, 182, 212, 0.22));
    border: 1.5px solid var(--emerald);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-weight: 800;
    font-size: 10px;
    color: #34d399;
    box-shadow: 0 0 10px rgba(16, 185, 129, 0.28);
  }

  .cmd-name {
    font-size: 13px;
    font-weight: 800;
    color: #ffffff;
    white-space: nowrap;
  }

  .cmd-sub {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
    white-space: nowrap;
  }

  .cmd-sub .star {
    color: #fbbf24;
  }

  /* 4 Game Mode Tabs (Compact Single-Line) */
  .mode-tabs {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .mode-tab {
    background: rgba(30, 41, 59, 0.45);
    border: 1px solid rgba(148, 163, 184, 0.16);
    color: var(--text-muted);
    height: 30px;
    padding: 0 8px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10.5px;
    font-weight: 800;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }

  .mode-tab:hover {
    background: rgba(51, 65, 85, 0.75);
    color: #ffffff;
  }

  .mode-tab.active {
    background: linear-gradient(180deg, rgba(14, 116, 144, 0.45), rgba(15, 23, 42, 0.95));
    border-color: #38bdf8;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(56, 189, 248, 0.28);
  }

  .mode-key {
    font-family: var(--font-mono);
    font-size: 9px;
    padding: 1px 4px;
    border-radius: 3px;
    background: rgba(56, 189, 248, 0.18);
    color: #38bdf8;
  }

  /* Camera Scale & Map Controls */
  .scale-bar {
    display: flex;
    align-items: center;
    gap: 3px;
    flex-shrink: 0;
  }

  .scale-btn {
    background: rgba(30, 41, 59, 0.65);
    border: 1px solid rgba(148, 163, 184, 0.18);
    color: #cbd5e1;
    height: 28px;
    padding: 0 6.5px;
    border-radius: 5px;
    font-size: 9.5px;
    font-weight: 700;
    font-family: var(--font-mono);
    cursor: pointer;
    transition: all 0.15s ease;
    white-space: nowrap;
  }

  .scale-btn:hover {
    background: rgba(51, 65, 85, 0.85);
    color: #ffffff;
  }

  .scale-btn.active {
    background: rgba(56, 189, 248, 0.22);
    border-color: #38bdf8;
    color: #38bdf8;
  }

  /* Deck 2: Keyword Switcher + Telemetry Counters */
  .lane-switcher {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .lane-label {
    font-size: 9.5px;
    font-family: var(--font-mono);
    text-transform: uppercase;
    color: var(--text-dim);
    margin-right: 3px;
    letter-spacing: 0.05em;
  }

  .lane-pill {
    background: rgba(30, 41, 59, 0.55);
    border: 1px solid rgba(148, 163, 184, 0.16);
    color: #cbd5e1;
    height: 24px;
    padding: 0 9px;
    border-radius: 5px;
    font-size: 10.5px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }

  .lane-pill:hover {
    background: rgba(51, 65, 85, 0.85);
    color: #ffffff;
  }

  .lane-pill.active {
    background: rgba(16, 185, 129, 0.22);
    border-color: var(--emerald);
    color: #34d399;
  }

  .lane-pill .pct {
    font-family: var(--font-mono);
    font-size: 9.5px;
    opacity: 0.9;
  }

  .telemetry-pills {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .t-pill {
    display: flex;
    align-items: center;
    gap: 5px;
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(148, 163, 184, 0.15);
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 10px;
    font-weight: 600;
    color: #cbd5e1;
    white-space: nowrap;
  }

  .t-pill strong {
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 800;
  }

  /* ============================================================================
     LEFT FLOATING MISSION & 9-RING TRAIL-OFF RADAR CARD (COMPACT, ZERO OVERLAP)
     ============================================================================ */
  #mission-banner {
    position: fixed;
    top: 98px;
    left: 12px;
    z-index: 550;
    width: 284px;
    padding: 11px 12px;
  }

  .mission-eyebrow {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: #38bdf8;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .mission-headline {
    font-size: 11.5px;
    font-weight: 600;
    color: #f1f5f9;
    line-height: 1.38;
    margin-bottom: 9px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-subtle);
  }

  .ring-curve-title {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 5px;
    display: flex;
    justify-content: space-between;
  }

  .ring-bars {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .ring-row {
    display: grid;
    grid-template-columns: 48px 1fr 34px 76px;
    align-items: center;
    gap: 5px;
    font-size: 9.5px;
    padding: 2.5px 4px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.12s;
  }

  .ring-row:hover, .ring-row.active {
    background: rgba(56, 189, 248, 0.16);
  }

  .ring-dist {
    font-family: var(--font-mono);
    font-weight: 700;
    color: #e2e8f0;
  }

  .ring-track {
    height: 6px;
    background: rgba(30, 41, 59, 0.9);
    border-radius: 3px;
    overflow: hidden;
  }

  .ring-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
  }

  .ring-pct {
    font-family: var(--font-mono);
    font-weight: 800;
    text-align: right;
  }

  .ring-leader {
    font-size: 9px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* ============================================================================
     CENTER-BOTTOM ACTION BUTTON (LIFT FOG OF WAR)
     ============================================================================ */
  #center-action-Wrap {
    position: fixed;
    bottom: 84px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 580;
    display: flex;
    align-items: center;
    pointer-events: none;
  }

  .fog-cta-btn {
    pointer-events: auto;
    background: linear-gradient(135deg, #f59e0b 0%, #ea580c 100%);
    color: #05080f;
    border: 2px solid #fde68a;
    border-radius: 999px;
    padding: 9px 20px;
    font-size: 11.5px;
    font-weight: 900;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    cursor: pointer;
    box-shadow: 0 8px 26px rgba(245, 158, 11, 0.5), 0 0 0 4px rgba(245, 158, 11, 0.16);
    transition: all 0.18s ease;
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
  }

  .fog-cta-btn:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 0 12px 32px rgba(245, 158, 11, 0.68);
  }

  .fog-cta-btn.lifted {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    border-color: #a7f3d0;
    color: #04130d;
    box-shadow: 0 8px 26px rgba(16, 185, 129, 0.45);
  }

  /* ============================================================================
     RIGHT FLOATING TACTICAL INSPECTOR CARD
     ============================================================================ */
  #inspector-card {
    position: fixed;
    top: 98px;
    right: 12px;
    bottom: 82px;
    width: 316px;
    z-index: 550;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .insp-header {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-subtle);
    background: rgba(15, 23, 42, 0.65);
  }

  .insp-badge-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    margin-bottom: 4px;
  }

  .status-pill {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 800;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .insp-title {
    font-size: 13.5px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.2;
  }

  .insp-sub {
    font-size: 10px;
    color: var(--text-muted);
    margin-top: 2px;
    font-family: var(--font-mono);
  }

  .insp-body {
    padding: 10px 12px;
    overflow-y: auto;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 9px;
  }

  .insp-body::-webkit-scrollbar {
    width: 4px;
  }
  .insp-body::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.25);
    border-radius: 2px;
  }

  .story-box {
    background: rgba(15, 23, 42, 0.76);
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-left: 3px solid var(--amber);
    border-radius: 6px;
    padding: 8px 10px;
  }

  .story-box.emerald {
    border-left-color: var(--emerald);
  }
  .story-box.cyan {
    border-left-color: var(--cyan);
  }

  .story-lbl {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #38bdf8;
    margin-bottom: 3px;
  }

  .story-text {
    font-size: 11px;
    line-height: 1.4;
    color: #e2e8f0;
  }

  .story-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 3.5px;
  }

  .story-list li {
    font-size: 10.5px;
    line-height: 1.35;
    color: #cbd5e1;
    padding-left: 10px;
    position: relative;
  }

  .story-list li::before {
    content: ">";
    position: absolute;
    left: 0;
    color: #f59e0b;
    font-family: var(--font-mono);
    font-weight: 800;
  }

  .serp-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .serp-item {
    background: rgba(15, 23, 42, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 5px;
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .serp-item.is-you {
    background: rgba(16, 185, 129, 0.15);
    border-color: rgba(16, 185, 129, 0.5);
  }

  .serp-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 5px;
  }

  .serp-rank-name {
    display: flex;
    align-items: center;
    gap: 5px;
    min-width: 0;
  }

  .serp-rk {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 800;
    padding: 1px 4.5px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.1);
    color: #ffffff;
    flex-shrink: 0;
  }

  .serp-name {
    font-size: 11px;
    font-weight: 700;
    color: #f8fafc;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .serp-tag {
    font-family: var(--font-mono);
    font-size: 8.5px;
    font-weight: 700;
    padding: 1.5px 4.5px;
    border-radius: 3px;
    flex-shrink: 0;
  }

  .serp-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 9.5px;
    color: var(--text-muted);
    font-family: var(--font-mono);
  }

  /* ============================================================================
     11-COLUMN BOTTOM FACTION COMMAND DOCK (FITS ALL 11 FACTIONS EDGE-TO-EDGE)
     ============================================================================ */
  #faction-dock {
    position: fixed;
    bottom: 10px;
    left: 12px;
    right: 12px;
    height: 64px;
    z-index: 600;
    display: grid;
    grid-template-columns: repeat(11, minmax(0, 1fr));
    gap: 4px;
    padding: 5px 6px;
  }

  .faction-card {
    min-width: 0;
    height: 52px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-top: 3px solid #64748b;
    border-radius: 6px;
    padding: 4px 5px;
    cursor: pointer;
    transition: all 0.14s ease;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }

  .faction-card:hover {
    transform: translateY(-2px);
    background: rgba(30, 41, 59, 0.95);
    border-color: rgba(255, 255, 255, 0.4);
  }

  .faction-card.active {
    background: rgba(30, 41, 59, 0.98);
    box-shadow: 0 0 14px rgba(56, 189, 248, 0.4);
    border-color: #38bdf8;
  }

  .fc-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 2px;
  }

  .fc-code {
    font-family: var(--font-mono);
    font-size: 8.5px;
    font-weight: 800;
    padding: 1px 3.5px;
    border-radius: 3px;
    color: #05080f;
  }

  .fc-solv {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 800;
    color: #ffffff;
  }

  .fc-name {
    font-size: 9.5px;
    font-weight: 700;
    color: #e2e8f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fc-bottom {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: 8px;
    color: var(--text-muted);
  }

  .fc-arch {
    font-size: 7.5px;
    font-weight: 800;
    padding: 0.5px 3px;
    border-radius: 2px;
  }

  /* ============================================================================
     MODE 4 FULL-STAGE STRATEGIC COMMAND MODAL (SPANS FULL WIDTH cleanly)
     ============================================================================ */
  #playbook-modal {
    position: fixed;
    top: 98px;
    left: 12px;
    right: 12px;
    bottom: 82px;
    z-index: 590;
    display: none;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg-glass-heavy);
  }

  #playbook-modal.open {
    display: flex;
  }

  .pb-header {
    padding: 12px 18px;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(15, 23, 42, 0.9);
  }

  .pb-body {
    padding: 14px 18px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .pb-grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }

  .pb-card {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    padding: 12px 14px;
  }

  .pb-card h3 {
    font-size: 11.5px;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #38bdf8;
    margin-bottom: 9px;
  }

  .move-card {
    background: rgba(9, 14, 24, 0.88);
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-left: 4px solid var(--emerald);
    border-radius: 7px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .move-card.amber {
    border-left-color: var(--amber);
  }

  .move-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    font-weight: 800;
    color: #ffffff;
  }

  .move-desc {
    font-size: 11px;
    color: #cbd5e1;
    line-height: 1.42;
  }

  .sector-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
  }
  .sector-table th {
    text-align: left;
    font-family: var(--font-mono);
    font-size: 9.5px;
    color: var(--text-muted);
    padding: 6px 8px;
    border-bottom: 1px solid var(--border-subtle);
  }
  .sector-table td {
    padding: 6px 8px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    font-family: var(--font-mono);
  }
</style>
</head>
<body>

<!-- FULL-BLEED MAP STAGE + HIGH-DPI TACTICAL RADAR CANVAS -->
<div id="map-stage" class="basemap-dark">
  <div id="leaflet-map"></div>
  <canvas id="tactical-canvas"></canvas>
</div>

<!-- 2-DECK FIXED-HEIGHT TOP COMMAND HUD -->
<header id="hud-top">
  <!-- DECK 1: IDENTITY + 4 GAME LENSES + CAMERA ZOOM PRESETS -->
  <div class="hud-glass top-deck-1">
    <div class="cmd-badge" id="cmd-home-btn" title="Click to inspect Your Commander Profile">
      <div class="cmd-shield">YOU</div>
      <div>
        <div class="cmd-name" id="hud-biz-name">Example Mechanical</div>
        <div class="cmd-sub" id="hud-biz-sub">275 Reviews <span class="star">&#9733;</span> 5.0 &bull; 9-Ring Radial (13 km)</div>
      </div>
    </div>

    <nav class="mode-tabs" id="mode-tabs">
      <button class="mode-tab active" data-mode="FOG">
        <span class="mode-key">1</span> FOG OF WAR
      </button>
      <button class="mode-tab" data-mode="TURF">
        <span class="mode-key">2</span> RIVAL EMPIRES
      </button>
      <button class="mode-tab" data-mode="STRIKE">
        <span class="mode-key">3</span> STRIKE TARGETS
      </button>
      <button class="mode-tab" data-mode="PLAYBOOK">
        <span class="mode-key">4</span> TRAIL-OFF &amp; PLAN
      </button>
    </nav>

    <div class="scale-bar">
      <button class="scale-btn" data-scale="CORE" title="Street-Level Core Zoom (0 - 2.5 km)">CORE 2.5KM</button>
      <button class="scale-btn active" data-scale="FRONTIER" title="Battle Frontier Zoom (0 - 5.5 km)">FRONTIER 5.5KM</button>
      <button class="scale-btn" data-scale="METRO" title="Full 9-Ring Metro Horizon (13 km radius)">FULL 13KM</button>
      <button class="scale-btn" id="basemap-btn" title="Switch Dark Tactical / Light Street Map">LIGHT MAP</button>
    </div>
  </div>

  <!-- DECK 2: KEYWORD SWITCHER + LIVE TELEMETRY COUNTERS -->
  <div class="hud-glass top-deck-2">
    <div class="lane-switcher" id="lane-switcher"></div>
    <div class="telemetry-pills">
      <div class="t-pill" title="Pins where you rank #1-#3"><strong style="color:#10b981" id="kpi-stronghold">29</strong> Stronghold</div>
      <div class="t-pill" title="Winnable Paper-Tiger Strike Targets"><strong style="color:#f59e0b" id="kpi-strike">104</strong> Strike Targets</div>
      <div class="t-pill" title="Pins where you rank #4-#10"><strong style="color:#38bdf8" id="kpi-contested">39</strong> Contested</div>
      <div class="t-pill" title="Blind Fog pins where you are unranked"><strong style="color:#ef4444" id="kpi-dark">85</strong> Blind Fog</div>
    </div>
  </div>
</header>

<!-- LEFT FLOATING MISSION & 9-RING TRAIL-OFF RADAR CARD -->
<aside id="mission-banner" class="hud-glass">
  <div class="mission-eyebrow">
    <span id="mission-mode-label">LENS 1 // FOG OF WAR RECON</span>
    <span id="mission-ring-filter" style="color:#fbbf24;cursor:pointer;display:none">[ALL RINGS]</span>
  </div>
  <div class="mission-headline" id="mission-headline">
    You command the inner 2.1 km core, hit a cliff edge at 3.3 km (27%), and go blind at 4.8 km+.
  </div>

  <div class="ring-curve-title">
    <span>9-Ring Trail-Off (Click Ring)</span>
    <span>Top-3 | Leader</span>
  </div>
  <div class="ring-bars" id="ring-bars"></div>
</aside>

<!-- BOTTOM-CENTER ACTION BUTTON (LIFT FOG OF WAR) -->
<div id="center-action-Wrap">
  <button class="fog-cta-btn" id="fog-toggle-btn">
    <span id="fog-btn-icon">[RECON SCAN]</span>
    <span id="fog-btn-text">LIFT FOG OF WAR : REVEAL WHO OWNS YOUR BLIND SPOTS</span>
  </button>
</div>

<!-- RIGHT FLOATING PLAIN-ENGLISH INSPECTOR CARD -->
<aside id="inspector-card" class="hud-glass">
  <div class="insp-header">
    <div class="insp-badge-row">
      <span class="status-pill" id="insp-badge" style="background:rgba(245,158,11,0.2);color:#fbbf24">PRIME STRIKE TARGET</span>
      <span style="font-family:var(--font-mono);font-size:10px;color:#94a3b8" id="insp-coord">Ring 4 - 3.3 km NE</span>
    </div>
    <div class="insp-title" id="insp-title">Select Any Radial Pin or Faction</div>
    <div class="insp-sub" id="insp-sub">Click any pin on the map or rival card below</div>
  </div>
  <div class="insp-body" id="insp-body"></div>
</aside>

<!-- MODE 4 FULL-STAGE MODAL: 9-RING TRAIL-OFF & 3-MOVE BATTLE PLAN -->
<section id="playbook-modal" class="hud-glass">
  <div class="pb-header">
    <div>
      <div style="font-family:var(--font-mono);font-size:10px;color:#38bdf8;font-weight:800;letter-spacing:0.08em">STRATEGIC COMMAND BRIEFING // RADIAL TRAIL-OFF &amp; 3-MOVE PLAYBOOK</div>
      <div style="font-size:15px;font-weight:800;color:#ffffff;margin-top:2px" id="pb-title">How to Push Example Mechanical's Boundary from 3.3 km Out to 6.8+ km</div>
    </div>
    <button class="scale-btn" id="pb-close-btn" style="height:32px;padding:0 14px;font-size:11px;border-color:#38bdf8;color:#38bdf8">BACK TO LIVE MAP [ESC]</button>
  </div>
  <div class="pb-body" id="pb-body"></div>
</section>

<!-- BOTTOM 11-COLUMN FACTION COMMAND DOCK -->
<footer id="faction-dock" class="hud-glass"></footer>

<script>
const MODEL = __MODEL_JSON__;

(function() {
  const state = {
    mode: 'FOG',          // 'FOG' | 'TURF' | 'STRIKE' | 'PLAYBOOK'
    lane: 'ALL',          // 'ALL' | 'q1' | 'q2' | 'q3'
    scale: 'FRONTIER',    // 'CORE' (2.5km) | 'FRONTIER' (5.5km) | 'METRO' (13km)
    fogLifted: false,
    selectedPinTag: null,
    selectedFactionId: null,
    selectedRing: null,
    basemapMode: 'dark'   // 'dark' | 'street'
  };

  const target = MODEL.target || MODEL.target_faction || {};
  const centerLat = Number((MODEL.grid && MODEL.grid.center_lat) || target.lat || 38.6441996);
  const centerLng = Number((MODEL.grid && MODEL.grid.center_lng) || target.lng || -121.2677833);
  const factions = MODEL.factions || [];
  const factionsById = {};
  factions.forEach(f => { factionsById[f.faction_id] = f; });
  const points = MODEL.points || [];
  const pointsByTag = {};
  points.forEach(p => { pointsByTag[p.tag] = p; });
  const lanes = MODEL.lanes || [];
  const radialPolicy = MODEL.radial_policy || { rings: [], sector_reach: {}, faction_envelopes: {} };

  function getPointView(pt) {
    if (state.lane === 'ALL' || !pt.by_lane || !pt.by_lane[state.lane]) {
      return pt.aggregate || pt;
    }
    return pt.by_lane[state.lane];
  }

  function friendlyArchetype(arch, isTarget) {
    if (isTarget) return 'YOUR HQ';
    if (arch === 'OVEREXTENDED_TIGER') return 'TIGER';
    if (arch === 'CITADEL_FORTRESS') return 'FORTRESS';
    if (arch === 'REGIONAL_HEGEMON') return 'HEGEMON';
    if (arch === 'CORRIDOR_BLOCKER') return 'BLOCKER';
    return 'OUTPOST';
  }

  function archBadgeStyle(arch, isTarget) {
    if (isTarget) return 'background:rgba(16,185,129,0.25);color:#34d399;border:1px solid rgba(16,185,129,0.5)';
    if (arch === 'OVEREXTENDED_TIGER') return 'background:rgba(245,158,11,0.22);color:#fbbf24;border:1px solid rgba(245,158,11,0.45)';
    if (arch === 'CITADEL_FORTRESS') return 'background:rgba(239,68,68,0.22);color:#f87171;border:1px solid rgba(239,68,68,0.45)';
    return 'background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4)';
  }

  // ==========================================================================
  // INITIALIZE LEAFLET MAP WITH WATERMARK-FREE OPENSTREETMAP TILES
  // ==========================================================================
  const map = L.map('leaflet-map', {
    center: [centerLat, centerLng],
    zoom: 12.75,
    zoomControl: false,
    preferCanvas: true,
    zoomSnap: 0.25
  });

  const osmTiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors | legends-geogrid'
  });
  osmTiles.addTo(map);

  // Asymmetric padding so the radial rings center squarely in the open stage between Left (284px) and Right (316px) HUD cards!
  function applyCameraScale(scaleKey) {
    state.scale = scaleKey;
    document.querySelectorAll('.scale-btn[data-scale]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.scale === scaleKey);
    });
    let radiusKm = 5.2;
    if (scaleKey === 'CORE') radiusKm = 2.3;
    else if (scaleKey === 'FRONTIER') radiusKm = 5.2;
    else if (scaleKey === 'METRO') radiusKm = 13.2;

    const dLat = radiusKm / 111.32;
    const dLng = radiusKm / (111.32 * Math.cos(centerLat * Math.PI / 180));
    const bounds = L.latLngBounds(
      [centerLat - dLat, centerLng - dLng],
      [centerLat + dLat, centerLng + dLng]
    );
    map.fitBounds(bounds, {
      paddingTopLeft: [300, 96],
      paddingBottomRight: [330, 128],
      animate: false
    });
    drawTacticalCanvas();
  }

  function selectDefaultPin() {
    const candidates = points.filter(p => {
      const pv = getPointView(p);
      return pv.tactical_class === 'PRIME_STRIKE_ZONE' && p.distance_from_target_km >= 2.0 && p.distance_from_target_km <= 3.5;
    }).sort((a, b) => getPointView(b).opportunity_score - getPointView(a).opportunity_score);
    if (candidates.length > 0) {
      state.selectedPinTag = candidates[0].tag;
    } else if (points.length > 0) {
      state.selectedPinTag = points[0].tag;
    }
  }

  // ==========================================================================
  // RENDER TOP COMMAND HUD
  // ==========================================================================
  function renderTopHud() {
    document.getElementById('hud-biz-name').textContent = target.name || 'Target Business';
    const votes = target.votes_count != null ? `${target.votes_count} Reviews` : 'Local Business';
    const rating = target.rating != null ? `${Number(target.rating).toFixed(1)}` : '';
    document.getElementById('hud-biz-sub').innerHTML =
      `${votes} <span class="star">&#9733;</span> ${rating} &bull; ${points.length} Pins`;

    const switcher = document.getElementById('lane-switcher');
    let html = `<span class="lane-label">Keyword:</span>`;
    const allActive = state.lane === 'ALL' ? 'active' : '';
    html += `<button class="lane-pill ${allActive}" data-lane="ALL">All Keywords <span class="pct">${Number(target.solv_pct || 0).toFixed(0)}%</span></button>`;
    lanes.forEach(l => {
      const act = state.lane === l.lane_id ? 'active' : '';
      const pct = Number(l.target_solv_pct != null ? l.target_solv_pct : l.solv_pct || 0).toFixed(0);
      html += `<button class="lane-pill ${act}" data-lane="${l.lane_id}">${l.query} <span class="pct">${pct}%</span></button>`;
    });
    switcher.innerHTML = html;

    switcher.querySelectorAll('.lane-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        state.lane = btn.dataset.lane;
        renderAll();
      });
    });
  }

  // ==========================================================================
  // RENDER MISSION BRIEFING & 9-RING TRAIL-OFF RADAR CARD
  // ==========================================================================
  function renderMissionCard() {
    let strongholds = 0, strikes = 0, contested = 0, darks = 0;
    points.forEach(p => {
      const pv = getPointView(p);
      if (pv.fog_state === 'CLEARED_CITADEL') strongholds++;
      else if (pv.fog_state === 'CONTESTED_VISION') contested++;
      else darks++;
      if (pv.tactical_class === 'PRIME_STRIKE_ZONE' || pv.tactical_class === 'FLANKING_MINE') {
        strikes++;
      }
    });

    document.getElementById('kpi-stronghold').textContent = strongholds;
    document.getElementById('kpi-strike').textContent = strikes;
    document.getElementById('kpi-contested').textContent = contested;
    document.getElementById('kpi-dark').textContent = darks;

    const modeLabels = {
      FOG: 'LENS 1 // FOG OF WAR & VISIBILITY',
      TURF: 'LENS 2 // 11-FACTION EMPIRES & REACH',
      STRIKE: 'LENS 3 // PAPER-TIGER STRIKE ZONES',
      PLAYBOOK: 'LENS 4 // RADIAL TRAIL-OFF & PLAYBOOK'
    };
    document.getElementById('mission-mode-label').textContent = modeLabels[state.mode] || modeLabels.FOG;

    const modeHeadlines = {
      FOG: state.fogLifted
        ? `Fog Lifted: Showing rival factions occupying your ${darks} blind-spot coordinates beyond 3.3 km.`
        : `You command the inner 2.1 km core (${strongholds} green pins), hit a cliff edge at 3.3 km, and go blind at 4.8 km+.`,
      TURF: state.selectedFactionId && factionsById[state.selectedFactionId]
        ? `Focusing ${factionsById[state.selectedFactionId].name}: ${factionsById[state.selectedFactionId].solv_pct}% Top-3 Share (${factionsById[state.selectedFactionId].votes_count || 0} reviews).`
        : `Compare all 11 Factions across the 26 km Sacramento theater. Click any rival below to isolate their territory.`,
      STRIKE: `${strikes} Winnable "Paper Tiger" pins identified where incumbents have fewer reviews than your ${target.votes_count || 275} reviews.`,
      PLAYBOOK: `3-Move Campaign Plan to push your Top-3 boundary from the 3.3 km cliff edge out to 6.8+ km.`
    };
    document.getElementById('mission-headline').textContent = modeHeadlines[state.mode];

    const clearRingBtn = document.getElementById('mission-ring-filter');
    clearRingBtn.style.display = state.selectedRing != null ? 'inline' : 'none';

    const ringMap = {};
    points.forEach(p => {
      const rIdx = p.ring != null ? p.ring : 0;
      if (!ringMap[rIdx]) {
        ringMap[rIdx] = { ring: rIdx, radius_km: p.ring_radius_km != null ? p.ring_radius_km : p.distance_from_target_km, pts: [] };
      }
      ringMap[rIdx].pts.push(p);
    });

    const ringRowsHtml = Object.keys(ringMap).sort((a, b) => Number(a) - Number(b)).map(rk => {
      const grp = ringMap[rk];
      const rIdx = Number(rk);
      let top3Hits = 0;
      let visHits = 0;
      const leaderCounts = {};
      grp.pts.forEach(p => {
        const pv = getPointView(p);
        const rVal = pv.best_target_rank != null ? pv.best_target_rank : pv.target_rank;
        if (state.lane === 'ALL') {
          top3Hits += (pv.top3_lanes || 0) / Math.max(1, pv.total_lanes || 3);
          visHits += (pv.top10_lanes || 0) / Math.max(1, pv.total_lanes || 3);
        } else {
          if (rVal != null && rVal <= 3) top3Hits += 1;
          if (rVal != null && rVal <= 10) visHits += 1;
        }
        const cfid = pv.controlling_faction_id;
        if (cfid && cfid !== 'UNALIGNED') {
          leaderCounts[cfid] = (leaderCounts[cfid] || 0) + 1;
        }
      });

      const pct = Math.round((top3Hits / Math.max(1, grp.pts.length)) * 100);
      const visPct = Math.round((visHits / Math.max(1, grp.pts.length)) * 100);
      let barColor = '#10b981';
      if (pct < 15 && visPct >= 20) barColor = '#f59e0b';
      else if (pct < 15) barColor = '#ef4444';
      else if (pct < 55) barColor = '#fbbf24';

      let domId = 'TARGET';
      let maxCnt = -1;
      Object.keys(leaderCounts).forEach(fid => {
        if (leaderCounts[fid] > maxCnt) {
          maxCnt = leaderCounts[fid];
          domId = fid;
        }
      });
      const domF = factionsById[domId];
      const leaderLabel = domF ? (domF.is_target ? 'YOU (Alpha)' : domF.name.split(' ').slice(0, 2).join(' ')) : 'Regional Pack';
      const leaderColor = domF ? domF.color : '#64748b';
      const isAct = state.selectedRing === rIdx ? 'active' : '';
      const radLabel = rIdx === 0 ? '0.0km' : `${Number(grp.radius_km).toFixed(1)}km`;

      return `
        <div class="ring-row ${isAct}" data-ring="${rIdx}" title="Click to highlight Ring ${rIdx} (${radLabel})">
          <div class="ring-dist">R${rIdx} ${radLabel}</div>
          <div class="ring-track">
            <div class="ring-fill" style="width:${Math.max(4, pct)}%;background:${barColor}"></div>
          </div>
          <div class="ring-pct" style="color:${barColor}">${pct}%</div>
          <div class="ring-leader" style="color:${leaderColor}">${leaderLabel}</div>
        </div>
      `;
    }).join('');

    const ringBarsEl = document.getElementById('ring-bars');
    ringBarsEl.innerHTML = ringRowsHtml;
    ringBarsEl.querySelectorAll('.ring-row').forEach(row => {
      row.addEventListener('click', () => {
        const r = Number(row.dataset.ring);
        state.selectedRing = (state.selectedRing === r) ? null : r;
        const ringPts = points.filter(p => (p.ring != null ? p.ring : 0) === r);
        if (ringPts.length > 0) {
          ringPts.sort((a, b) => getPointView(b).opportunity_score - getPointView(a).opportunity_score);
          state.selectedPinTag = ringPts[0].tag;
          state.selectedFactionId = null;
        }
        renderAll();
      });
    });
  }

  // ==========================================================================
  // RENDER 11-COLUMN BOTTOM FACTION COMMAND DOCK
  // ==========================================================================
  function renderFactionDock() {
    const dock = document.getElementById('faction-dock');
    dock.innerHTML = factions.map(f => {
      const isAct = state.selectedFactionId === f.faction_id ? 'active' : '';
      const solv = state.lane === 'ALL'
        ? Number(f.solv_pct || 0).toFixed(1)
        : Number((f.lane_stats && f.lane_stats[state.lane] && f.lane_stats[state.lane].solv_pct) || 0).toFixed(1);
      const archLabel = friendlyArchetype(f.archetype, f.is_target);
      const archStyle = archBadgeStyle(f.archetype, f.is_target);
      const votes = f.votes_count != null ? `${f.votes_count}*` : 'N/A';
      return `
        <div class="faction-card ${isAct}" data-fid="${f.faction_id}" style="border-top-color:${f.color}" title="${f.name} (${f.votes_count || 0} reviews)">
          <div class="fc-top">
            <span class="fc-code" style="background:${f.color}">${f.short_code}</span>
            <span class="fc-solv">${solv}%</span>
          </div>
          <div class="fc-name">${f.name}</div>
          <div class="fc-bottom">
            <span>${votes}</span>
            <span class="fc-arch" style="${archStyle}">${archLabel}</span>
          </div>
        </div>
      `;
    }).join('');

    dock.querySelectorAll('.faction-card').forEach(card => {
      card.addEventListener('click', () => {
        const fid = card.dataset.fid;
        if (state.selectedFactionId === fid) {
          state.selectedFactionId = null;
        } else {
          state.selectedFactionId = fid;
          if (state.mode === 'FOG') {
            state.mode = 'TURF';
            syncModeTabs();
          }
        }
        renderAll();
      });
    });
  }

  // ==========================================================================
  // RENDER RIGHT PLAIN-ENGLISH INSPECTOR CARD
  // ==========================================================================
  function renderInspector() {
    const badgeEl = document.getElementById('insp-badge');
    const coordEl = document.getElementById('insp-coord');
    const titleEl = document.getElementById('insp-title');
    const subEl = document.getElementById('insp-sub');
    const bodyEl = document.getElementById('insp-body');

    if (state.selectedFactionId && factionsById[state.selectedFactionId]) {
      const f = factionsById[state.selectedFactionId];
      const env = (radialPolicy.faction_envelopes && radialPolicy.faction_envelopes[f.faction_id]) || {};
      const archName = f.is_target ? 'COMMANDER HQ' : (f.archetype === 'OVEREXTENDED_TIGER' ? 'PAPER TIGER' : 'FORTRESS');
      badgeEl.textContent = f.is_target ? 'YOUR COMMANDER PROFILE' : `${f.short_code} // ${archName}`;
      badgeEl.setAttribute('style', archBadgeStyle(f.archetype, f.is_target));
      coordEl.textContent = `${Number(f.distance_from_center_km || 0).toFixed(1)} km from center`;
      titleEl.textContent = f.name;
      subEl.textContent = `${f.category || 'HVAC contractor'} | ${f.votes_count || 0} Reviews (${f.rating || 'N/A'}*)`;

      const youVotes = target.votes_count || 275;
      const rivVotes = f.votes_count || 0;
      const revDiff = youVotes - rivVotes;
      const revCompareText = f.is_target
        ? `You hold ${youVotes} reviews (${target.rating || 5.0}*), outgunning 6 of the Top 10 regional competitors.`
        : (revDiff >= 0
            ? `YOU OUTGUN THIS RIVAL: You have ${youVotes} reviews vs their ${rivVotes} reviews (+${revDiff} review advantage).`
            : `HEAVY REVIEW ADVANTAGE: This rival holds ${rivVotes} reviews vs your ${youVotes} reviews.`);

      const laneBreakdown = lanes.map(l => {
        const st = (f.lane_stats && f.lane_stats[l.lane_id]) || {};
        const tSt = (target.lane_stats && target.lane_stats[l.lane_id]) || {};
        return `
          <div style="display:flex;justify-content:space-between;font-size:10.5px;padding:4px 0;border-bottom:1px solid rgba(148,163,184,0.1)">
            <span style="color:#cbd5e1;font-weight:600">${l.query}</span>
            <span style="font-family:var(--font-mono)">
              <strong style="color:${f.color}">${Number(st.solv_pct || 0).toFixed(1)}%</strong>
              ${!f.is_target ? `<span style="color:#64748b"> vs You ${Number(tSt.solv_pct || 0).toFixed(1)}%</span>` : ''}
            </span>
          </div>
        `;
      }).join('');

      bodyEl.innerHTML = `
        <div class="story-box ${revDiff >= 0 ? 'emerald' : ''}">
          <div class="story-lbl">${f.is_target ? 'STRATEGIC POSTURE' : 'HEAD-TO-HEAD VERDICT'}</div>
          <div class="story-text">${revCompareText}</div>
        </div>

        <div class="story-box cyan">
          <div class="story-lbl">RADIAL EMPIRE &amp; TRAIL-OFF RANGE</div>
          <ul class="story-list">
            <li><strong>Top-3 Share:</strong> ${Number(f.solv_pct || 0).toFixed(1)}% (${f.top3_count || 0} Top-3 slots across 153 pins)</li>
            <li><strong>Max Top-3 Reach:</strong> ${Number(env.max_top3_reach_km || f.max_top3_distance_km || 0).toFixed(1)} km from its shop</li>
            <li><strong>Outer Trail-Off Horizon:</strong> ${Number(env.trail_off_radius_km || 0).toFixed(1)} km radius</li>
            <li><strong>Primary Vulnerability:</strong> ${f.primary_vulnerability || 'Localized reach'}</li>
          </ul>
        </div>

        <div class="story-box">
          <div class="story-lbl">KEYWORD SHARE COMPARISON</div>
          ${laneBreakdown}
        </div>

        <button class="scale-btn" id="clear-faction-btn" style="width:100%;height:30px;text-align:center">
          RETURN TO PIN INSPECTOR
        </button>
      `;

      const clrBtn = document.getElementById('clear-faction-btn');
      if (clrBtn) {
        clrBtn.addEventListener('click', () => {
          state.selectedFactionId = null;
          renderAll();
        });
      }
      return;
    }

    const pt = pointsByTag[state.selectedPinTag] || points[0];
    if (!pt) return;
    const pv = getPointView(pt);
    const tClass = pv.tactical_class || 'CONTESTED_FRONT';
    const opp = pv.opportunity_score != null ? pv.opportunity_score : 50;
    const rVal = state.lane === 'ALL' ? pv.best_target_rank : pv.target_rank;
    const rankStr = rVal != null ? `Rank #${rVal}` : 'Unranked (20+)';
    const ringNum = pt.ring != null ? pt.ring : 0;

    let classLabel = 'CONTESTED BORDER';
    let classStyle = 'background:rgba(56,189,248,0.2);color:#38bdf8;border:1px solid rgba(56,189,248,0.4)';
    if (tClass === 'OWNED_STRONGHOLD') {
      classLabel = 'YOUR STRONGHOLD';
      classStyle = 'background:rgba(16,185,129,0.22);color:#34d399;border:1px solid rgba(16,185,129,0.5)';
    } else if (tClass === 'PRIME_STRIKE_ZONE') {
      classLabel = `PRIME STRIKE (SCORE ${opp})`;
      classStyle = 'background:rgba(245,158,11,0.25);color:#fbbf24;border:1px solid rgba(245,158,11,0.55)';
    } else if (tClass === 'FLANKING_MINE') {
      classLabel = `PAPER-TIGER FLANK (${opp})`;
      classStyle = 'background:rgba(6,182,212,0.22);color:#22d3ee;border:1px solid rgba(6,182,212,0.5)';
    } else if (tClass === 'ENEMY_FORTRESS') {
      classLabel = 'ENEMY FORTRESS';
      classStyle = 'background:rgba(239,68,68,0.22);color:#f87171;border:1px solid rgba(239,68,68,0.45)';
    }

    badgeEl.textContent = classLabel;
    badgeEl.setAttribute('style', classStyle);
    coordEl.textContent = `Ring ${ringNum} (${Number(pt.distance_from_target_km).toFixed(1)} km ${pt.sector})`;
    titleEl.textContent = `Your Position: ${rankStr}`;
    subEl.textContent = `Controlled by: ${pv.controlling_faction_name || 'Local Pack'} | Pin ${pt.tag.toUpperCase()}`;

    const laneRankPills = lanes.map(l => {
      const le = pt.by_lane && pt.by_lane[l.lane_id];
      const rk = le && le.target_rank != null ? `#${le.target_rank}` : '20+';
      const col = (le && le.target_rank != null && le.target_rank <= 3) ? '#10b981'
        : ((le && le.target_rank != null && le.target_rank <= 10) ? '#f59e0b' : '#ef4444');
      return `
        <div style="flex:1;background:rgba(15,23,42,0.85);border:1px solid rgba(148,163,184,0.16);border-radius:5px;padding:4px 5px;text-align:center">
          <div style="font-size:8.5px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${l.query}</div>
          <div style="font-family:var(--font-mono);font-size:11.5px;font-weight:800;color:${col}">${rk}</div>
        </div>
      `;
    }).join('');

    const reasonsHtml = (pv.vulnerability_reasons || []).map(r => `<li>${r}</li>`).join('');
    const topItems = (pv.top_items || pt.top_items || []).slice(0, 6);
    const youVotes = target.votes_count || 275;

    const serpHtml = topItems.map(it => {
      const isYou = it.faction_id === 'TARGET';
      const fObj = it.faction_id && factionsById[it.faction_id];
      const fColor = fObj ? fObj.color : '#64748b';
      const fCode = fObj ? fObj.short_code : 'LOC';
      const itVotes = it.votes_count != null ? it.votes_count : null;
      const isPaperTiger = !isYou && itVotes != null && itVotes < youVotes;
      const badgeText = isYou ? 'YOU' : (isPaperTiger ? `BEATABLE (${itVotes} rev)` : `${itVotes != null ? itVotes + ' rev' : fCode}`);
      const badgeBg = isYou ? 'rgba(16,185,129,0.25);color:#34d399'
        : (isPaperTiger ? 'rgba(245,158,11,0.22);color:#fbbf24' : 'rgba(148,163,184,0.15);color:#cbd5e1');

      return `
        <div class="serp-item ${isYou ? 'is-you' : ''}">
          <div class="serp-top">
            <div class="serp-rank-name">
              <span class="serp-rk" style="border-left:3px solid ${fColor}">#${it.rank}</span>
              <span class="serp-name" title="${it.title}">${it.title}</span>
            </div>
            <span class="serp-tag" style="background:${badgeBg}">${badgeText}</span>
          </div>
          <div class="serp-meta">
            <span>${it.category || 'HVAC'}</span>
            <span>${it.rating != null ? it.rating + '*' : ''} &bull; ${Number(it.distance_from_pin_km || 0).toFixed(1)} km from shop</span>
          </div>
        </div>
      `;
    }).join('');

    bodyEl.innerHTML = `
      <div style="display:flex;gap:4px">${laneRankPills}</div>

      <div class="story-box ${tClass === 'OWNED_STRONGHOLD' ? 'emerald' : ''}">
        <div class="story-lbl">WHY THIS COORDINATE MATTERS</div>
        <ul class="story-list">${reasonsHtml}</ul>
      </div>

      <div class="story-box cyan">
        <div class="story-lbl">RECOMMENDED COUNTER-MOVE</div>
        <div class="story-text">${pv.counter_move || 'Build localized review and category signals along this corridor.'}</div>
      </div>

      <div>
        <div class="story-lbl" style="margin-bottom:5px">WHO RANKS #1 TO #6 AT THIS PIN (VS YOUR ${youVotes} REVIEWS)</div>
        <div class="serp-list">${serpHtml || '<div style="font-size:11px;color:#64748b">No SERP items recorded</div>'}</div>
      </div>
    `;
  }

  // ==========================================================================
  // RENDER MODE 4 FULL-WIDTH PLAYBOOK MODAL
  // ==========================================================================
  function renderPlaybookModal() {
    const modal = document.getElementById('playbook-modal');
    modal.classList.toggle('open', state.mode === 'PLAYBOOK');
    if (state.mode !== 'PLAYBOOK') return;

    const orders = MODEL.campaign_orders || {};
    const unlocks = orders.tech_tree_unlocks || [];
    const corridors = orders.strike_corridors || [];
    const sectorReach = radialPolicy.sector_reach || {};

    const sectorRows = Object.keys(sectorReach).map(sec => {
      const s = sectorReach[sec];
      return `
        <tr>
          <td style="font-weight:800;color:#ffffff">${s.sector} (${s.sector_name})</td>
          <td style="color:#10b981;font-weight:700">${Number(s.target_top3_reach_km).toFixed(1)} km</td>
          <td style="color:#38bdf8">${Number(s.target_top10_reach_km).toFixed(1)} km</td>
          <td style="color:#f59e0b">${Number(s.target_trail_off_km).toFixed(1)} km</td>
          <td style="color:${s.dominant_rival_color};font-weight:700">${s.dominant_rival_name}</td>
        </tr>
      `;
    }).join('');

    const corridorCards = corridors.slice(0, 3).map((c, idx) => `
      <div class="move-card ${idx === 0 ? 'emerald' : 'amber'}">
        <div class="move-head">
          <span>STRIKE CORRIDOR #${idx + 1}: ${c.title}</span>
          <span style="font-family:var(--font-mono);font-size:11px;color:#fbbf24">AVG OPP ${c.avg_opportunity_score}</span>
        </div>
        <div class="move-desc">
          <strong>Beatable Incumbent:</strong> ${c.weak_incumbent_name} (${c.weak_incumbent_vulnerability})<br/>
          <strong>Order:</strong> ${c.recommended_order}
        </div>
      </div>
    `).join('');

    const unlockCards = unlocks.slice(0, 3).map((u, idx) => `
      <div class="move-card ${idx === 0 ? 'emerald' : 'amber'}">
        <div class="move-head">
          <span>MOVE #${idx + 1}: ${u.name}</span>
          <span style="font-family:var(--font-mono);font-size:10px;color:#34d399">${u.unlock_type}</span>
        </div>
        <div class="move-desc">${u.impact_rationale}</div>
      </div>
    `).join('');

    document.getElementById('pb-body').innerHTML = `
      <div class="pb-grid-2">
        <div class="pb-card">
          <h3>1. Immediate Tech-Tree &amp; Category Unlocks (Highest Leverage)</h3>
          <div style="display:flex;flex-direction:column;gap:8px">${unlockCards}</div>
        </div>
        <div class="pb-card">
          <h3>2. Priority Paper-Tiger Strike Corridors (Expand 3.3 km -> 6.8 km)</h3>
          <div style="display:flex;flex-direction:column;gap:8px">${corridorCards}</div>
        </div>
      </div>

      <div class="pb-card">
        <h3>3. 8-Compass Sector Reach &amp; Trail-Off Boundary (Exact Distance Where Your Rankings Drop Off)</h3>
        <table class="sector-table">
          <thead>
            <tr>
              <th>Compass Sector</th>
              <th>Your Top-3 Reach</th>
              <th>Your Page-1 Reach</th>
              <th>Complete Trail-Off</th>
              <th>Dominant Sector Rival</th>
            </tr>
          </thead>
          <tbody>${sectorRows}</tbody>
        </table>
      </div>
    `;
  }

  // ==========================================================================
  // HIGH-DPI HTML5 TACTICAL CANVAS OVERLAY
  // ==========================================================================
  const canvas = document.getElementById('tactical-canvas');
  const ctx = canvas.getContext('2d');
  let hitRegions = [];

  function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawTacticalCanvas();
  }

  function hexToRgba(hex, alpha) {
    const clean = (hex || '#64748b').replace('#', '');
    const r = parseInt(clean.substring(0, 2), 16) || 100;
    const g = parseInt(clean.substring(2, 4), 16) || 116;
    const b = parseInt(clean.substring(4, 6), 16) || 139;
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function kmToPixelsAtCenter(km) {
    const pCenter = map.latLngToContainerPoint([centerLat, centerLng]);
    const edgeLat = centerLat + (km / 111.32);
    const pEdge = map.latLngToContainerPoint([edgeLat, centerLng]);
    return Math.abs(pCenter.y - pEdge.y);
  }

  function drawTacticalCanvas() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    ctx.clearRect(0, 0, w, h);
    hitRegions = [];

    const pCenter = map.latLngToContainerPoint([centerLat, centerLng]);
    const zoom = map.getZoom();

    // 1. DRAW 8 COMPASS SPOKES & CONCENTRIC RADIAL DISTANCE RINGS
    const ringRadiiKm = [0.55, 1.2, 2.1, 3.3, 4.8, 6.8, 9.5, 13.0];
    ctx.save();
    const outerPx = kmToPixelsAtCenter(13.0);
    const compassLabels = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    for (let i = 0; i < 8; i++) {
      const a = i * 45;
      const rad = (a * Math.PI) / 180;
      ctx.beginPath();
      ctx.moveTo(pCenter.x, pCenter.y);
      ctx.lineTo(pCenter.x + Math.sin(rad) * outerPx, pCenter.y - Math.cos(rad) * outerPx);
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.14)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    ringRadiiKm.forEach((rKm, idx) => {
      const ringNum = idx + 1;
      const rPx = kmToPixelsAtCenter(rKm);
      if (rPx < 14) return;
      const isSelectedRing = state.selectedRing === ringNum;
      const isCliffRing = Math.abs(rKm - 3.3) < 0.15;

      ctx.beginPath();
      ctx.arc(pCenter.x, pCenter.y, rPx, 0, Math.PI * 2);
      if (isSelectedRing) {
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.95)';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([]);
      } else if (isCliffRing) {
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.65)';
        ctx.lineWidth = 1.8;
        ctx.setLineDash([6, 4]);
      } else {
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.24)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 4]);
      }
      ctx.stroke();
      ctx.setLineDash([]);

      // Distance badge at 35 deg (NE arc) so it never collides with North radial pins!
      const badgeRad = (28 * Math.PI) / 180;
      const bx = pCenter.x + Math.sin(badgeRad) * rPx;
      const by = pCenter.y - Math.cos(badgeRad) * rPx;
      if (rPx > 36 && by > 96 && by < h - 90 && bx > 300 && bx < w - 330) {
        const lbl = isCliffRing ? `3.3 KM CLIFF` : `${rKm} KM`;
        ctx.font = '700 9px "JetBrains Mono", monospace';
        const tw = ctx.measureText(lbl).width + 8;
        ctx.fillStyle = isCliffRing ? 'rgba(120, 53, 15, 0.92)' : 'rgba(9, 14, 24, 0.88)';
        ctx.fillRect(bx - tw / 2, by - 7, tw, 14);
        ctx.strokeStyle = isCliffRing ? '#f59e0b' : 'rgba(148,163,184,0.32)';
        ctx.strokeRect(bx - tw / 2, by - 7, tw, 14);
        ctx.fillStyle = isCliffRing ? '#fde68a' : '#cbd5e1';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(lbl, bx, by);
      }
    });
    ctx.restore();

    // 2. MODE-SPECIFIC TERRITORY GLOWS & FOG OF WAR SHROUD
    points.forEach(p => {
      const pv = getPointView(p);
      const ptPx = map.latLngToContainerPoint([p.lat, p.lng]);
      if (ptPx.x < -80 || ptPx.x > w + 80 || ptPx.y < -80 || ptPx.y > h + 80) return;

      const ringIdx = p.ring != null ? p.ring : 3;
      const cellRadius = Math.max(14, Math.min(54, kmToPixelsAtCenter(ringIdx <= 2 ? 0.42 : (ringIdx <= 4 ? 0.82 : 1.45))));

      if (state.mode === 'FOG') {
        if (!state.fogLifted) {
          if (pv.fog_state === 'CLEARED_CITADEL') {
            const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 2, ptPx.x, ptPx.y, cellRadius * 1.25);
            grad.addColorStop(0, 'rgba(16, 185, 129, 0.32)');
            grad.addColorStop(1, 'rgba(16, 185, 129, 0.0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.25, 0, Math.PI * 2);
            ctx.fill();
          } else if (pv.fog_state === 'CONTESTED_VISION') {
            const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 2, ptPx.x, ptPx.y, cellRadius * 1.15);
            grad.addColorStop(0, 'rgba(245, 158, 11, 0.24)');
            grad.addColorStop(1, 'rgba(245, 158, 11, 0.0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.15, 0, Math.PI * 2);
            ctx.fill();
          } else {
            const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 4, ptPx.x, ptPx.y, cellRadius * 1.45);
            grad.addColorStop(0, 'rgba(3, 6, 14, 0.80)');
            grad.addColorStop(0.7, 'rgba(5, 9, 18, 0.55)');
            grad.addColorStop(1, 'rgba(5, 9, 18, 0.0)');
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.45, 0, Math.PI * 2);
            ctx.fill();
          }
        } else {
          const fCol = pv.controlling_faction_color || '#64748b';
          const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 2, ptPx.x, ptPx.y, cellRadius * 1.2);
          grad.addColorStop(0, hexToRgba(fCol, 0.30));
          grad.addColorStop(1, hexToRgba(fCol, 0.0));
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.2, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (state.mode === 'TURF') {
        const fCol = pv.controlling_faction_color || '#64748b';
        const isFocusFaction = !state.selectedFactionId || pv.controlling_faction_id === state.selectedFactionId;
        const alpha = isFocusFaction ? 0.32 : 0.06;
        const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 2, ptPx.x, ptPx.y, cellRadius * 1.25);
        grad.addColorStop(0, hexToRgba(fCol, alpha));
        grad.addColorStop(1, hexToRgba(fCol, 0.0));
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.25, 0, Math.PI * 2);
        ctx.fill();
      } else if (state.mode === 'STRIKE') {
        if (pv.tactical_class === 'PRIME_STRIKE_ZONE' || pv.tactical_class === 'FLANKING_MINE') {
          const grad = ctx.createRadialGradient(ptPx.x, ptPx.y, 2, ptPx.x, ptPx.y, cellRadius * 1.3);
          grad.addColorStop(0, 'rgba(245, 158, 11, 0.36)');
          grad.addColorStop(1, 'rgba(245, 158, 11, 0.0)');
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.arc(ptPx.x, ptPx.y, cellRadius * 1.3, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    });

    // Selected Faction Reach Envelope Circle
    if (state.selectedFactionId && factionsById[state.selectedFactionId]) {
      const sf = factionsById[state.selectedFactionId];
      const env = (radialPolicy.faction_envelopes && radialPolicy.faction_envelopes[sf.faction_id]) || {};
      const fPt = map.latLngToContainerPoint([sf.lat, sf.lng]);
      const reachKm = Number(env.max_top3_reach_km || sf.gravity_radius_km || 3.0);
      const reachPx = kmToPixelsAtCenter(reachKm);

      if (reachPx > 15) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(fPt.x, fPt.y, reachPx, 0, Math.PI * 2);
        ctx.strokeStyle = sf.color;
        ctx.lineWidth = 2.2;
        ctx.setLineDash([8, 5]);
        ctx.stroke();
        ctx.fillStyle = hexToRgba(sf.color, 0.08);
        ctx.fill();
        ctx.restore();
      }
    }

    // 3. DRAW ALL 153 RADIAL PINS (CRISP & UNOBSTRUCTED)
    points.forEach(p => {
      const pv = getPointView(p);
      const ptPx = map.latLngToContainerPoint([p.lat, p.lng]);
      if (ptPx.x < -30 || ptPx.x > w + 30 || ptPx.y < -30 || ptPx.y > h + 30) return;

      const ringIdx = p.ring != null ? p.ring : 3;
      const isSelected = state.selectedPinTag === p.tag;
      const isRingFiltered = state.selectedRing != null && state.selectedRing !== ringIdx;

      let baseR = zoom >= 13.8 ? 11.5 : (zoom >= 12.2 ? 9.0 : 7.0);
      if (ringIdx === 0) baseR += 2.5;
      else if (ringIdx === 1 && zoom < 13.2) baseR = Math.min(baseR, 7.2);
      if (isSelected) baseR += 3.5;

      let fillCol = '#1e293b';
      let strokeCol = '#64748b';
      let labelText = '';
      let textColor = '#ffffff';
      let alpha = isRingFiltered ? 0.22 : 1.0;

      const rVal = state.lane === 'ALL' ? pv.best_target_rank : pv.target_rank;

      if (state.selectedFactionId && factionsById[state.selectedFactionId]) {
        const fid = state.selectedFactionId;
        let fRank = null;
        const items = pv.top_items || p.top_items || [];
        for (let i = 0; i < items.length; i++) {
          if (items[i].faction_id === fid) {
            fRank = items[i].rank;
            break;
          }
        }
        if (fRank != null && fRank <= 3) {
          fillCol = factionsById[fid].color;
          strokeCol = '#ffffff';
          labelText = `#${fRank}`;
        } else if (fRank != null) {
          fillCol = '#0f172a';
          strokeCol = factionsById[fid].color;
          labelText = `#${fRank}`;
          textColor = '#cbd5e1';
        } else {
          fillCol = 'rgba(15, 23, 42, 0.55)';
          strokeCol = 'rgba(100, 116, 139, 0.3)';
          alpha = 0.3;
        }
      } else if (state.mode === 'FOG') {
        if (pv.fog_state === 'CLEARED_CITADEL') {
          fillCol = '#10b981';
          strokeCol = '#a7f3d0';
          labelText = rVal != null ? `#${rVal}` : '#1';
          textColor = '#04130d';
        } else if (pv.fog_state === 'CONTESTED_VISION') {
          fillCol = '#f59e0b';
          strokeCol = '#fde68a';
          labelText = rVal != null ? `#${rVal}` : '#6';
          textColor = '#05080f';
        } else if (!state.fogLifted) {
          fillCol = '#090d16';
          strokeCol = 'rgba(239, 68, 68, 0.5)';
          labelText = '';
        } else {
          fillCol = pv.controlling_faction_color || '#475569';
          strokeCol = '#f8fafc';
          const cf = factionsById[pv.controlling_faction_id];
          labelText = zoom >= 12.2 ? (cf ? cf.short_code : '') : '';
          textColor = '#ffffff';
        }
      } else if (state.mode === 'TURF') {
        fillCol = pv.controlling_faction_color || '#334155';
        strokeCol = pv.controlling_faction_id === 'TARGET' ? '#a7f3d0' : 'rgba(255,255,255,0.75)';
        const cf = factionsById[pv.controlling_faction_id];
        labelText = zoom >= 12.2 ? (cf ? cf.short_code : '') : (rVal != null && rVal <= 3 ? `#${rVal}` : '');
        textColor = pv.controlling_faction_id === 'TARGET' ? '#04130d' : '#ffffff';
      } else if (state.mode === 'STRIKE') {
        if (pv.tactical_class === 'PRIME_STRIKE_ZONE' || pv.tactical_class === 'FLANKING_MINE') {
          fillCol = '#f59e0b';
          strokeCol = '#ffffff';
          labelText = `${pv.opportunity_score}`;
          textColor = '#05080f';
          baseR += 1.0;
        } else if (pv.tactical_class === 'OWNED_STRONGHOLD') {
          fillCol = '#10b981';
          strokeCol = '#a7f3d0';
          labelText = rVal != null ? `#${rVal}` : '#1';
          textColor = '#04130d';
        } else if (pv.tactical_class === 'ENEMY_FORTRESS') {
          fillCol = '#7f1d1d';
          strokeCol = '#ef4444';
          labelText = zoom >= 12.5 ? 'FT' : '';
          textColor = '#fca5a5';
          alpha = 0.65;
        } else {
          fillCol = '#1e293b';
          strokeCol = '#475569';
          labelText = rVal != null ? `#${rVal}` : '';
          textColor = '#94a3b8';
          alpha = 0.45;
        }
      }

      ctx.save();
      ctx.globalAlpha = alpha;

      if (state.mode === 'STRIKE' && pv.tactical_class === 'PRIME_STRIKE_ZONE') {
        ctx.beginPath();
        ctx.arc(ptPx.x, ptPx.y, baseR + 4, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.72)';
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }

      if (isSelected) {
        ctx.beginPath();
        ctx.arc(ptPx.x, ptPx.y, baseR + 6, 0, Math.PI * 2);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.arc(ptPx.x, ptPx.y, baseR, 0, Math.PI * 2);
      ctx.fillStyle = fillCol;
      ctx.fill();
      ctx.lineWidth = isSelected ? 2.5 : 1.3;
      ctx.strokeStyle = strokeCol;
      ctx.stroke();

      if (labelText && baseR >= 7.0) {
        ctx.font = `800 ${baseR >= 9.5 ? 9 : 7.5}px "JetBrains Mono", monospace`;
        ctx.fillStyle = textColor;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, ptPx.x, ptPx.y + 0.5);
      }
      ctx.restore();

      hitRegions.push({
        type: 'PIN',
        tag: p.tag,
        x: ptPx.x,
        y: ptPx.y,
        r: baseR + 4
      });
    });

    // 4. DRAW CITADEL HQ MARKERS WITH OUTWARD LEADER LINES (NEVER COVERING PINS)
    const placedBoxes = [];
    points.forEach(p => {
      if ((p.ring != null ? p.ring : 3) <= 2) {
        const pp = map.latLngToContainerPoint([p.lat, p.lng]);
        placedBoxes.push({ x: pp.x - 12, y: pp.y - 12, w: 24, h: 24 });
      }
    });

    const showHqCallouts = (state.mode === 'TURF') || (state.selectedFactionId != null);
    const hqList = (state.mode === 'TURF')
      ? factions.slice(0, 7)
      : (state.selectedFactionId && factionsById[state.selectedFactionId]
          ? [factions[0], factionsById[state.selectedFactionId]]
          : [factions[0]]);

    hqList.forEach((f, idx) => {
      if (!f || f.lat == null || f.lng == null) return;
      const fPx = map.latLngToContainerPoint([f.lat, f.lng]);
      if (fPx.x < 300 || fPx.x > w - 320 || fPx.y < 95 || fPx.y > h - 85) return;

      const dSize = f.is_target ? 10 : 8;
      ctx.save();
      ctx.translate(fPx.x, fPx.y);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = f.color;
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.8;
      ctx.fillRect(-dSize / 2, -dSize / 2, dSize, dSize);
      ctx.strokeRect(-dSize / 2, -dSize / 2, dSize, dSize);
      ctx.restore();

      if (showHqCallouts) {
        const angleRad = f.is_target ? (-Math.PI * 0.72) : ((idx * 52 - 35) * Math.PI / 180);
        const offsetDist = f.is_target ? 82 : 68;
        const lxCenter = fPx.x + Math.cos(angleRad) * offsetDist;
        const lyCenter = fPx.y + Math.sin(angleRad) * offsetDist;

        const shortName = f.is_target
          ? `YOU: Alpha HQ (${f.votes_count || 275}*)`
          : `${f.short_code} ${f.name.split(' ').slice(0, 2).join(' ')} (${f.votes_count || 0}*)`;
        ctx.font = '700 9.5px "Inter", sans-serif';
        const bw = ctx.measureText(shortName).width + 10;
        const bh = 17;
        const bx = lxCenter - bw / 2;
        const by = lyCenter - bh / 2;

        const collides = placedBoxes.some(b =>
          !(bx + bw < b.x || bx > b.x + b.w || by + bh < b.y || by > b.y + b.h)
        );
        if (!collides && bx > 295 && bx + bw < w - 315 && by > 95 && by + bh < h - 80) {
          placedBoxes.push({ x: bx, y: by, w: bw, h: bh });
          ctx.save();
          ctx.beginPath();
          ctx.moveTo(fPx.x, fPx.y);
          ctx.lineTo(lxCenter, lyCenter);
          ctx.strokeStyle = f.color;
          ctx.lineWidth = 1.4;
          ctx.stroke();

          ctx.fillStyle = 'rgba(5, 8, 15, 0.92)';
          ctx.fillRect(bx, by, bw, bh);
          ctx.strokeStyle = f.color;
          ctx.lineWidth = 1.3;
          ctx.strokeRect(bx, by, bw, bh);
          ctx.fillStyle = '#f8fafc';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(shortName, lxCenter, lyCenter);
          ctx.restore();
        }
      }

      hitRegions.push({
        type: 'FACTION',
        fid: f.faction_id,
        x: fPx.x,
        y: fPx.y,
        r: 12
      });
    });
  }

  // ==========================================================================
  // INTERACTIONS & EVENT HANDLERS
  // ==========================================================================
  map.on('move zoom viewreset resize', drawTacticalCanvas);
  window.addEventListener('resize', resizeCanvas);

  map.on('click', function(ev) {
    const pt = ev.containerPoint;
    for (let i = hitRegions.length - 1; i >= 0; i--) {
      const hr = hitRegions[i];
      const dx = pt.x - hr.x;
      const dy = pt.y - hr.y;
      if (dx * dx + dy * dy <= hr.r * hr.r) {
        if (hr.type === 'FACTION') {
          state.selectedFactionId = hr.fid;
          renderAll();
          return;
        }
        if (hr.type === 'PIN') {
          state.selectedPinTag = hr.tag;
          state.selectedFactionId = null;
          renderAll();
          return;
        }
      }
    }
  });

  function syncModeTabs() {
    document.querySelectorAll('.mode-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.mode === state.mode);
    });
    const fogBtn = document.getElementById('fog-toggle-btn');
    fogBtn.style.display = state.mode === 'FOG' ? 'flex' : 'none';
    fogBtn.classList.toggle('lifted', state.fogLifted);
    document.getElementById('fog-btn-icon').textContent = state.fogLifted ? '[VISION ACTIVE]' : '[RECON SCAN]';
    document.getElementById('fog-btn-text').textContent = state.fogLifted
      ? 'FOG LIFTED : SHOWING ENEMY FACTIONS IN BLIND SPOTS (CLICK TO RESTORE FOG)'
      : 'LIFT FOG OF WAR : REVEAL WHO OWNS YOUR BLIND SPOTS';
  }

  document.querySelectorAll('.mode-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      state.mode = btn.dataset.mode;
      syncModeTabs();
      renderAll();
    });
  });

  document.querySelectorAll('.scale-btn[data-scale]').forEach(btn => {
    btn.addEventListener('click', () => {
      applyCameraScale(btn.dataset.scale);
    });
  });

  document.getElementById('basemap-btn').addEventListener('click', function() {
    const stage = document.getElementById('map-stage');
    if (state.basemapMode === 'dark') {
      stage.classList.remove('basemap-dark');
      stage.classList.add('basemap-street');
      state.basemapMode = 'street';
      this.textContent = 'DARK MAP';
    } else {
      stage.classList.remove('basemap-street');
      stage.classList.add('basemap-dark');
      state.basemapMode = 'dark';
      this.textContent = 'LIGHT MAP';
    }
  });

  document.getElementById('fog-toggle-btn').addEventListener('click', () => {
    state.fogLifted = !state.fogLifted;
    syncModeTabs();
    renderAll();
  });

  document.getElementById('pb-close-btn').addEventListener('click', () => {
    state.mode = 'STRIKE';
    syncModeTabs();
    renderAll();
  });

  document.getElementById('mission-ring-filter').addEventListener('click', () => {
    state.selectedRing = null;
    renderAll();
  });

  document.getElementById('cmd-home-btn').addEventListener('click', () => {
    state.selectedFactionId = 'TARGET';
    renderAll();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === '1') { state.mode = 'FOG'; syncModeTabs(); renderAll(); }
    else if (e.key === '2') { state.mode = 'TURF'; syncModeTabs(); renderAll(); }
    else if (e.key === '3') { state.mode = 'STRIKE'; syncModeTabs(); renderAll(); }
    else if (e.key === '4') { state.mode = 'PLAYBOOK'; syncModeTabs(); renderAll(); }
    else if (e.key === 'Escape') {
      if (state.mode === 'PLAYBOOK') state.mode = 'STRIKE';
      state.selectedFactionId = null;
      state.selectedRing = null;
      syncModeTabs();
      renderAll();
    }
  });

  function renderAll() {
    renderTopHud();
    renderMissionCard();
    renderFactionDock();
    renderInspector();
    renderPlaybookModal();
    drawTacticalCanvas();
  }

  window.BATTLEFIELD_CONSOLE = {
    setMode: (m) => { state.mode = m; syncModeTabs(); renderAll(); },
    setScale: (s) => { applyCameraScale(s); },
    toggleFog: () => { state.fogLifted = !state.fogLifted; syncModeTabs(); renderAll(); },
    selectFaction: (fid) => { state.selectedFactionId = fid; renderAll(); },
    selectPin: (tag) => { state.selectedPinTag = tag; state.selectedFactionId = null; renderAll(); },
    getState: () => state
  };

  selectDefaultPin();
  syncModeTabs();
  resizeCanvas();
  applyCameraScale('FRONTIER');
  renderAll();
})();
</script>
</body>
</html>
"""


def render_console(model: dict[str, Any], output_path: str | Path) -> Path:
    """Render the self-contained HTML5 Radial Strategy-Game Battlefield Console."""
    clean_model = _sanitize_no_em_dash(model)
    target_name = (
        (clean_model.get("target") or {}).get("name")
        or (clean_model.get("business") or {}).get("name")
        or "Target Business"
    )
    page_title = f"{target_name} // Radial Battlefield Command (legends-geogrid)"
    model_json = json.dumps(clean_model, ensure_ascii=False).replace("<", "\\u003c")

    html_content = (
        HTML_TEMPLATE.replace("__PAGE_TITLE__", page_title.replace("\u2014", " - "))
        .replace("__MODEL_JSON__", model_json)
        .replace("\u2014", " - ")
    )

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_content, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render Radial Strategy-Game Battlefield Console HTML.")
    parser.add_argument("--model", required=True, help="Path to battlefield-model.json")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args(argv)

    model_path = Path(args.model).resolve()
    model = json.loads(model_path.read_text(encoding="utf-8-sig"))
    out = render_console(model, Path(args.output).resolve())
    print(json.dumps({"status": "ok", "console_html": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
