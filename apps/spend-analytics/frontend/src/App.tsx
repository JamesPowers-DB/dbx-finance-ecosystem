import React, { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { Home } from "./pages/Home";
import { Contracts } from "./pages/Contracts";
import { Suppliers } from "./pages/Suppliers";
import { CostSavings } from "./pages/CostSavings";
import { Chatbot } from "./pages/Chatbot";
import { Analytics } from "./pages/Analytics";
import { getMe } from "./api";
import type { MeResponse } from "./types";

export type PageId = "home" | "analytics" | "contracts" | "suppliers" | "savings" | "chatbot";

export default function App() {
  const [page, setPage] = useState<PageId>("home");
  const [user, setUser] = useState<MeResponse | null>(null);
  const [resolving, setResolving] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  // Deep-link payload for cross-page launches (e.g. an Analytics supplier row
  // opening that supplier's scorecard on the Suppliers page).
  const [focusSupplierId, setFocusSupplierId] = useState<string | null>(null);

  useEffect(() => {
    getMe()
      .then(setUser)
      .catch(() => setUser({ email: "user@example.com", display_name: "User", initials: "U" }))
      .finally(() => setResolving(false));
  }, []);

  if (resolving) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--fs-body-sm)",
          color: "var(--fg-3)",
        }}
      >
        resolving identity…
      </div>
    );
  }

  const navigate = (p: string, opts?: { supplierId?: string }) => {
    setSearchQuery("");
    setFocusSupplierId(opts?.supplierId ?? null);
    setPage(p as PageId);
  };

  return (
    <>
      <Sidebar page={page} onNavigate={navigate} user={user} searchQuery={searchQuery} onSearch={setSearchQuery} />
      <main style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {page === "home"      && <Home onNavigate={navigate} />}
        {page === "analytics" && <Analytics onNavigate={navigate} />}
        {page === "contracts" && <Contracts searchQuery={searchQuery} />}
        {page === "suppliers" && <Suppliers searchQuery={searchQuery} focusSupplierId={focusSupplierId} />}
        {page === "savings"   && <CostSavings searchQuery={searchQuery} />}
        {page === "chatbot"   && <Chatbot />}
      </main>
    </>
  );
}
