/**
 * Gate for internal-only routes, mirroring the /dev-log rule: on while
 * developing, opt-in in production.
 *
 * In a client bundle only NEXT_PUBLIC_* variables are exposed, so this returns
 * false in production there. The route itself still honours ENABLE_DICE_DEMO
 * because it is evaluated on the server.
 */
export function diceDemoEnabled(): boolean {
  return process.env.NODE_ENV !== "production" || process.env.ENABLE_DICE_DEMO === "true";
}
