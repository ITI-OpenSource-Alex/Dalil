import { redirect } from "next/navigation";

// See app/(app)/speaking/page.tsx for why this redirects rather than
// rendering directly.
export default function SpeakingHistoryRedirect() {
  redirect("/practice/speaking/history");
}
