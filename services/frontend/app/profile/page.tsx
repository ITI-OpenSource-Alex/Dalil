import Skeleton from "@/components/ui/skeleton";

export default function ProfilePage() {
  const loading = true;

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </div>
    );
  }

  return <h1>Profile Page</h1>;
}
