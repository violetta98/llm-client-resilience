# Task bodies of the TypeScript references for the CONFIRMATORY tasks R6, W5, B5, H4
# (tasks/CONFIRM_TASKS.md). Loaded by references/build_confirm.py into the namespace of
# tasks.py; same prelude and budgets as the benchmark references.

BODIES["R6"] = '''
export class StockError extends Error {}

export async function getStockLevels(baseUrl: string, productId: string): Promise<Record<string, unknown>> {
  let r: RefResponse;
  try {
    r = await refCall(deadlineIn(9500), { method: "GET", url: `${baseUrl}/v1/products/${encodeURIComponent(productId)}/stock`, idempotent: true });
  } catch (e) {
    throw new StockError(String(e), { cause: e });
  }
  if (r.status !== 200) throw new StockError(`HTTP ${r.status}`);
  return r.json();
}
'''

IMPORTS["W5"] = ['import { randomUUID } from "node:crypto";']
BODIES["W5"] = '''
export class TicketError extends Error {}

export async function createTicket(baseUrl: string, customerId: string, subject: string, message: string): Promise<Record<string, unknown>> {
  const key = randomUUID(); // one key per ticket: every retry reuses it
  const headers = () => ({ "Content-Type": "application/json", "Idempotency-Key": MUTANT === "UNSAFE_POST_RETRY" ? randomUUID() : key });
  let r: RefResponse;
  try {
    r = await refCall(deadlineIn(9500), { method: "POST", url: `${baseUrl}/v1/tickets`, idempotent: true, headers,
      body: JSON.stringify({ customer_id: customerId, subject, message }) });
  } catch (e) {
    throw new TicketError(String(e), { cause: e });
  }
  if (r.status !== 201) throw new TicketError(`HTTP ${r.status}: ${r.text.slice(0, 200)}`);
  return r.json();
}
'''

BODIES["B5"] = '''
export class ShipmentUpdatesError extends Error {}

export async function fetchShipmentUpdates(baseUrl: string, carrierId: string, since: string): Promise<Array<Record<string, unknown>>> {
  const qs = new URLSearchParams({ since });
  let r: RefResponse;
  try {
    r = await refCall(deadlineIn(28000), { method: "GET", url: `${baseUrl}/v1/carriers/${encodeURIComponent(carrierId)}/shipment-updates?${qs}`, idempotent: true });
  } catch (e) {
    throw new ShipmentUpdatesError(String(e), { cause: e });
  }
  if (r.status !== 200) throw new ShipmentUpdatesError(`HTTP ${r.status}`);
  return r.json().updates;
}
'''

BODIES["H4"] = '''
const DEFAULT_PREFERENCES = { email: true, sms: false, push: false };

// Returns the documented default on any failure.
export async function getNotificationPreferences(preferencesUrl: string, userId: string): Promise<Record<string, unknown>> {
  try {
    const r = await refCall(deadlineIn(1800), { method: "GET", url: `${preferencesUrl}/v1/users/${encodeURIComponent(userId)}/notification-preferences`, idempotent: true });
    if (r.status !== 200) return { ...DEFAULT_PREFERENCES };
    const p = r.json();
    if (typeof p.email !== "boolean" || typeof p.sms !== "boolean" || typeof p.push !== "boolean") return { ...DEFAULT_PREFERENCES };
    return { email: p.email, sms: p.sms, push: p.push };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}
'''
