import { toCsv } from "./Analytics";

it("exports CSV with quoting", () => {
  expect(toCsv(["department", "no_shows"], [["ENT", 3], ['Say "hi", ok', null]])).toBe(
    'department,no_shows\nENT,3\n"Say ""hi"", ok",',
  );
});
