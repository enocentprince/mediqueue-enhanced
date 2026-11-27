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
  await expect(page.getByLabel("Email address")).toBeVisible();
  await page.getByLabel("Email address").fill("admin@example.com");
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

test("admin can create an admin account and sees their own name", async ({ page }) => {
  let createdAccount;
  await page.route("**/auth/me", (route) =>
    route.fulfill({
      json: {
        user: {
          id: "admin-1",
          name: "Jordan Admin",
          email: "jordan@example.com",
          role: "admin",
        },
      },
    }),
  );
  await page.route("**/consultations/mine/latest", (route) =>
    route.fulfill({ json: null }),
  );
  await page.route("**/admin/consultations", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/admin/appointments**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/admin/accounts", (route) => {
    createdAccount = route.request().postDataJSON();
    return route.fulfill({
      status: 201,
      json: {
        id: "admin-2",
        name: createdAccount.name,
        email: createdAccount.email,
        role: "admin",
      },
    });
  });

  await page.goto("/#/admin");
  await expect(page.getByText("Welcome, Jordan Admin.")).toBeVisible();
  await page.getByLabel("Full name").fill("Taylor Admin");
  await page.getByLabel("Email address").fill("taylor@example.com");
  await page.getByLabel("Mobile number").fill("0712345678");
  await page.getByLabel("Password", { exact: true }).fill("taylor-password");
  await page.getByLabel("Confirm password").fill("different-password");
  await page.getByRole("button", { name: "Create admin account" }).click();
  await expect(page.getByRole("alert")).toHaveText("The admin passwords do not match.");
  expect(createdAccount).toBeUndefined();
  await page
    .getByLabel("Confirm password")
    .fill("taylor-password");
  await page.getByRole("button", { name: "Create admin account" }).click();

  await expect(
    page.locator(".admin-account-section").getByRole("status"),
  ).toHaveText("Admin account created for Taylor Admin.");
  expect(createdAccount).toMatchObject({
    name: "Taylor Admin",
    email: "taylor@example.com",
    mobile: "0712345678",
    password: "taylor-password",
  });
});
