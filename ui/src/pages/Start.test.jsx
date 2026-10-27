import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SessionProvider } from "../session";
import Start from "./Start";

function renderStart(config) {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, init) => {
    calls.push({ url: String(url), body: JSON.parse(String(init?.body ?? "{}")) });
    if (String(url).endsWith("/config")) return new Response(JSON.stringify(config), { status: 200 });
    return new Response(JSON.stringify({ error: { code: "USERNAME_TAKEN", message: "taken" } }), { status: 409 });
  });
  render(
    <SessionProvider>
      <MemoryRouter>
        <Start />
      </MemoryRouter>
    </SessionProvider>,
  );
  return calls;
}

describe("start page", () => {
  it("offers the demo roles on the demo deployment", async () => {
    renderStart({ demo_mode: true, demo_notice: true, allow_registration: true });
    expect(await screen.findByText("Or try the demo without an account")).toBeInTheDocument();
  });

  it("offers the roles without calling the hospital fictional when the notice is off", async () => {
    renderStart({ demo_mode: true, demo_notice: false, allow_registration: true });
    expect(await screen.findByText("Or explore without an account")).toBeInTheDocument();
    expect(screen.getByText(/Explore every role without an account/)).toBeInTheDocument();
    expect(screen.queryByText(/Fictional hospital/)).not.toBeInTheDocument();
  });

  it("has no demo on a hospital's own deployment", async () => {
    renderStart({ demo_mode: false, allow_registration: true });
    expect(await screen.findByText(/created by the hospital's administrator/)).toBeInTheDocument();
    expect(screen.queryByText("Or try the demo without an account")).not.toBeInTheDocument();
  });

  it("links a hospital's deployment to its demo site when one is set", async () => {
    renderStart({ demo_mode: false, allow_registration: true, demo_site_url: "https://demo.example.org" });
    const link = await screen.findByRole("link", { name: /Try the demo/ });
    expect(link).toHaveAttribute("href", "https://demo.example.org");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("signs a caregiver up without a birth year or phone number", async () => {
    const calls = renderStart({ demo_mode: false, allow_registration: true });
    fireEvent.click(await screen.findByRole("button", { name: "Create account" }));
    fireEvent.click(screen.getByRole("button", { name: "A family member I help" }));
    expect(screen.queryByLabelText("Mobile number")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Sanjay Kale" } });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "sanjay.k" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "lotus-pond-88" } });
    fireEvent.submit(screen.getByRole("form", { name: "Create account" }));
    await screen.findByRole("alert");
    const sent = calls.find((c) => c.url.endsWith("/auth/register")).body;
    expect(sent).toEqual({
      account_type: "caregiver",
      name: "Sanjay Kale",
      username: "sanjay.k",
      password: "lotus-pond-88",
      language: "en",
    });
  });
});
