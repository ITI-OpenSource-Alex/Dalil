import { redirect } from "next/navigation";

// Moved under Practice (Phase D, docs/IA-REDESIGN-PROPOSAL.md): Speaking is
// no longer a top-level sidebar section on its own, it's one of Practice's
// two skills. Kept as a redirect rather than deleted so any existing
// bookmark or external link to /speaking keeps working.
export default function SpeakingRedirect() {
  redirect("/practice/speaking");
}
