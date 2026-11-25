import { test, expect } from "@playwright/test";

test("patient can search completed and cancelled appointment history", async ({
  page,
}) => {
  await page.route("**/auth/me", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "patient-1",
          name: "Alex Patient",
          email: "alex@example.com",
          role: "patient",
        },
      },
    }),
  );
  await page.route("**/consultations/mine/latest", (route) =>
    route.fulfill({ json: null }),
  );
  await page.route("**/appointments", (route) =>
    route.fulfill({
      json: [
        {
          id: "completed-1",
          consultation_id: "consultation-1",
          slot_id: "slot-1",
          starts_at: "2024-06-01T10:00:00Z",
          department: "Cardiology",
          location: "Block B",
          status: "completed",
        },
        {
          id: "cancelled-1",
          consultation_id: "consultation-2",
          slot_id: "slot-2",
          starts_at: "2024-05-01T10:00:00Z",
          department: "General medicine",
          location: "Block C",
          status: "cancelled",
        },
        {
          id: "current-1",
          consultation_id: "consultation-3",
          slot_id: "slot-3",
          starts_at: "2030-07-01T10:00:00Z",
          department: "Neurology",
          location: "Block D",
          status: "confirmed",
        },
      ],
    }),
  );

  await page.goto("/#/history");
  await expect(
    page.getByRole("heading", { name: "History", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".history-appointment")).toHaveCount(2);
  await expect(page.getByText("Neurology")).toHaveCount(0);

  const search = page.getByRole("searchbox", {
    name: "Search your appointment history",
  });
  await search.fill("CARDIOLOGY");
  await expect(page.locator(".history-appointment")).toHaveCount(1);
  await expect(page.getByText("Cardiology")).toBeVisible();

  await search.fill("block c");
  await expect(page.locator(".history-appointment")).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "Cancelled appointment", exact: true }),
  ).toBeVisible();

  await search.fill("no matching visit");
  await expect(
    page.getByRole("heading", { name: "No matching appointments" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.locator(".history-appointment")).toHaveCount(2);
});
