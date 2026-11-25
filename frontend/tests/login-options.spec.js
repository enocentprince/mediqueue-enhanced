import { test, expect } from "@playwright/test";

test("home login choices work on desktop and mobile", async ({ page }) => {
  for (const width of [1280, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(page.locator("header").getByRole("link", { name: /sign in/i })).toHaveCount(0);
    await page.getByRole("link", { name: "Log in as Admin", exact: true }).click();
    await expect(page).toHaveURL(/#\/login\/admin$/);
    await expect(page.getByText("Use your authorised admin account to continue.")).toBeVisible();
    await expect(page.getByRole("button", { name: /Explore the patient demo/ })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText("Log in as Admin", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: "Patient", exact: true }).click();
    await expect(page.getByRole("button", { name: /Explore the patient demo/ })).toBeVisible();
    await page.goto("/");
    await page.getByRole("link", { name: "Log in as Patient", exact: true }).click();
    await expect(page).toHaveURL(/#\/login\/patient$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  }
});

test("admin login redirects to the guarded admin workspace", async ({ page }) => {
  await page.route("**/auth/me", route => route.fulfill({ status: 401, json: { detail: "Not signed in" } }));
  await page.route("**/auth/admin-login", route => route.fulfill({ json: { user: { id: "sample", name: "Patient", email: "patient@example.com", role: "patient" } } }));
  await page.goto("/#/login/admin");
  await expect(page.getByLabel("Email address")).toHaveCount(0);
  await page.getByLabel("Password", { exact: true }).fill("Admin@");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/#\/admin$/);
  await expect(page.getByRole("heading", { name: "Administrator access required." })).toBeVisible();
});

test("admin dashboard lists appointments and searches by patient email", async ({ page }) => {
  const firstAppointment = {
    id: "appointment-1",
    patient: { name: "Alex Patient", email: "alex@example.com" },
    starts_at: "2035-06-01T10:00:00Z",
    department: "General medicine",
    location: "Block B",
    status: "confirmed",
  };
  const secondAppointment = {
    id: "appointment-2",
    patient: { name: "Sam Patient", email: "sam@example.com" },
    starts_at: "2035-06-02T10:00:00Z",
    department: "Cardiology",
    location: "Block C",
    status: "completed",
  };
  await page.route("**/auth/me", route => route.fulfill({
    json: { user: { id: "admin", name: "Admin", email: "admin@example.com", role: "admin" } },
  }));
  await page.route("**/consultations/mine/latest", route => route.fulfill({ json: null }));
  await page.route("**/admin/consultations", route => route.fulfill({ json: [] }));
  await page.route("**/admin/appointments**", route => {
    const email = new URL(route.request().url()).searchParams.get("email");
    return route.fulfill({ json: email ? [firstAppointment] : [firstAppointment, secondAppointment] });
  });

  await page.goto("/");
  const dashboardLink = page.locator("nav").getByRole("link", { name: "My dashboard", exact: true });
  await expect(dashboardLink).toBeVisible();
  await dashboardLink.click();
  await expect(page.getByRole("heading", { name: "My dashboard", exact: true })).toBeVisible();
  await expect(page.getByText("Cardiology")).toBeVisible();

  await page.getByLabel("Patient email").fill("alex@example.com");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Alex Patient")).toBeVisible();
  await expect(page.getByText("Sam Patient")).toHaveCount(0);
  await expect(page.getByText("General medicine")).toBeVisible();
});
