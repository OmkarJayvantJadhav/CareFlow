import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SessionProvider } from "../session";
import Chat from "./Chat";

const base = {
  conversation_id: "c1",
  language: "en",
  citations: [],
  actions: [],
  needs_confirmation: false,
  confirmation: null,
  handoff: false,
  ticket_id: null,
  emergency: false,
  offer_handoff: false,
};

function mockReplies(...replies) {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, init) => {
    // The session asks once what the deployment offers; that is not a chat turn.
    if (String(url).endsWith("/config")) {
      return new Response(JSON.stringify({ demo_mode: true, allow_registration: true }), { status: 200 });
    }
    calls.push({ body: JSON.parse(String(init?.body ?? "{}")) });
    return new Response(JSON.stringify({ ...base, ...replies.shift() }), { status: 200 });
  });
  return calls;
}

function renderChat() {
  render(
    <SessionProvider>
      <MemoryRouter>
        <Chat />
      </MemoryRouter>
    </SessionProvider>,
  );
}

function type(text) {
  fireEvent.change(screen.getByLabelText("Type your message…"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("chat", () => {
  it("shows the emergency panel and nothing else to act on", async () => {
    mockReplies({ reply: "This may be a medical emergency.", emergency: true });
    renderChat();
    type("my father collapsed and is not breathing");
    expect(await screen.findByRole("alert")).toHaveTextContent("Call 112 or 108 now");
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
  });

  it("confirms a card with its action id and shows citations as chips", async () => {
    const expires = new Date(Date.now() + 5 * 60000).toISOString();
    const calls = mockReplies(
      {
        reply: "Please confirm: book Dr. Anand Kulkarni on Saturday at 09:00?",
        needs_confirmation: true,
        actions: [{ tool: "book_appointment", ok: true, label: "Preparing the booking" }],
        confirmation: {
          action_id: "abc123",
          tool: "book_appointment",
          summary: {
            patient: "Asha Patil",
            doctor: "Dr. Anand Kulkarni",
            department: "Cardiology",
            date: "Saturday 24 Oct 2026",
            time: "09:00",
          },
          expires_at: expires,
          expires_in_seconds: 300,
        },
      },
      {
        reply: "Done. Fast for 10–12 hours [1].",
        citations: [
          {
            ref: 1,
            title: "Lipid profile",
            section: "Before the test",
            collection: "test_preparation",
            language: "en",
            source_path: "knowledge/en/test_preparation/lipid-profile.md",
            last_verified: "2026-10-01",
          },
        ],
      },
    );
    renderChat();
    type("Book Dr Kulkarni on Saturday");
    expect(await screen.findByText("Please confirm")).toBeInTheDocument();
    expect(screen.getByText("Dr. Anand Kulkarni (Cardiology)")).toBeInTheDocument();
    expect(screen.getByText("Preparing the booking")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(calls[1].body.confirm_action_id).toBe("abc123"));
    expect(await screen.findByRole("button", { name: "[1] Lipid profile — Before the test" })).toBeInTheDocument();
    expect(screen.queryByText("Please confirm")).not.toBeInTheDocument(); // an answered card disappears
  });
});
