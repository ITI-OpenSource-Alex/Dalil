/**
 * Placeholder current-user id shared by the chat/speaking flow and the
 * speaking history pages, so sessions created via chat actually show up in
 * the user's own history.
 *
 * There is no real authentication wired up yet (no session/JWT lookup) —
 * this is a known gap tracked outside this ticket's scope, not something
 * GOA-042 fixes. Replace with a real auth-derived user id once available.
 */
export const CURRENT_USER_ID = "user-lina";
