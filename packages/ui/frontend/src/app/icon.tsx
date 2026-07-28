import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

// Generate a tiny "M" mark on a deep cyan background. Served by Next.js as
// the page favicon (and the head <link rel="icon">) without needing a
// binary asset under public/.
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          fontSize: 22,
          background: "linear-gradient(135deg, #0e7490 0%, #155e75 100%)",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#e0f2fe",
          fontWeight: 700,
          fontFamily: "system-ui, sans-serif",
        }}
      >
        M
      </div>
    ),
    { ...size },
  );
}