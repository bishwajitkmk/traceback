import type { RequestDefinition, ResponseSummary } from "../types";

/**
 * A tiny stand-in for the demo "checkout" FastAPI app that replays are sent to.
 * `fixed` flips the known bugs off so the verify-the-fix flow can be demonstrated.
 */
export function simulate(req: RequestDefinition, fixed: boolean): ResponseSummary {
  const json = (status: number, body: unknown): ResponseSummary => ({
    status,
    headers: { "content-type": "application/json", "x-correlation-id": crypto.randomUUID() },
    body,
    body_truncated: false,
  });
  const body = (req.body ?? {}) as Record<string, unknown>;

  if (req.method === "POST" && req.path === "/checkout") {
    const quantity = Number(body.quantity ?? 1);
    if (quantity <= 0) {
      return fixed
        ? json(422, { error: { code: "invalid_quantity", message: "quantity must be at least 1" } })
        : json(500, { detail: "Internal Server Error" });
    }
    return json(201, {
      order_id: "ord_7c1e",
      status: "confirmed",
      quantity,
      total: Math.round(quantity * 19.99 * 100) / 100,
    });
  }

  const order = /^\/orders\/([^/]+)$/.exec(req.path);
  if (req.method === "GET" && order) {
    if (order[1] === "ord_missing") {
      return fixed
        ? json(404, { error: { code: "not_found", message: "Order not found" } })
        : json(500, { detail: "Internal Server Error" });
    }
    return json(200, { order_id: order[1], status: "confirmed", items: [{ sku: "TB-001", qty: 1 }] });
  }

  if (req.method === "GET" && req.path === "/cart") {
    return json(200, { items: [], currency: "USD", total: 0 });
  }

  if (req.method === "GET" && req.path.startsWith("/reports/daily")) {
    return fixed
      ? json(200, { date: "2026-10-13", orders: 128, revenue: 2558.72 })
      : json(500, { detail: "Internal Server Error" });
  }

  return json(404, { detail: "Not Found" });
}
