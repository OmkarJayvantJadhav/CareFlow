import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Root } from "../App";
import { SessionProvider } from "../session";

const HOSPITAL = {
  name: { en: "Omkar General Hospital" },
  address: "Pune, Maharashtra",
  phone: "020 2555 0101",
  emergency_note: { en: "Emergency department at Gate 1." },
};
const DIRECTORY = {
  reception_hours: "08:00–18:00",
  departments: [
    {
      name: "Cardiology",
      floor: 2,
      opd_start: "09:00",
      opd_end: "13:00",
      doctors: [{ name: "Dr. Meera Joshi", languages: ["en", "mr"], opd_days: [1, 3] }],
    },
  ],
};

function renderRoot(config) {
  globalThis.fetch = vi.fn(async (url) => {
    const body = String(url).endsWith("/config") ? config : DIRECTORY;
    return new Response(JSON.stringify(body), { status: 200 });
  });
  render(
    <SessionProvider>
      <MemoryRouter>
        <Root />
      </MemoryRouter>
    </SessionProvider>,
  );
}

describe("home page", () => {
  it("shows a hospital's own homepage to visitors", async () => {
    renderRoot({ demo_mode: false, allow_registration: true, hospital: HOSPITAL, demo_site_url: null });
    expect(await screen.findByRole("heading", { level: 1, name: "Omkar General Hospital" })).toBeInTheDocument();
    expect(await screen.findByText("Dr. Meera Joshi")).toBeInTheDocument();
    expect(screen.getByText("Reception: 08:00–18:00", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByText("Floor 2 · OPD 09:00–13:00")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Book an appointment/ })[0]).toHaveAttribute("href", "/book");
    expect(screen.getByRole("link", { name: /Emergency 112/ })).toHaveAttribute("href", "tel:112");
    expect(screen.getByText("Emergency department at Gate 1.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Try the demo/ })).not.toBeInTheDocument();
  });

  it("keeps the demo's start page", async () => {
    renderRoot({ demo_mode: true, demo_notice: false, allow_registration: true, hospital: HOSPITAL });
    expect(await screen.findByText("Or explore without an account")).toBeInTheDocument();
    expect(screen.queryByText("Our doctors")).not.toBeInTheDocument();
  });
});
