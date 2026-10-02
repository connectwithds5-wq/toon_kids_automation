# Toon Kids — Remotion renderer

This renderer adapts the architecture of the Remotion Prompt-to-Video template for the Toon Kids pipeline.

Pipeline:
Gemini/local story -> Pillow cartoon scenes -> Hindi Edge TTS -> Remotion composition -> 1080x1920 MP4.

The original Remotion template demonstrates timeline-based background, text and audio synchronization. This project keeps that rendering concept while retaining Toon Kids' existing story/history/TTS generation.

Run:
npm install
npm run render
