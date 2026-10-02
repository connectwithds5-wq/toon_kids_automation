import { Composition } from "remotion";
import { ToonKidsVideo } from "./ToonKidsVideo";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="ToonKidsVideo"
    component={ToonKidsVideo}
    durationInFrames={7 * 8 * 30}
    fps={30}
    width={1080}
    height={1920}
  />
);
