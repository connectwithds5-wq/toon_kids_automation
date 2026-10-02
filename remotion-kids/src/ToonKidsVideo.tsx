import { Audio, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AbsoluteFill, interpolate, Sequence } from "remotion";

const SCENES = [
  { image: "scene_art_01.png", audio: "tts_01.mp3" },
  { image: "scene_art_02.png", audio: "tts_02.mp3" },
  { image: "scene_art_03.png", audio: "tts_03.mp3" },
  { image: "scene_art_04.png", audio: "tts_04.mp3" },
  { image: "scene_art_05.png", audio: "tts_05.mp3" },
  { image: "scene_art_06.png", audio: "tts_06.mp3" },
  { image: "scene_art_07.png", audio: "tts_07.mp3" }
];

const sceneText = [
  "एक नई मजेदार शुरुआत!",
  "कुछ नया खोजते हैं...",
  "दोस्ती से रास्ता आसान होता है।",
  "वाह! हमें कुछ खास मिला!",
  "अब राज़ खुलने वाला है...",
  "कितना मजेदार सरप्राइज!",
  "सीख: मिलकर कोशिश करना सबसे अच्छा है।"
];

export const ToonKidsVideo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sceneFrames = 8 * fps;

  return (
    <AbsoluteFill style={{ backgroundColor: "#BFE8FF", fontFamily: "Noto Sans Devanagari, Noto Sans, sans-serif" }}>
      {SCENES.map((scene, index) => {
        const from = index * sceneFrames;
        const local = frame - from;
        const progress = Math.max(0, Math.min(1, local / sceneFrames));
        const scale = interpolate(progress, [0, 1], [1.02, 1.10]);
        const opacity = interpolate(local, [0, 12, sceneFrames - 12, sceneFrames], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

        return (
          <Sequence key={scene.image} from={from} durationInFrames={sceneFrames}>
            <AbsoluteFill>
              <Img
                src={staticFile(`content/kids/images/${scene.image}`)}
                style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${scale})` }}
              />
              <AbsoluteFill
                style={{
                  background: "linear-gradient(180deg, rgba(0,0,0,0.02) 45%, rgba(0,0,0,0.55) 100%)",
                  opacity
                }}
              />
              <div style={{
                position: "absolute",
                top: 54,
                left: 54,
                padding: "12px 22px",
                borderRadius: 24,
                backgroundColor: "rgba(255,255,255,0.92)",
                color: "#4C6FFF",
                fontSize: 28,
                fontWeight: 800
              }}>
                TOON KIDS • {index + 1}/7
              </div>
              <div style={{
                position: "absolute",
                left: 55,
                right: 55,
                bottom: 100,
                padding: "26px 30px",
                borderRadius: 32,
                backgroundColor: "rgba(0,0,0,0.62)",
                color: "white",
                textAlign: "center",
                fontSize: 48,
                lineHeight: 1.35,
                fontWeight: 800,
                opacity
              }}>
                {sceneText[index]}
              </div>
              <Audio src={staticFile(`content/kids/audio/${scene.audio}`)} volume={1} />
            </AbsoluteFill>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
