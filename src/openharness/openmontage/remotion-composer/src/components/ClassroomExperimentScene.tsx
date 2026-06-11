import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

type ExperimentVariant = "question" | "setup" | "morning" | "evening" | "rule";

export interface ClassroomExperimentSceneProps {
  variant?: ExperimentVariant;
  title?: string;
  subtitle?: string;
  note?: string;
  backgroundColor?: string;
  accentColor?: string;
  textColor?: string;
}

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const variantAngle = (variant: ExperimentVariant, progress: number) => {
  if (variant === "morning") {
    return interpolate(progress, [0, 1], [-150, -20]);
  }
  if (variant === "evening") {
    return interpolate(progress, [0, 1], [-20, 115]);
  }
  if (variant === "rule") {
    return interpolate(progress, [0, 1], [-135, 135]);
  }
  return interpolate(progress, [0, 1], [-40, 20]);
};

export const ClassroomExperimentScene: React.FC<ClassroomExperimentSceneProps> = ({
  variant = "setup",
  title,
  subtitle,
  note,
  backgroundColor = "#F7F0E3",
  accentColor = "#D88A35",
  textColor = "#253426",
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const sceneProgress = clamp01(frame / Math.max(1, durationInFrames - 1));
  const entrance = spring({ frame, fps, config: { damping: 18, stiffness: 90 } });

  const angle = (variantAngle(variant, sceneProgress) * Math.PI) / 180;
  const globeRadius = 148;
  const stickerX = Math.cos(angle) * globeRadius;
  const stickerY = Math.sin(angle) * globeRadius * 0.72;
  const stickerScale = interpolate(Math.cos(angle), [-1, 1], [0.65, 1.1]);
  const stickerOpacity = interpolate(Math.cos(angle), [-1, -0.25, 1], [0.25, 0.5, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const headline =
    title ||
    (variant === "question"
      ? "太阳真的在跑吗？"
      : variant === "setup"
        ? "我们做个小实验"
        : variant === "morning"
          ? "转进光里，就是早晨"
          : variant === "evening"
            ? "转出光里，就是傍晚"
            : "地球向东转，太阳像往西走");

  const subline =
    subtitle ||
    (variant === "question"
      ? "每天东升西落，其实是我们在转"
      : variant === "setup"
        ? "手电筒当太阳，小球当地球"
        : variant === "morning"
          ? "小贴纸看见了光，就像看见日出"
          : variant === "evening"
            ? "小贴纸离开光，就像太阳落山"
            : "记住这句，就不会搞反");

  return (
    <AbsoluteFill
      style={{
        background: backgroundColor,
        color: textColor,
        overflow: "hidden",
        fontFamily: "Space Grotesk, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(37,52,38,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(37,52,38,0.045) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          opacity: 0.7,
        }}
      />

      <div
        style={{
          position: "absolute",
          left: 118,
          top: 94,
          maxWidth: 760,
          opacity: entrance,
          transform: `translateY(${interpolate(entrance, [0, 1], [34, 0])}px)`,
        }}
      >
        <div
          style={{
            fontSize: 76,
            lineHeight: 1.05,
            fontWeight: 900,
            letterSpacing: "-0.045em",
          }}
        >
          {headline}
        </div>
        <div
          style={{
            marginTop: 20,
            fontSize: 34,
            lineHeight: 1.35,
            fontWeight: 600,
            color: "rgba(37,52,38,0.72)",
          }}
        >
          {subline}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 260,
          background: "linear-gradient(180deg, rgba(205,156,96,0), rgba(205,156,96,0.34))",
        }}
      />

      <div
        style={{
          position: "absolute",
          left: 126,
          bottom: 188,
          width: 340,
          height: 148,
          borderRadius: "42px 110px 110px 42px",
          background: "#3A3326",
          transform: `translateX(${interpolate(entrance, [0, 1], [-80, 0])}px) rotate(-3deg)`,
          opacity: entrance,
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 32,
            top: 34,
            width: 128,
            height: 80,
            borderRadius: 28,
            background: "#574A34",
          }}
        />
        <div
          style={{
            position: "absolute",
            right: -36,
            top: 23,
            width: 78,
            height: 102,
            borderRadius: "50%",
            background: accentColor,
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 88,
            bottom: -72,
            width: 68,
            height: 72,
            background: "#6A5435",
            borderRadius: "0 0 18px 18px",
          }}
        />
      </div>

      <div
        style={{
          position: "absolute",
          left: 432,
          bottom: 132,
          width: 845,
          height: 320,
          opacity: variant === "question" ? 0.35 : 0.72,
          clipPath: "polygon(0 34%, 100% 0, 100% 100%, 0 66%)",
          background:
            "linear-gradient(90deg, rgba(249,190,85,0.72), rgba(249,190,85,0.28), rgba(249,190,85,0))",
          filter: "blur(1px)",
          transform: `scaleX(${interpolate(entrance, [0, 1], [0.82, 1])})`,
          transformOrigin: "left center",
        }}
      />

      <div
        style={{
          position: "absolute",
          right: 220,
          bottom: 112,
          width: 500,
          height: 500,
          transform: `scale(${interpolate(entrance, [0, 1], [0.85, 1])})`,
          opacity: entrance,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 44,
            borderRadius: "50%",
            background:
              "radial-gradient(circle at 35% 30%, #8BB98D 0 20%, #5D956F 21% 48%, #406F69 49% 72%, #315A59 73% 100%)",
            boxShadow: "inset -26px -24px 0 rgba(0,0,0,0.12), 0 34px 65px rgba(56,43,28,0.2)",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 245,
            top: 46,
            width: 16,
            height: 404,
            borderRadius: 999,
            background: "#253426",
            opacity: 0.8,
            transform: "rotate(-18deg)",
          }}
        />
        <div
          style={{
            position: "absolute",
            left: 250 + stickerX - 24,
            top: 250 + stickerY - 24,
            width: 48,
            height: 48,
            borderRadius: "50% 50% 45% 45%",
            background: "#FFF2D2",
            border: `5px solid ${accentColor}`,
            opacity: stickerOpacity,
            transform: `scale(${stickerScale})`,
            boxShadow: "0 8px 18px rgba(0,0,0,0.22)",
          }}
        >
          <div
            style={{
              position: "absolute",
              left: 12,
              top: 13,
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: textColor,
            }}
          />
          <div
            style={{
              position: "absolute",
              right: 12,
              top: 13,
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: textColor,
            }}
          />
        </div>
        <div
          style={{
            position: "absolute",
            left: 92,
            top: 96,
            width: 316,
            height: 316,
            borderRadius: "50%",
            border: `8px dashed ${accentColor}`,
            opacity: variant === "rule" ? 0.78 : 0.34,
            transform: `rotate(${interpolate(sceneProgress, [0, 1], [0, 70])}deg)`,
          }}
        />
      </div>

      {note && (
        <div
          style={{
            position: "absolute",
            right: 118,
            top: 112,
            maxWidth: 520,
            padding: "22px 30px",
            borderRadius: 28,
            background: "rgba(255,255,255,0.62)",
            border: "2px solid rgba(37,52,38,0.1)",
            fontSize: 30,
            lineHeight: 1.3,
            fontWeight: 700,
            opacity: spring({ frame: frame - 12, fps, config: { damping: 18 } }),
          }}
        >
          {note}
        </div>
      )}

      <div
        style={{
          position: "absolute",
          left: 120,
          bottom: 88,
          padding: "14px 22px",
          borderRadius: 999,
          background: "rgba(255,255,255,0.62)",
          color: "rgba(37,52,38,0.74)",
          fontSize: 24,
          fontWeight: 800,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        flashlight = sun · ball = earth · sticker = us
      </div>
    </AbsoluteFill>
  );
};
