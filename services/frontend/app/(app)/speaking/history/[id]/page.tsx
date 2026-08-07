import { redirect } from "next/navigation";

// See app/(app)/speaking/page.tsx for why this redirects rather than
// rendering directly.
export default async function SpeakingSessionDetailRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/practice/speaking/history/${id}`);
}
