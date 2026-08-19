import { redirect } from "next/navigation";

export default function CvReviewPage() {
  redirect("/profile?tab=cv");
}
