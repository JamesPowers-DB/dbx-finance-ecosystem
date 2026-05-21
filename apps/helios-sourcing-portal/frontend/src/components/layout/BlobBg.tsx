import React from "react";

export function BlobBg() {
  return (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 0,
      }}
    >
      {/* Lava blob */}
      <div
        style={{
          position: "absolute",
          top: "-10%",
          left: "20%",
          width: 520,
          height: 520,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(255,54,33,0.12) 0%, transparent 70%)",
          filter: "blur(60px)",
          animation: "home-drift 9s ease-in-out infinite",
        }}
      />
      {/* Blue blob */}
      <div
        style={{
          position: "absolute",
          top: "30%",
          right: "-5%",
          width: 400,
          height: 400,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(4,53,93,0.10) 0%, transparent 70%)",
          filter: "blur(60px)",
          animation: "home-drift 12s ease-in-out infinite reverse",
        }}
      />
      {/* Yellow blob */}
      <div
        style={{
          position: "absolute",
          bottom: "5%",
          left: "5%",
          width: 360,
          height: 360,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(255,171,0,0.08) 0%, transparent 70%)",
          filter: "blur(50px)",
          animation: "home-drift 15s ease-in-out infinite 3s",
        }}
      />
    </div>
  );
}
