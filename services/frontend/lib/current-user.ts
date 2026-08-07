/**
 * Fallback current-user id used only while the real, authenticated profile
 * (useCurrentUser, wired to GET /api/profile) is still loading or has
 * failed to load — not the primary source of truth. Every consumer that
 * can reach a real identity (chat, exam session creation, speaking
 * history, the sidebar) prefers `user.id` from that hook and falls back to
 * this value only transiently; nothing should treat it as a real user id
 * once a profile has resolved (GOA-035/BUG-047).
 *
 * Kept as an explicit export rather than deleted — a few call sites (e.g.
 * speaking WebSocket construction) still read it directly as their own
 * fallback.
 */
export const CURRENT_USER_ID = "user-lina";
